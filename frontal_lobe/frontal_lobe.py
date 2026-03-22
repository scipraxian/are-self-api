import json
import logging
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async
from django.utils import timezone
from litellm.exceptions import APIConnectionError, RateLimitError

from central_nervous_system.models import Spike, SpikeStatus
from central_nervous_system.utils import resolve_environment_context
from environments.variable_renderer import VariableRenderer
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import (
    ChatMessage,
    ChatMessageRole,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from frontal_lobe.serializers import LLMFunctionCall, LLMToolCall
from frontal_lobe.synapse_client import SynapseClient, SynapseResponse
from hypothalamus.hypothalamus import Hypothalamus
from hypothalamus.models import AIModelProvider, AIModelProviderUsageRecord
from hypothalamus.serializers import ModelSelection
from identity.addons.addon_package import AddonPackage
from identity.addons.addon_registry import ADDON_REGISTRY
from identity.models import IdentityDisc
from parietal_lobe.parietal_lobe import ParietalLobe
from temporal_lobe.models import IterationShiftParticipant

logger = logging.getLogger(__name__)

STATUS_ID = 'status_id'
ROLE = 'role'
CONTENT = 'content'


def _serialize_messages_sync(turn_record, all_messages):
    return [
        chat_message_to_llm_dict(msg, current_turn=turn_record.turn_number)
        for msg in all_messages
    ]


def _fetch_disc_sync(session_id):
    s = ReasoningSession.objects.select_related(
        'identity_disc', 'identity_disc__budget'
    ).get(id=session_id)
    return s.identity_disc


def _mint_usage_record_sync(
    turn_record: ReasoningTurn,
    identity_disc: 'IdentityDisc',
    model_selection: ModelSelection,
    response: SynapseResponse,
    estimated_cost: Decimal,
    duration: timedelta,
):
    """Synchronously creates the immutable FinOps ledger entry."""

    # Safety Check: If the API crashed before processing tokens, don't mint a blank ledger
    if response.is_error and response.tokens_input == 0:
        return

    provider_record = (
        AIModelProvider.objects.filter(
            provider_unique_model_id=model_selection.provider_model_id
        )
        .select_related('ai_model')
        .first()
    )

    if provider_record:
        AIModelProviderUsageRecord.objects.create(
            ai_model_provider=provider_record,
            model_provider=provider_record,
            ai_model=provider_record.ai_model,
            identity_disc=identity_disc,
            reasoning_turn=turn_record,
            query_time=duration,
            input_tokens=response.tokens_input,
            output_tokens=response.tokens_output,
            reasoning_tokens=response.metrics.reasoning_tokens,
            cache_read_input_tokens=response.metrics.cache_read_input_tokens,
            cache_creation_input_tokens=response.metrics.cache_creation_input_tokens,
            audio_tokens=response.metrics.audio_tokens,
            estimated_cost=estimated_cost,
        )


class FrontalLobe:
    """Async execution wrapper for the Frontal Lobe AI loop."""

    def __init__(self, spike: Spike):
        self.spike = spike
        self.spike_id = spike.id
        self.log_output: List[str] = []
        self.parietal_lobe: Optional[ParietalLobe] = None

        self.session: Optional[ReasoningSession] = None

        self._cached_environment_id = None
        self._cached_shift_id = None
        self._cached_iteration_id = None

    # --- IO & Logging ---

    async def _log_live(self, message: str) -> None:
        """Appends to the execution log in memory and writes to the DB immediately."""
        self.log_output.append(message)
        current_log = self.spike.application_log or ''
        self.spike.application_log = current_log + message + '\n'
        await sync_to_async(self.spike.save)(update_fields=['application_log'])

    # --- Initialization ---

    def _get_rendered_objective(self, raw_context: Dict[str, Any]) -> str:
        raw_prompt = raw_context.get(
            FrontalLobeConstants.KEY_PROMPT,
            raw_context.get(
                FrontalLobeConstants.KEY_OBJECTIVE,
                FrontalLobeConstants.DEFAULT_PROMPT,
            ),
        )
        rendered_prompt = VariableRenderer.render_string(
            str(raw_prompt), raw_context
        )
        if not rendered_prompt.strip():
            rendered_prompt = f'{FrontalLobeConstants.DEFAULT_PROMPT} Context Head: {self.spike_id}'
        return rendered_prompt

    async def _initialize_session(
        self, rendered_objective: str, max_turns: int
    ) -> None:
        """Creates or resumes the ReasoningSession in the DB."""
        if not self.session:
            existing = await sync_to_async(
                lambda: (
                    ReasoningSession.objects.filter(
                        spike=self.spike,
                        status_id__in=[
                            ReasoningStatusID.ATTENTION_REQUIRED,
                            ReasoningStatusID.ACTIVE,
                        ],
                    )
                    .order_by('-created')
                    .first()
                )
            )()

            if existing:
                # Ensure it's active before proceeding
                if existing.status_id != ReasoningStatusID.ACTIVE:
                    existing.status_id = ReasoningStatusID.ACTIVE
                    await sync_to_async(existing.save)(
                        update_fields=['status_id']
                    )
                self.session = existing
            else:
                self.session = await sync_to_async(
                    ReasoningSession.objects.create
                )(
                    spike=self.spike,
                    status_id=ReasoningStatusID.ACTIVE,
                    max_turns=max_turns,
                )

        await self.cache_ids()
        await self._log_live(f'Session ID: {self.session.id}')

    async def cache_ids(self):
        # Cache the iteration ID so we don't query it every turn
        if self.session.participant_id:
            try:
                p = await sync_to_async(
                    IterationShiftParticipant.objects.select_related(
                        'iteration_shift',
                        'iteration_shift__shift',
                        'iteration_shift__shift_iteration__environment',
                    ).get
                )(id=self.session.participant_id)
                self._cached_iteration_id = p.iteration_shift.shift_iteration_id
                self._cached_environment_id = (
                    p.iteration_shift.shift_iteration.environment.id
                )
                self._cached_shift_id = p.iteration_shift.shift_id
            except IterationShiftParticipant.DoesNotExist:
                self._cached_iteration_id = None

    # --- Turn Execution ---

    async def _record_turn_start(
        self,
        turn_index: int,
        previous_turn: Optional[ReasoningTurn] = None,
    ) -> ReasoningTurn:
        turn = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=turn_index + 1,
            status_id=ReasoningStatusID.ACTIVE,
            last_turn=previous_turn,
        )
        return turn

    async def _build_turn_payload(
        self, turn_record: ReasoningTurn
    ) -> list[dict]:
        """
        Assembles the Turn payload by purely orchestrating Addons.
        """
        all_messages: list[ChatMessage] = []

        # 1. Build the unified context package
        package = AddonPackage(
            session_id=self.session.id,
            spike_id=self.spike.id,
            identity_disc=self.session.identity_disc.id
            if self.session.identity_disc
            else None,
            turn_number=turn_record.turn_number,
            reasoning_turn_id=turn_record.id,
            iteration=self._cached_iteration_id,
            environment_id=self._cached_environment_id,
            shift_id=self._cached_shift_id,
        )

        # 2. Fetch active addons ordered by Phase
        active_addons = await sync_to_async(list)(
            self.session.identity_disc.addons.select_related('phase').order_by(
                'phase__id'
            )
        )

        # 3. Execute addons and collect ChatMessage instances
        for addon_model in active_addons:
            # --- NATIVE TEXT INJECTION (No Python Function Required) ---
            if not addon_model.function_slug:
                if addon_model.description:
                    logger.debug(
                        f'Injecting native text addon: {addon_model.name}'
                    )
                    native_msg = ChatMessage(
                        session_id=self.session.id,
                        turn_id=turn_record.id,
                        role_id=ChatMessageRole.SYSTEM,
                        content=addon_model.description,
                        is_volatile=True,
                    )
                    all_messages.append(native_msg)
                continue

            # --- DYNAMIC PYTHON EXECUTION ---
            addon_func = ADDON_REGISTRY.get(addon_model.function_slug)
            if addon_func:
                logger.debug(f'Executing addon: {addon_model.function_slug}')
                addon_messages = await sync_to_async(addon_func)(package)
                if addon_messages:
                    all_messages.extend(addon_messages)
            else:
                logger.warning(
                    f'Addon {addon_model.function_slug} not found in registry.'
                )

        # 4. Bulk save ONLY the new, volatile messages (so they appear in your DB timeline)
        unsaved_volatile = [
            m for m in all_messages if m._state.adding and m.is_volatile
        ]
        if unsaved_volatile:
            for msg in unsaved_volatile:
                msg.session_id = self.session.id
                msg.turn_id = turn_record.id
            await sync_to_async(ChatMessage.objects.bulk_create)(
                unsaved_volatile
            )

            # 5. Translate the final sequence to LLM dictionaries
            llm_payload = await sync_to_async(_serialize_messages_sync)(
                turn_record, all_messages
            )

        # Logging output for debug
        await self._log_live(
            f'\n--- TURN {turn_record.turn_number} PAYLOAD ({len(llm_payload)} messages) ---'
        )
        for msg in llm_payload:
            content_str = msg.get(ChatMessage.CONTENT_KEY, '') or ''
            await self._log_live(
                f'[{msg.get(ChatMessage.ROLE_KEY)}] {content_str[:150]}...'
            )
        await self._log_live('------------------------\n')

        return llm_payload

    async def _execute_turn(
        self,
        turn_index: int,
        ollama_tools: list,
        previous_turn: Optional[ReasoningTurn],
    ) -> Tuple[bool, ReasoningTurn]:
        """
        Executes a single conversational turn with an 8-attempt hot-swap failover loop.
        """
        # 1. Start Turn
        turn_record = await self._record_turn_start(turn_index, previous_turn)

        # 2. Build Payload
        messages = await self._build_turn_payload(turn_record)
        tools = ollama_tools if ollama_tools else None

        # Rough token estimation for the context filter
        estimated_tokens = len(str(messages)) // 4

        MAX_FAILOVERS = 8
        response = None
        model_selection = None
        start_time = timezone.now()

        # THE HOT-SWAP LOOP
        for attempt in range(MAX_FAILOVERS):
            # Ask Hypothalamus for a brain
            model_selection = await sync_to_async(
                Hypothalamus().pick_optimal_model
            )(self.session.identity_disc, payload_size=estimated_tokens)

            if not model_selection:
                logger.error(
                    '[FrontalLobe] SWARM PARALYSIS: Hypothalamus returned NO valid models. All brains rate-limited or budget exhausted.'
                )
                raise Exception(
                    'No available AI models found in the routing pool.'
                )

            logger.info(
                f'[FrontalLobe] Attempt {attempt + 1}/{MAX_FAILOVERS}: Routing thought to {model_selection.provider_model_id}'
            )

            # Ensure we spin up a new SynapseClient inside the loop so it attaches to the new model
            synapse = await sync_to_async(SynapseClient)(model_selection)

            try:
                # Fire the Synapse
                response = await sync_to_async(synapse.chat)(
                    messages=messages, tools=tools
                )

                # Success! Break the loop immediately.
                break

            except (RateLimitError, APIConnectionError) as e:
                logger.warning(
                    f'[FrontalLobe] BRAIN REJECTED ({model_selection.provider_model_id}): {str(e)}'
                )

                if attempt == MAX_FAILOVERS - 1:
                    logger.error(
                        '[FrontalLobe] Critical Failure: Max failovers reached. Terminating Spike.'
                    )
                    raise e

                logger.info(
                    '[FrontalLobe] Circuit Breaker tripped. Hot-swapping to a new brain...'
                )
                continue  # Instantly restarts loop. Hypothalamus provides the NEXT best model.

            except Exception as e:
                # Catch logic errors (like bad JSON schemas) so we don't infinitely retry bad code
                logger.error(f'[FrontalLobe] Fatal Inference Error: {str(e)}')
                raise e

        # Calculate exact duration
        duration = timezone.now() - start_time

        # 3. Save to the ledger
        await _record_turn_completion(
            turn_record=turn_record,
            response=response,
            model_selection=model_selection,
            inference_duration=duration,
            identity_disc=self.session.identity_disc,
        )

        # 4. Save Assistant Message to History
        await sync_to_async(ChatMessage.objects.create)(
            session=self.session,
            turn=turn_record,
            role_id=ChatMessageRole.ASSISTANT,
            content=response.content or '',
        )

        if response.content:
            await self._log_live(
                f'[{model_selection.ai_model_name}] {response.content}'
            )

        # 5. Handle Tool Calls or Yield
        if response.tool_calls and self.parietal_lobe:
            await self._log_live(
                f'[ParietalLobe] Processing {len(response.tool_calls)} tool calls in parallel...'
            )

            # Serialize LiteLLM tool calls to raw dicts for the Parietal Lobe
            tool_calls_data = []
            for tc in response.tool_calls:
                if isinstance(tc, dict):
                    tool_calls_data.append(tc)
                elif hasattr(tc, 'model_dump'):
                    tool_calls_data.append(tc.model_dump())
                elif hasattr(tc, 'dict'):
                    tool_calls_data.append(tc.dict())
                else:
                    try:
                        tool_calls_data.append(dict(tc))
                    except (TypeError, ValueError):
                        continue

            # Call the ORIGINAL method signature from your working Parietal Lobe
            await self.parietal_lobe.process_tool_calls(
                turn_record=turn_record, tool_calls_data=tool_calls_data
            )
            return True, turn_record
        else:
            # AI didn't call tools, yield to user
            self.session.status_id = ReasoningStatusID.ATTENTION_REQUIRED
            await sync_to_async(self.session.save)(update_fields=[STATUS_ID])
            return False, turn_record

    async def run(self) -> Tuple[int, str]:
        """Main asynchronous execution orchestrator."""
        logger.debug(f'[FrontalLobe] Waking up for Spike {self.spike_id}')

        self.spike.application_log = ''
        await sync_to_async(self.spike.save)(update_fields=['application_log'])
        await self._log_live(FrontalLobeConstants.LOG_START)

        try:
            # 1. Resolve Environment & Objective
            raw_context = await sync_to_async(resolve_environment_context)(
                spike_id=self.spike.id
            )
            rendered_objective = self._get_rendered_objective(raw_context)

            # 2. Initialize DB Session
            max_turns = int(
                raw_context.get(
                    'max_turns', FrontalLobeConstants.DEFAULT_MAX_TURNS
                )
            )
            await self._initialize_session(rendered_objective, max_turns)

            # 3. Resolve IdentityDisc and prep Parietal Lobe
            identity_disc = await sync_to_async(_fetch_disc_sync)(
                self.session.id
            )
            if not identity_disc:
                raise ValueError(
                    f'Session {self.session.id} missing IdentityDisc.'
                )

            self.session.identity_disc = identity_disc
            self.parietal_lobe = ParietalLobe(self.session, self._log_live)

            # 4. Build Tool Schemas
            ollama_tools = await self.parietal_lobe.build_tool_schemas()
            await self._log_live(f'[[[[[Loaded {len(ollama_tools)} tools.]]]]]')

            # 5. The Loop
            previous_turn = None
            for turn in range(self.session.max_turns):
                await sync_to_async(self.spike.refresh_from_db)(
                    fields=['status']
                )
                if self.spike.status_id == SpikeStatus.STOPPING:
                    await self._log_live('\n[WARNING] Stop Signal. Halting.')
                    break

                should_continue, previous_turn = await self._execute_turn(
                    turn, ollama_tools, previous_turn
                )

                await sync_to_async(self.session.refresh_from_db)(
                    fields=[STATUS_ID]
                )
                if self.session.status_id != ReasoningStatusID.ACTIVE:
                    await self._log_live(
                        '\n[SYSTEM] Session halted by tool execution or intervention.'
                    )
                    break

                if not should_continue:
                    break

                if turn == self.session.max_turns - 1:
                    await self._log_live('\n[WARNING] Max turns reached.')
                    if self.session:
                        self.session.status_id = ReasoningStatusID.MAXED_OUT
                        await sync_to_async(self.session.save)()

            if self.session:
                await sync_to_async(self.session.refresh_from_db)(
                    fields=[STATUS_ID]
                )
                if self.session.status_id == ReasoningStatusID.ACTIVE:
                    self.session.status_id = ReasoningStatusID.COMPLETED
                    await sync_to_async(self.session.save)(
                        update_fields=[STATUS_ID]
                    )

        except Exception as e:
            logger.exception(f'[FrontalLobe] Crash: {e}')
            await self._log_live(f'\n[CRITICAL ERROR]: {str(e)}')
            if self.session:
                self.session.status_id = ReasoningStatusID.ERROR
                await sync_to_async(self.session.save)()
            return 500, '\n'.join(self.log_output)

        finally:
            await self._log_live('\n[SYSTEM] Requesting VRAM cleanup...')
            if self.parietal_lobe:
                await self.parietal_lobe.unload_client()
            await self._log_live(FrontalLobeConstants.LOG_END)

        return 200, '\n'.join(self.log_output)


