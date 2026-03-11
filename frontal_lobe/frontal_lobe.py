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
    ModelRegistry,
    ReasoningGoal,
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
        self.current_goal: Optional[ReasoningGoal] = None

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
        """Creates the ReasoningSession and primary ReasoningGoal in the DB."""
        if not self.session:
            self.session = await sync_to_async(ReasoningSession.objects.create)(
                spike=self.spike,
                status_id=ReasoningStatusID.ACTIVE,
                max_turns=max_turns,
            )
        self.current_goal = await sync_to_async(ReasoningGoal.objects.create)(
            session=self.session,
            rendered_goal=rendered_objective,
            status_id=ReasoningStatusID.ACTIVE,
        )
        await self._log_live(f'Session ID: {self.session.id}')

    # --- Turn Execution ---

    async def _record_turn_start(
        self,
        turn_index: int,
        payload_dict: dict,
        previous_turn: Optional[ReasoningTurn] = None,
    ) -> ReasoningTurn:
        turn = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=turn_index + 1,
            request_payload=payload_dict,
            status_id=ReasoningStatusID.ACTIVE,
            last_turn=previous_turn,
        )
        if self.current_goal:
            await sync_to_async(turn.turn_goals.add)(self.current_goal)
        return turn

    async def _record_turn_completion(
        self,
        turn_record: ReasoningTurn,
        thought_process: str,
        tokens_in: int,
        tokens_out: int,
        inference_duration: timedelta,
    ) -> None:
        turn_record.thought_process = thought_process
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
        Rebuilds the recent conversational history as native chat messages.

        For each of the last ~6 completed ReasoningTurns, we append:
        - The historical user messages that the model saw on that turn.
        - The assistant message containing the stored thought_process and a
          native-style tool_calls array.
        - Tool messages that surface the cached (or evicted) tool results,
          applying L1/L2 cache eviction rules based on turn age.
        """
        if not self.session:
            return []

        session = self.session
        current_turn = turn_record.turn_number

        recent_turns: List[ReasoningTurn] = await sync_to_async(list)(
            session.turns.filter(
                status_id=ReasoningStatusID.COMPLETED,
                turn_number__lt=current_turn,
            ).order_by('-turn_number')[:6]
        )
        recent_turns.reverse()

        messages: List[Dict[str, Any]] = []

        for t in recent_turns:
            # 1. Historical user messages (what the model saw on that turn)
            payload = t.request_payload or {}
            user_contents: List[str] = []

            if isinstance(payload, dict):
                raw_messages = payload.get('messages') or []
                for msg in raw_messages:
                    if (
                        isinstance(msg, dict)
                        and msg.get('role') == FrontalLobeConstants.ROLE_USER
                    ):
                        content = msg.get('content')
                        if content:
                            user_contents.append(str(content))

            # Fallback for legacy turns that might not have structured messages
            if not user_contents:
                if t.thought_process:
                    user_contents.append(
                        f'[LEGACY CONTEXT SNAPSHOT] User context for turn {t.turn_number} was not stored as messages.'
                    )

            for content in user_contents:
                messages.append(
                    {
                        ROLE: FrontalLobeConstants.ROLE_USER,
                        CONTENT: content,
                    }
                )

            # 2. Assistant message with thought_process and native-style tool_calls
            tool_calls = await sync_to_async(list)(
                t.tool_calls.select_related('tool').all()
            )
            tool_calls_payload: List[Dict[str, Any]] = []
            for tc in tool_calls:
                func_payload: Dict[str, Any] = {
                    'name': tc.tool.name,
                    'arguments': tc.arguments or '{}',
                }
                tool_calls_payload.append(
                    {
                        'id': f'call_{tc.id}',
                        'type': 'function',
                        'function': func_payload,
                    }
                )

            assistant_message: Dict[str, Any] = {
                ROLE: FrontalLobeConstants.ROLE_ASSISTANT,
                CONTENT: t.thought_process or '',
            }
            if tool_calls_payload:
                assistant_message['tool_calls'] = tool_calls_payload
            messages.append(assistant_message)

            # 3. Tool result messages with L1/L2 cache eviction applied
            age = current_turn - t.turn_number
            for tc in tool_calls:
                if age <= 3:
                    result_content = tc.result_payload or ''
                    if age == 3:
                        result_content += (
                            '\n\n[SYSTEM WARNING: L1 EVICTION IMMINENT. '
                            'FLUSH TO ENGRAMS.]'
                        )
                else:
                    result_content = (
                        '[DATA EVICTED FROM L1 CACHE. '
                        'REQUIRES ENGRAM RETRIEVAL.]'
                    )

                messages.append(
                    {
                        ROLE: FrontalLobeConstants.ROLE_TOOL,
                        CONTENT: result_content,
                        'name': tc.tool.name,
                    }
                )

        return messages

    async def _build_addon_messages(
        self, turn_record: ReasoningTurn
    ) -> List[Dict[str, Any]]:
        """
        Executes Identity Addons for the current turn and emits one user
        message per addon, with the addon name baked into the content.
        """
        if not self.session or not self.session.identity_disc:
            return []

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

        addon_blocks = await sync_to_async(collect_addon_blocks)(
            identity_disc=self.session.identity_disc,
            iteration_id=iteration_id,
            turn_number=turn_record.turn_number,
            reasoning_turn_id=turn_record.id,
        )

        messages: List[Dict[str, Any]] = []
        for addon_name, addon_text in addon_blocks:
            prefix = f'[{addon_name.upper()} ADDON]: '
            messages.append(
                {
                    ROLE: FrontalLobeConstants.ROLE_USER,
                    CONTENT: f'{prefix}{addon_text}',
                }
            )

        return messages

    async def _build_turn_payload(
        self, turn_record: ReasoningTurn
    ) -> list[dict]:
        """
        Assembles the Turn payload as a Living Chatroom array.

        Phases:
        1. Immutable laws (system prompt from IdentityDisc + Focus/Cache rules).
        2. Timeline reconstruction (last ~6 ReasoningTurns with tool_calls + L1/L2 cache).
        3. Living chatroom (current-turn Addons as individual user messages).
        4. Final sensory trigger (Thalamus) for this turn.
        """

        system_instruction = await sync_to_async(self._get_identity_prompt)(
            turn_record
        )

        history_messages = await self._build_history_messages(turn_record)
        addon_messages = await self._build_addon_messages(turn_record)
        sensory_trigger = await relay_sensory_state(turn_record)

        messages: List[Dict[str, Any]] = []

        # Phase 1: Immutable laws
        messages.append(
            {
                ROLE: FrontalLobeConstants.ROLE_SYSTEM,
                CONTENT: system_instruction,
            }
        )

        # Phase 2: Reconstructed history with L1/L2 cache semantics
        messages.extend(history_messages)

        # Phase 3: Addons as first-class chatroom participants
        messages.extend(addon_messages)

        # Phase 4: Final sensory trigger for this turn
        messages.append(
            {
                ROLE: FrontalLobeConstants.ROLE_USER,
                CONTENT: sensory_trigger,
            }
        )

        await self._log_live(
            f'\n--- TURN {turn_record.turn_number} PAYLOAD ({len(messages)} messages) ---'
        )
        for msg in messages:
            await self._log_live(f"[{msg.get(ROLE)}] {msg.get(CONTENT)[:500]}")
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
        turn_record = await self._record_turn_start(
            turn_index, {}, previous_turn
        )

        # 2. Trigger the RPG progression logic (The Ding!)
        # The variables returned are no longer needed here, as the Thalamus derives them natively.
        await sync_to_async(turn_record.apply_efficiency_bonus)()

        # 3. Build the entire context window from scratch
        messages = await self._build_turn_payload(turn_record)

        turn_record.request_payload = dict(messages=messages)
        await sync_to_async(turn_record.save)(update_fields=['request_payload'])

        # 4. Execute Inference
        start_time = time.time()
        response = await self.parietal_lobe.chat(messages, ollama_tools)
        inf_duration = timedelta(seconds=time.time() - start_time)

        await self._record_turn_completion(
            turn_record,
            response.content or '',
            response.tokens_input,
            response.tokens_output,
            inf_duration,
        )

        if response.content:
            await self._log_live(f'Thought: {response.content.strip()}')

        if not response.tool_calls:
            await self._log_live(
                '\nNo further actions requested. Permanent Sleep Initiated.'
            )
            return False, turn_record

        # 5. Fire Tools
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
            # 1. Resolve Environment & Model
            raw_context = await sync_to_async(resolve_environment_context)(
                spike_id=self.spike.id
            )
            target_id = int(
                raw_context.get(
                    FrontalLobeConstants.MODEL_ID_KEY,
                    ModelRegistry.DEFAULT_MODEL_ID,
                )
            )

            try:
                model_entry = await sync_to_async(ModelRegistry.objects.get)(
                    id=target_id
                )
                model_name = model_entry.name
            except ModelRegistry.DoesNotExist:
                logger.warning(
                    f'Model ID {target_id} not found. Reverting to Default.'
                )
                model_entry = await sync_to_async(ModelRegistry.objects.get)(
                    id=ModelRegistry.DEFAULT_MODEL_ID
                )
                model_name = model_entry.name

            rendered_objective = self._get_rendered_objective(raw_context)

            # 2. Initialize DB Session
            max_turns = int(
                raw_context.get(
                    'max_turns', FrontalLobeConstants.DEFAULT_MAX_TURNS
                )
            )
            await self._initialize_session(rendered_objective, max_turns)

            # 3. Initialize Parietal Lobe
            self.parietal_lobe = ParietalLobe(self.session, self._log_live)
            await self.parietal_lobe.initialize_client(model_name)
            await self._log_live(f'Model: {model_name}')

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
