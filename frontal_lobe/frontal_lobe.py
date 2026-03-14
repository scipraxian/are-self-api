import json
import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async

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
from frontal_lobe.thalamus import relay_sensory_state
from identity.identity_prompt import build_identity_prompt, collect_addon_blocks
from parietal_lobe.parietal_lobe import ParietalLobe

logger = logging.getLogger(__name__)

STATUS_ID = 'status_id'
ROLE = 'role'
CONTENT = 'content'


class FrontalLobe:
    """Async execution wrapper for the Frontal Lobe AI loop."""

    def __init__(self, spike: Spike):
        self.spike = spike
        self.spike_id = spike.id
        self.log_output: List[str] = []
        self.parietal_lobe: Optional[ParietalLobe] = None

        self.session: Optional[ReasoningSession] = None

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
        """Creates the ReasoningSession in the DB."""
        if not self.session:
            self.session = await sync_to_async(ReasoningSession.objects.create)(
                spike=self.spike,
                status_id=ReasoningStatusID.ACTIVE,
                max_turns=max_turns,
            )
        await self._log_live(f'Session ID: {self.session.id}')

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

    async def _record_turn_completion(
        self,
        turn_record: ReasoningTurn,
        tokens_in: int,
        tokens_out: int,
        inference_duration: timedelta,
    ) -> None:
        turn_record.tokens_input = tokens_in
        turn_record.tokens_output = tokens_out
        turn_record.inference_time = inference_duration
        turn_record.status_id = ReasoningStatusID.COMPLETED
        await sync_to_async(turn_record.save)()

    def _get_identity_prompt(self, turn_record: ReasoningTurn):
        iteration_id = None
        if self.session.participant_id:
            from temporal_lobe.models import IterationShiftParticipant

            try:
                p = IterationShiftParticipant.objects.select_related(
                    'iteration_shift'
                ).get(id=self.session.participant_id)
                iteration_id = p.iteration_shift.shift_iteration_id
            except IterationShiftParticipant.DoesNotExist:
                pass

        return build_identity_prompt(
            identity_disc=self.session.identity_disc,
            iteration_id=iteration_id,
            turn_number=turn_record.turn_number,
            reasoning_turn_id=turn_record.id,
        )

    async def _build_history_messages(
        self, turn_record: ReasoningTurn
    ) -> List[Dict[str, Any]]:
        """
        Rebuilds the recent conversational history from native ChatMessage records.
        L1 (Previous 2 turns): Full data.
        L2 (Turns 3-6 prior): Truncated tool data.
        """
        if not self.session:
            return []

        current_turn_num = turn_record.turn_number
        cutoff_turn = max(1, current_turn_num - 6)

        # Retrieve strictly non-volatile messages from the last 6 turns, ordered chronologically
        history_qs = await sync_to_async(list)(
            ChatMessage.objects.filter(
                session=self.session,
                turn__turn_number__gte=cutoff_turn,
                turn__turn_number__lt=current_turn_num,
                is_volatile=False,
            )
            .select_related('turn', 'role', 'tool_call__tool')
            .prefetch_related('turn__tool_calls__tool')  # <-- ADD THIS PREFETCH
            .order_by('created')
        )

        messages_for_llm = []

        for msg in history_qs:
            role_name = 'system'
            if msg.role_id == ChatMessageRole.USER:
                role_name = 'user'
            elif msg.role_id == ChatMessageRole.ASSISTANT:
                role_name = 'assistant'
            elif msg.role_id == ChatMessageRole.TOOL:
                role_name = 'tool'

            content = msg.content
            message_dict: Dict[str, Any] = {ROLE: role_name}

            # 2. FIX ASSISTANT FORMATTING
            if msg.role_id == ChatMessageRole.ASSISTANT:
                # Look at the TURN's tool calls, not the message's tool call ID
                tool_calls_payload = []
                for tc in msg.turn.tool_calls.all():
                    raw_args = tc.arguments or '{}'
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            parsed_args = {}
                    elif isinstance(raw_args, dict):
                        parsed_args = raw_args
                    else:
                        parsed_args = {}

                    tool_calls_payload.append(
                        {
                            'id': f'call_{tc.id}',
                            'type': 'function',
                            'function': {
                                'name': tc.tool.name,
                                'arguments': parsed_args,
                            },
                        }
                    )

                if tool_calls_payload:
                    message_dict['tool_calls'] = tool_calls_payload

            # Handle Tool Results formatting & L2 Eviction logic (Unchanged, this was correct)
            elif msg.role_id == ChatMessageRole.TOOL:
                age = current_turn_num - msg.turn.turn_number

                # L2 Eviction: If older than 2 turns, strip the heavy data
                if age > 2:
                    content = '[DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]'
                elif age == 2:
                    content += '\n\n[SYSTEM WARNING: L1 EVICTION IMMINENT. FLUSH TO ENGRAMS.]'

                if msg.tool_call_id:
                    message_dict['name'] = msg.tool_call.tool.name

            message_dict[CONTENT] = content
            messages_for_llm.append(message_dict)

        return messages_for_llm

    async def _inject_addons(self, turn_record: ReasoningTurn) -> None:
        """
        Executes Identity Addons for the current turn and saves them directly
        to the database as Volatile user messages.
        """
        if not self.session or not self.session.identity_disc:
            return

        iteration_id = None
        if self.session.participant_id:
            from temporal_lobe.models import IterationShiftParticipant

            def _get_iteration_id() -> Optional[int]:
                try:
                    p = IterationShiftParticipant.objects.select_related(
                        'iteration_shift'
                    ).get(id=self.session.participant_id)
                    return p.iteration_shift.shift_iteration_id
                except IterationShiftParticipant.DoesNotExist:
                    return None

            iteration_id = await sync_to_async(_get_iteration_id)()

        addon_blocks = await sync_to_async(collect_addon_blocks)(
            identity_disc=self.session.identity_disc,
            iteration_id=iteration_id,
            turn_number=turn_record.turn_number,
            reasoning_turn_id=turn_record.id,
        )

        for addon_name, addon_text in addon_blocks:
            await sync_to_async(ChatMessage.objects.create)(
                session=self.session,
                turn=turn_record,
                role_id=ChatMessageRole.USER,
                content=f'[{addon_name.upper()} ADDON]:\n{addon_text}',
                is_volatile=True,
            )

    async def _build_turn_payload(
        self, turn_record: ReasoningTurn
    ) -> list[dict]:
        """
        Assembles the Turn payload as a Living Chatroom array.
        Fetches the static core, historical context, and volatile context from the DB.
        """
        messages: List[Dict[str, Any]] = []

        # Phase 1: Immutable laws (System Prompt)
        system_instruction = await sync_to_async(self._get_identity_prompt)(
            turn_record
        )
        messages.append(
            {
                ROLE: 'system',
                CONTENT: system_instruction,
            }
        )

        # Phase 2: Timeline reconstruction (L1/L2 cache from DB)
        history_messages = await self._build_history_messages(turn_record)
        messages.extend(history_messages)

        # Phase 3: Living chatroom (Fetch the Volatile Addons we just created for this turn)
        current_turn_volatile_qs = await sync_to_async(list)(
            ChatMessage.objects.filter(
                turn=turn_record, is_volatile=True
            ).order_by('created')
        )
        for volatile_msg in current_turn_volatile_qs:
            messages.append({ROLE: 'user', CONTENT: volatile_msg.content})

        # Phase 4: Final sensory trigger for this turn (Saved as volatile)
        sensory_trigger = await relay_sensory_state(turn_record)
        await sync_to_async(ChatMessage.objects.create)(
            session=self.session,
            turn=turn_record,
            role_id=ChatMessageRole.USER,
            content=sensory_trigger,
            is_volatile=True,
        )
        messages.append(
            {
                ROLE: 'user',
                CONTENT: sensory_trigger,
            }
        )

        # Logging output for debug
        await self._log_live(
            f'\n--- TURN {turn_record.turn_number} PAYLOAD ({len(messages)} messages) ---'
        )
        for msg in messages:
            content_str = msg.get(CONTENT, '') or ''
            await self._log_live(f'[{msg.get(ROLE)}] {content_str[:500]}')
        await self._log_live('------------------------\n')

        return messages

    async def _execute_turn(
        self,
        turn_index: int,
        ollama_tools: List[Dict[str, Any]],
        previous_turn: Optional[ReasoningTurn] = None,
    ) -> Tuple[bool, Optional[ReasoningTurn]]:
        await self._log_live(f'\n--- Turn {turn_index + 1} (Awakening) ---')

        # 1. Start the turn record
        turn_record = await self._record_turn_start(turn_index, previous_turn)

        # 2. Trigger the RPG progression logic (The Ding!)
        await sync_to_async(turn_record.apply_efficiency_bonus)()

        # 3. Inject Volatile Context (Addons & Sensory triggers) directly into DB for this turn
        await self._inject_addons(turn_record)

        # 4. Build the context window for the LLM
        messages = await self._build_turn_payload(turn_record)

        turn_record.request_payload = {'messages': messages}
        await sync_to_async(turn_record.save)(update_fields=['request_payload'])

        # 5. Execute Inference
        start_time = time.time()
        response = await self.parietal_lobe.chat(messages, ollama_tools)
        inf_duration = timedelta(seconds=time.time() - start_time)

        # 6. Save AI Response to ChatMessage (Persistent)
        if response.content:
            await sync_to_async(ChatMessage.objects.create)(
                session=self.session,
                turn=turn_record,
                role_id=ChatMessageRole.ASSISTANT,
                content=response.content.strip(),
                is_volatile=False,
            )
            await self._log_live(f'Thought: {response.content.strip()}')

        # Note: Tool execution will happen in ParietalLobe, and those results
        # MUST be saved as ChatMessage objects with role=TOOL and is_volatile=False
        # inside process_tool_calls() to ensure they enter the history properly.

        await self._record_turn_completion(
            turn_record,
            response.tokens_input,
            response.tokens_output,
            inf_duration,
        )

        if not response.tool_calls:
            await self._log_live(
                '\nNo further actions requested. Permanent Sleep Initiated.'
            )
            return False, turn_record

        # 7. Fire Tools
        # Ensure parietal_lobe.process_tool_calls is updated to save ChatMessages!
        await self.parietal_lobe.process_tool_calls(
            turn_record, response.tool_calls
        )

        return True, turn_record

    async def run(self) -> Tuple[int, str]:
        """Main asynchronous execution orchestrator."""
        logger.info(f'[FrontalLobe] Waking up for Spike {self.spike_id}')

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

            # 3. Resolve model from IdentityDisc and initialize Parietal Lobe
            identity_disc = self.session.identity_disc
            ai_model = (
                await sync_to_async(getattr)(identity_disc, 'ai_model', None)
                if identity_disc
                else None
            )
            if not identity_disc or not ai_model:
                raise ValueError(
                    'ReasoningSession.identity_disc.ai_model must be set before FrontalLobe.run().'
                )

            self.parietal_lobe = ParietalLobe(self.session, self._log_live)
            await self.parietal_lobe.initialize_client(identity_disc)
            await self._log_live(f'Model: {ai_model.name}')

            # 4. Build Synapse Payload
            ollama_tools = await self.parietal_lobe.build_tool_schemas()
            await self._log_live(f'Loaded {len(ollama_tools)} tools.')

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
            await self._log_live('\n[SYSTEM] Unloading model to free VRAM...')
            if self.parietal_lobe:
                await self.parietal_lobe.unload_client()
            await self._log_live(FrontalLobeConstants.LOG_END)

        return 200, '\n'.join(self.log_output)


async def run_frontal_lobe(spike_id: UUID) -> Tuple[int, str]:
    """Asynchronous entry point for the generic effector caster.

    # Used by GEC.
    """
    try:
        spike = await sync_to_async(
            lambda: Spike.objects.select_related('spike_train').get(id=spike_id)
        )()
        lobe = FrontalLobe(spike)
        return await lobe.run()
    except Exception as e:
        logger.exception(f'[FrontalLobe] Fatal crash on init: {e}')
        return 500, f'Fatal Error: {str(e)}'