async def run_frontal_lobe(spike_id: UUID) -> Tuple[int, str]:
    try:
        spike = await sync_to_async(
            lambda: Spike.objects.select_related('spike_train').get(id=spike_id)
        )()
        lobe = FrontalLobe(spike)
        return await lobe.run()
    except Exception as e:
        logger.exception(f'[FrontalLobe] Fatal crash on init: {e}')
        return 500, f'Fatal Error: {str(e)}'


async def _record_turn_completion(
    turn_record: ReasoningTurn,
    response: SynapseResponse,
    model_selection: ModelSelection,
    inference_duration: timedelta,
    identity_disc: 'IdentityDisc',
) -> None:
    # 1. Update Turn
    turn_record.tokens_input = response.tokens_input
    turn_record.tokens_output = response.tokens_output
    turn_record.inference_time = inference_duration
    turn_record.status_id = ReasoningStatusID.COMPLETED
    turn_record.request_payload = response.request_payload
    turn_record.response_payload = response.response_payload
    await sync_to_async(turn_record.save)()

    # 2. Calculate the estimated cost based on the Selection
    estimated_cost = (
        Decimal(response.tokens_input) * model_selection.input_cost_per_token
    )

    # 3. Mint Usage Record
    await sync_to_async(_mint_usage_record_sync)(
        turn_record,
        identity_disc,
        model_selection,
        response,
        estimated_cost,
        inference_duration,
    )


