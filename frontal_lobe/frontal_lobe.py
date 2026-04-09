import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async
from django.utils import timezone
from litellm.exceptions import APIConnectionError, NotFoundError, RateLimitError

from central_nervous_system.models import Spike, SpikeStatus
from central_nervous_system.utils import resolve_environment_context
from common.constants import CONTENT, HUMAN_TAG, ROLE, USER
from environments.variable_renderer import VariableRenderer
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from frontal_lobe.synapse_client import (
    SynapseClient,
    recover_tool_calls_from_content,
)
from hypothalamus.hypothalamus import Hypothalamus
from hypothalamus.models import AIModelProviderUsageRecord
from identity.addons.addon_registry import ADDON_REGISTRY
from parietal_lobe.parietal_lobe import ParietalLobe
from temporal_lobe.models import IterationShiftParticipant

logger = logging.getLogger(__name__)

STATUS_ID = 'status_id'
MODEL_USAGE_RECORD = 'model_usage_record'


def _fetch_disc_sync(session_id):
    s = ReasoningSession.objects.select_related('identity_disc').get(
        id=session_id
    )
    return s.identity_disc


def compile_system_messages(messages: list[dict]) -> list[dict]:
    """
    Extracts all 'system' messages, concatenates their content into a single
    master prompt, and hoists it to index 0. Preserves chronological order
    for all 'user', 'assistant', and 'tool' messages.
    """
    system_blocks = []
    chat_history = []

    for msg in messages:
        if msg.get('role') == 'system':
            content = msg.get('content')
            if content:
                system_blocks.append(str(content).strip())
        else:
            chat_history.append(msg)

    # If there are no system messages, just return the history untouched
    if not system_blocks:
        return chat_history

    # Join all system instructions with a clean divider
    master_system_prompt = '\n\n---\n\n'.join(system_blocks)

    # Return the unified system prompt exactly at index 0
    return [{'role': 'system', 'content': master_system_prompt}] + chat_history


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
        logger.info(message)

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
        self, raw_context: Dict[str, Any], rendered_objective: str, max_turns: int
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
                # Extract identity_disc from context (spike blackboard, neuron context, or effector context)
                identity_disc_id = None
                identity_disc_value = raw_context.get('identity_disc')
                if identity_disc_value:
                    # If it's already a UUID, use it; otherwise convert string to UUID
                    try:
                        identity_disc_id = (
                            identity_disc_value
                            if isinstance(identity_disc_value, UUID)
                            else UUID(str(identity_disc_value))
                        )
                    except (ValueError, TypeError):
                        logger.warning(
                            f'[FrontalLobe] Invalid identity_disc value: {identity_disc_value}'
                        )

                self.session = await sync_to_async(
                    ReasoningSession.objects.create
                )(
                    spike=self.spike,
                    status_id=ReasoningStatusID.ACTIVE,
                    max_turns=max_turns,
                    identity_disc_id=identity_disc_id,
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
        (Base history is fetched entirely by the History-phase Addons to prevent Double Vision).
        """
        all_messages: list[dict] = []

        active_addons = await sync_to_async(list)(
            self.session.identity_disc.addons.select_related('phase').order_by(
                'phase__id'
            )
        )

        for addon_model in active_addons:
            if not addon_model.function_slug:
                if addon_model.description:
                    logger.debug(
                        f'Injecting native text addon: {addon_model.name}'
                    )
                    all_messages.append(
                        {'role': 'system', 'content': addon_model.description}
                    )
                continue

            addon_func = ADDON_REGISTRY.get(addon_model.function_slug)
            if addon_func:
                logger.debug(f'Executing addon: {addon_model.function_slug}')
                addon_messages = await sync_to_async(addon_func)(turn_record)
                if addon_messages:
                    all_messages.extend(addon_messages)
            else:
                logger.warning(
                    f'Addon {addon_model.function_slug} not found in registry.'
                )

        if self.session.swarm_message_queue:
            # Tag human messages with <<h>> so river_of_six replays them.
            # Addon-injected user messages have no tag and get skipped
            # on history reconstruction (the addon re-injects fresh).
            for msg in self.session.swarm_message_queue:
                if msg.get(ROLE) == USER and msg.get(CONTENT):
                    msg[CONTENT] = HUMAN_TAG + '\n' + msg[CONTENT]
            all_messages.extend(self.session.swarm_message_queue)
            self.session.swarm_message_queue = []
            await sync_to_async(self.session.save)(
                update_fields=['swarm_message_queue']
            )

        llm_payload = compile_system_messages(all_messages)

        await self._log_live(
            f'\n--- TURN {turn_record.turn_number} PAYLOAD ({len(llm_payload)} messages) ---'
        )
        for msg in llm_payload:
            content_str = str(msg.get('content', ''))
            await self._log_live(f'[{msg.get("role")}] {content_str[:150]}...')
        await self._log_live('------------------------\n')

        return llm_payload

    async def _execute_turn(
        self,
        ollama_tools: list,
        previous_turn: Optional[ReasoningTurn],
    ) -> Tuple[bool, ReasoningTurn]:

        # Check for an active turn created by the API, otherwise create the next chronological turn
        turn_record = await sync_to_async(
            lambda: self.session.turns.filter(
                status_id=ReasoningStatusID.ACTIVE
            ).first()
        )()

        if not turn_record:
            current_count = await sync_to_async(self.session.turns.count)()
            turn_record = await self._record_turn_start(
                current_count, previous_turn
            )

        messages = await self._build_turn_payload(turn_record)
        tools = ollama_tools if ollama_tools else {}

        # 🛒 1. BUILD THE PENDING LEDGER
        pending_ledger = AIModelProviderUsageRecord(
            identity_disc=self.session.identity_disc,
            request_payload=messages,
            tool_payload=tools,
        )

        MAX_FAILOVERS = 8
        tool_calls_data = []
        start_time = timezone.now()

        for attempt in range(MAX_FAILOVERS):
            # 🧠 2. PASS THE LEDGER TO THE HYPOTHALAMUS
            routing_success = await sync_to_async(
                Hypothalamus().pick_optimal_model
            )(pending_ledger, attempt=attempt)

            # TODO: Save the ledger here.

            if not routing_success or not pending_ledger.ai_model_provider:
                logger.error(
                    '[FrontalLobe] SWARM PARALYSIS: Hypothalamus returned '
                    'NO valid models for session %s, turn %s.',
                    self.session.id,
                    turn_record.turn_number,
                )
                self.session.status_id = ReasoningStatusID.MAXED_OUT
                await sync_to_async(self.session.save)(
                    update_fields=[STATUS_ID]
                )
                turn_record.status_id = ReasoningStatusID.ERROR
                await sync_to_async(turn_record.save)(
                    update_fields=[STATUS_ID]
                )
                return False, turn_record

            # ⚡ 3. PASS THE LEDGER TO THE SYNAPSE
            synapse = await sync_to_async(SynapseClient)(pending_ledger)

            # TODO: Save the ledger here. maybe new status?

            try:
                # chat() mutates the ledger, returns normalized tool calls
                success, tool_calls_data = await sync_to_async(synapse.chat)()
                if success:
                    break  # Success! escape loop!

            except (RateLimitError, APIConnectionError, NotFoundError) as e:
                provider_id = (
                    pending_ledger.ai_model_provider.provider_unique_model_id
                )
                # TODO: we should consider minting an error log for this.
                logger.warning(
                    f'[FrontalLobe] BRAIN REJECTED ({provider_id}): {str(e)}'
                )
                if attempt == MAX_FAILOVERS - 1:
                    raise e
                continue

        duration = timezone.now() - start_time

        # 💳 4. CHECKOUT (File the Form)
        pending_ledger.query_time = duration
        if pending_ledger.input_tokens and pending_ledger.input_cost_per_token:
            pending_ledger.estimated_cost = (
                Decimal(pending_ledger.input_tokens)
                * pending_ledger.input_cost_per_token
            )
        else:
            pending_ledger.estimated_cost = Decimal(0)

        await sync_to_async(pending_ledger.save)()

        # 5. Update and Save the Turn Record
        turn_record.status_id = ReasoningStatusID.COMPLETED
        turn_record.model_usage_record = pending_ledger
        await sync_to_async(turn_record.save)(
            update_fields=[STATUS_ID, MODEL_USAGE_RECORD]
        )

        # 6. Logging and Tool Execution
        res_payload = pending_ledger.response_payload or {}
        content = ''
        if isinstance(res_payload, dict):
            content = (
                res_payload.get('choices', [{}])[0]
                .get('message', {})
                .get('content', '')
            )

        if content:
            await self._log_live(
                f'[{pending_ledger.ai_model.name}] {content}'
            )

        # Recovery: model emitted tool calls as text content
        if not tool_calls_data and content:
            tool_calls_data = recover_tool_calls_from_content(content)

        if tool_calls_data and self.parietal_lobe:
            await self._log_live(
                f'[ParietalLobe] Processing {len(tool_calls_data)} tool calls...'
            )
            await self.parietal_lobe.process_tool_calls(
                turn_record=turn_record, tool_calls_data=tool_calls_data
            )
            await sync_to_async(self.session.refresh_from_db)(
                fields=[STATUS_ID]
            )
            should_continue = self.session.status_id == ReasoningStatusID.ACTIVE
            return should_continue, turn_record

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
            await self._initialize_session(raw_context, rendered_objective, max_turns)

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
            previous_turn = await sync_to_async(
                lambda: (
                    self.session.turns.exclude(
                        status_id=ReasoningStatusID.ACTIVE
                    )
                    .order_by('-turn_number')
                    .first()
                )
            )()

            while True:
                current_turn_count = await sync_to_async(
                    self.session.turns.count
                )()
                if current_turn_count >= self.session.max_turns:
                    await self._log_live('\n[WARNING] Max turns reached.')
                    break

                await sync_to_async(self.spike.refresh_from_db)(
                    fields=['status']
                )
                if self.spike.status_id == SpikeStatus.STOPPING:
                    await self._log_live('\n[WARNING] Stop Signal. Halting.')
                    break

                # The clean, 2-argument call
                should_continue, previous_turn = await self._execute_turn(
                    ollama_tools, previous_turn
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
