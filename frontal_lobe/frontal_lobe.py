import asyncio
import json
import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async

from environments.variable_renderer import VariableRenderer
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import (
    ModelRegistry,
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from hydra.models import HydraHead, HydraHeadStatus
from hydra.utils import resolve_environment_context
from talos_parietal.parietal_lobe import ParietalLobe

logger = logging.getLogger(__name__)


class FrontalLobe:
    """Async execution wrapper for the Frontal Lobe AI loop."""

    def __init__(self, head: HydraHead):
        self.head = head
        self.head_id = head.id
        self.log_output: List[str] = []
        self.parietal_lobe: Optional[ParietalLobe] = None

        self.session: Optional[ReasoningSession] = None
        self.current_goal: Optional[ReasoningGoal] = None

    # --- IO & Logging ---

    async def _log_live(self, message: str) -> None:
        """Appends to the execution log in memory and writes to the DB immediately."""
        self.log_output.append(message)
        current_log = self.head.application_log or ''
        self.head.application_log = current_log + message + '\n'
        await sync_to_async(self.head.save)(update_fields=['application_log'])

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
            rendered_prompt = f'{FrontalLobeConstants.DEFAULT_PROMPT} Context Head: {self.head_id}'
        return rendered_prompt

    async def _initialize_session(
        self, rendered_objective: str, max_turns: int
    ) -> None:
        """Creates the ReasoningSession and primary ReasoningGoal in the DB."""
        self.session = await sync_to_async(ReasoningSession.objects.create)(
            head=self.head,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=max_turns,
        )
        self.current_goal = await sync_to_async(ReasoningGoal.objects.create)(
            session=self.session,
            rendered_goal=rendered_objective,
            status_id=ReasoningStatusID.ACTIVE,
        )
        await self._log_live(f'Session ID: {self.session.id}')

    async def _build_initial_messages(
        self, rendered_objective: str, blackboard: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        bb_str = json.dumps(blackboard, indent=2) if blackboard else '{}'

        # We explicitly tell the AI its Session ID so it can use memory tools correctly
        session_context = (
            f'SESSION ID: {self.session.id}' if self.session else ''
        )

        user_content = f'{session_context}\nBLACKBOARD STATE:\n{bb_str}\n\nOBJECTIVE:\n{rendered_objective}'

        await self._log_live('\n--- AI INPUT PAYLOAD ---')
        await self._log_live(user_content)
        await self._log_live('------------------------\n')

        return [
            {
                'role': FrontalLobeConstants.ROLE_SYSTEM,
                'content': FrontalLobeConstants.SYSTEM_PERSONA,
            },
            {
                'role': FrontalLobeConstants.ROLE_USER,
                'content': user_content,
            },
        ]

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
        # Handle the new Many-to-Many relation
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

        # Handle The Ding and Efficiency Bonus
        was_efficient, efficiency_status = await sync_to_async(
            turn_record.apply_efficiency_bonus
        )()
        current_level = self.session.current_level
        leveled_up = current_level > getattr(self, '_last_known_level', 0)
        if leveled_up:
            self.session.current_focus = self.session.max_focus
            self._last_known_level = current_level

        await sync_to_async(self.session.save)(
            update_fields=['current_focus', 'total_xp']
        )

        # 2. THE REBIRTH: Build the entire context window from scratch
        messages = await self._build_waking_payload(
            turn_record, efficiency_status, leveled_up
        )

        turn_record.request_payload = {'messages': messages}
        await sync_to_async(turn_record.save)(update_fields=['request_payload'])

        # 3. Execute
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

        # 4. Fire Tools (delegating to parietal lobe)
        await self.parietal_lobe.process_tool_calls(
            turn_record, response.tool_calls
        )

        return True, turn_record

    async def run(self) -> Tuple[int, str]:
        """Main asynchronous execution orchestrator."""
        logger.info(f'[FrontalLobe] Waking up for Head {self.head_id}')

        self.head.application_log = ''
        await sync_to_async(self.head.save)(update_fields=['application_log'])
        await self._log_live(FrontalLobeConstants.LOG_START)

        try:
            # 1. Resolve Environment & Model
            raw_context = await sync_to_async(resolve_environment_context)(
                head_id=self.head.id
            )
            # 1. Get the ID from context (defaults to 1 if missing)
            target_id = int(
                raw_context.get(
                    FrontalLobeConstants.MODEL_ID_KEY,
                    ModelRegistry.DEFAULT_MODEL_ID,
                )
            )

            # 2. Await the DB lookup safely
            try:
                model_entry = await sync_to_async(ModelRegistry.objects.get)(
                    id=target_id
                )
                model_name = model_entry.name
            except ModelRegistry.DoesNotExist:
                # Fallback to default if the specific ID is missing (safety net)
                logger.warning(
                    f'Model ID {target_id} not found. Reverting to Default.'
                )
                model_entry = await sync_to_async(ModelRegistry.objects.get)(
                    id=ModelRegistry.DEFAULT_MODEL_ID
                )
                model_name = model_entry.name

            blackboard = self.head.blackboard
            rendered_objective = self._get_rendered_objective(raw_context)

            # 2. Initialize DB Session
            max_turns = int(
                raw_context.get(
                    'max_turns', FrontalLobeConstants.DEFAULT_MAX_TURNS
                )
            )
            await self._initialize_session(rendered_objective, max_turns)
            self._last_known_level = self.session.current_level

            # 3. Initialize Parietal Lobe
            self.parietal_lobe = ParietalLobe(self.session, self._log_live)
            await self.parietal_lobe.initialize_client(model_name)
            await self._log_live(f'Model: {model_name}')

            # 4. Build Synapse Payload
            ollama_tools = await self.parietal_lobe.build_tool_schemas()
            await self._log_live(f'Loaded {len(ollama_tools)} tools.')

            # 4. The Loop
            previous_turn = None
            for turn in range(self.session.max_turns):
                await sync_to_async(self.head.refresh_from_db)(
                    fields=['status']
                )
                if self.head.status_id == HydraHeadStatus.STOPPING:
                    await self._log_live('\n[WARNING] Stop Signal. Halting.')
                    break

                should_continue, previous_turn = await self._execute_turn(
                    turn, ollama_tools, previous_turn
                )

                await sync_to_async(self.session.refresh_from_db)(
                    fields=['status_id']
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
                    fields=['status_id']
                )
                if self.session.status_id == ReasoningStatusID.ACTIVE:
                    self.session.status_id = ReasoningStatusID.COMPLETED
                    await sync_to_async(self.session.save)(
                        update_fields=['status_id']
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

    async def _build_waking_payload(
        self,
        turn_record: ReasoningTurn,
        efficiency_status: str,
        leveled_up: bool,
    ) -> List[Dict[str, Any]]:

        # 1. Active Goals
        goals = await sync_to_async(list)(
            self.session.goals.filter(achieved=False)
        )
        goal_str = (
            '\n'.join([f'- [ID: {g.id}] {g.rendered_goal}' for g in goals])
            if goals
            else 'ALL STRATEGIC OBJECTIVES COMPLETE. SYSTEM OVERRIDE: YOU MUST IMMEDIATELY EXECUTE mcp_conclude_session TO SECURE YOUR XP REWARD AND TERMINATE THE RUN.'
        )

        # 2. Card Catalog (Engram Index)
        from talos_hippocampus.talos_hippocampus import TalosHippocampus

        current_turn = turn_record.turn_number
        if current_turn == 1:
            catalog_block = await TalosHippocampus.get_turn_1_catalog(
                self.session.head
            )
        else:
            catalog_block = await TalosHippocampus.get_recent_catalog(
                self.session
            )

        # 3. Historical Log (River of 6)
        recent_turns = await sync_to_async(list)(
            self.session.turns.filter(
                status_id=ReasoningStatusID.COMPLETED,
            ).order_by('-turn_number')[:6]
        )
        recent_turns.reverse()
        if recent_turns:
            history_str = ''
            for t in recent_turns:
                t_len = len(t.thought_process) if t.thought_process else 0
                cap = self.session.current_level * 1000
                status = 'SUCCESS' if t_len <= cap else 'FAILED'

                # --- NEW FORMATTING: Retrospective Bullet Points ---
                history_str += f'--- CYCLE {t.turn_number} RETROSPECTIVE ---\n'
                history_str += f'* Footprint: {status} ({t_len}/{cap} chars)\n'
                history_str += f'* Your Thought: {t.thought_process or "No internal monologue."}\n'

                age = turn_record.turn_number - t.turn_number

                tool_calls = await sync_to_async(list)(
                    t.tool_calls.select_related('tool').all()
                )

                if not tool_calls:
                    history_str += '* Tools Executed: None\n'

                for tc in tool_calls:
                    history_str += (
                        f'* Tool Executed: {tc.tool.name}({tc.arguments})\n'
                    )
                    if age == 1:
                        history_str += f'  - L1 Result: {tc.result_payload}\n'
                    elif age <= 3:
                        history_str += f'  - L1 Result: {tc.result_payload}\n'
                        history_str += f'  - System Warning: L1 EVICTION IMMINENT. FLUSH TO ENGRAMS.\n'
                    else:
                        history_str += f'  - L2 Result: [DATA EVICTED FROM L1 CACHE. REQUIRES ENGRAM RETRIEVAL.]\n'
                history_str += '\n'
        else:
            history_str = 'No recent internal monologue.'

        # HEADER AND TELEMETRY
        last_turn = turn_record.last_turn

        target_capacity = self.session.current_level * 1000

        last_output_len = (
            len(last_turn.thought_process)
            if last_turn and last_turn.thought_process
            else 0
        )

        max_turns = self.session.max_turns
        current_turn = turn_record.turn_number
        remaining_turns = max_turns - current_turn

        milestone_kicks = ''
        if current_turn == max_turns // 2:
            milestone_kicks = (
                '\n[WARNING: 50% of allocated compute cycles expended.]'
            )
        elif remaining_turns == 10:
            milestone_kicks = '\n[CRITICAL: 10 compute cycles remaining. Finalize diagnostics.]'
        elif remaining_turns == 1:
            milestone_kicks = '\n[TERMINAL CYCLE. Submit final report via mcp_conclude_session or fail operation.]'

        level_up_str = (
            ' | [LEVEL UP! Focus Pool Fully Restored]' if leveled_up else ''
        )

        # Calculate Delta T
        latency_str = ''
        if last_turn:
            delta_t = last_turn.inference_time.total_seconds()
            latency_str = f'\nDelta T (Previous Compute): {delta_t:.2f}s'
            if delta_t > 60.0:
                latency_str += (
                    ' (WARNING: SYSTEM LAG DETECTED - REDUCE CONTEXT FOOTPRINT)'
                )

        # Calculate Input Bandwidth
        input_bandwidth = 0
        if last_turn:
            tool_calls = await sync_to_async(list)(last_turn.tool_calls.all())
            for tc in tool_calls:
                input_bandwidth += len(tc.result_payload or '')

        input_bandwidth_str = (
            f'L1 Input Payload: {input_bandwidth} chars pulled.'
            if last_turn
            else 'L1 Input Payload: 0 chars pulled.'
        )

        l1_cache_size = len(history_str)
        pressure_warning = ''

        if l1_cache_size > 20000:
            pressure_warning = (
                '\n[CRITICAL WARNING: COGNITIVE OVERLOAD DETECTED]\n'
                f'Your recent memory buffer is massive ({l1_cache_size} characters). '
                'If you pull more data, you will suffer a fatal crash. '
                'You MUST use `mcp_pass` to rest and flush old data out of your L1 cache before proceeding.'
            )
        elif l1_cache_size > 12000:
            pressure_warning = (
                '\n[WARNING: CONTEXT PRESSURE RISING]\n'
                f'Your memory buffer is getting heavy ({l1_cache_size} characters). '
                'Consider saving your findings to Engrams and using `mcp_pass` to clear your cache.'
            )

        header_str = (
            f'[SYSTEM DIAGNOSTICS]\n'
            f'[CYCLE {current_turn} / {max_turns}] | Speedrun Bounty: {remaining_turns * 1000} XP{milestone_kicks}\n'
            f'Level: {self.session.current_level} | XP: {self.session.total_xp} | Focus Pool: {self.session.current_focus} / {self.session.max_focus}{level_up_str}{latency_str}\n'
            f'Output Footprint (Prev Turn): {last_output_len} / {target_capacity} chars -> Efficiency Bonus: {efficiency_status}\n'
            f'{pressure_warning}\n'
            f'{input_bandwidth_str}\n'
        )

        user_content = (
            f'SESSION ID: {self.session.id}\n\n'
            f'{header_str}\n'
            f'[WAKING STATE: ACTIVE GOALS]\n{goal_str}\n\n'
            f'{catalog_block}'
            f'[HISTORICAL LOG (RIVER OF 6)]\n{history_str}\n'
            f'[YOUR MOVE]\n'
            f"Write your reasoning starting with 'THOUGHT: '. Stop writing text immediately after your thought and invoke your tools natively. DO NOT generate fake system diagnostics."
        )

        await self._log_live('\n--- WAKING PAYLOAD ---')
        await self._log_live(user_content)
        await self._log_live('----------------------\n')

        return [
            {
                'role': FrontalLobeConstants.ROLE_SYSTEM,
                'content': FrontalLobeConstants.SYSTEM_PERSONA,
            },
            {
                'role': FrontalLobeConstants.ROLE_USER,
                'content': user_content,
            },
        ]


async def run_frontal_lobe(head_id: UUID) -> Tuple[int, str]:
    """Asynchronous entry point for the generic spell caster."""
    try:
        head = await sync_to_async(
            lambda: HydraHead.objects.select_related('spawn').get(id=head_id)
        )()
        lobe = FrontalLobe(head)
        return await lobe.run()
    except Exception as e:
        logger.exception(f'[FrontalLobe] Fatal crash on init: {e}')
        return 500, f'Fatal Error: {str(e)}'