def chat_message_to_llm_dict(
    chat_message: ChatMessage, current_turn: Optional[int] = None
) -> dict:
    role_map = dict(ChatMessageRole.ROLE_CHOICES)
    role_name = role_map.get(chat_message.role_id, ChatMessageRole.USER_NAME)

    payload = {
        chat_message.ROLE_KEY: role_name,
        chat_message.CONTENT_KEY: chat_message.content,
    }

    if (
        chat_message.role_id == ChatMessageRole.TOOL
        and chat_message.tool_call_id
    ):
        if chat_message.tool_call and getattr(
            chat_message.tool_call, chat_message.TOOL_KEY, None
        ):
            payload[chat_message.NAME_KEY] = chat_message.tool_call.tool.name
        payload[chat_message.TOOL_CALL_ID_KEY] = (
            f'call_{chat_message.tool_call_id}'
        )

    elif chat_message.role_id == ChatMessageRole.ASSISTANT:
        tool_calls_payload = []
        for tc in chat_message.turn.tool_calls.all():
            raw_args = tc.arguments or '{}'
            parsed_args = (
                json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            )
            if current_turn:
                age = current_turn - chat_message.turn.turn_number
                for assignment in tc.tool.assignments.all():
                    if (
                        assignment.prune_after_turns
                        and age >= assignment.prune_after_turns
                    ):
                        param_name = assignment.parameter.name
                        if param_name in parsed_args:
                            parsed_args[param_name] = '[PRUNED TO SAVE TOKENS]'
            llm_tc = LLMToolCall(
                id=f'call_{tc.id}',
                function=LLMFunctionCall(
                    name=tc.tool.name, arguments=json.dumps(parsed_args)
                ),
            )
            tool_calls_payload.append(llm_tc.to_dict())

        if tool_calls_payload:
            payload[chat_message.TOOL_CALLS_KEY] = tool_calls_payload

    return payload
