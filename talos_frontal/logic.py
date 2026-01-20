import logging
import traceback
from talos_occipital.readers import read_build_log
from talos_thalamus.types import SignalTypeID
from talos_frontal.models import ConsciousStatusID, ConsciousStream
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_reasoning.engine import ReasoningEngine

logger = logging.getLogger(__name__)


class StimulusProcessor:
    """
    The Executive Function of the Frontal Lobe.
    Evaluates signals (stimuli) and delegates complex analysis to the Reasoning Engine.
    """

    def process(self, stimulus):
        """Main entry point for handling a biological signal."""
        logger.info(f"[FRONTAL] 🧠 Stimulus Received: {stimulus.description}")

        spawn_id = stimulus.context_data.get('spawn_id')
        head_id = stimulus.context_data.get('head_id')
        event_type = stimulus.context_data.get('event_type')

        if not spawn_id:
            logger.error("[FRONTAL] ❌ No spawn_id. Aborting.")
            return

        # 1. Initialize Consciousness
        stream = self._create_conscious_stream(spawn_id, head_id,
                                               stimulus.description)
        if not stream:
            logger.error("[FRONTAL] ❌ No Stream. Aborting.")
            return

        # 2. Evaluate Necessity
        should_analyze, prompt = self._evaluate_necessity(spawn_id, event_type)

        if not should_analyze:
            self._finalize_stream(stream,
                                  "Build Succeeded. No anomalies detected.")
            return

        # 3. Handover to Cortex
        try:
            session = self._initialize_cortex_session(spawn_id, prompt)
            self._execute_auto_drive(session, stream)
            self._finalize_stream(
                stream,
                f"Analysis Complete. See Reasoning Session {session.id}.")

        except Exception as e:
            self._handle_crash(stream, e)

    def _create_conscious_stream(self, spawn_id, head_id, description):
        """Creates the initial UI record of thought."""
        try:
            return ConsciousStream.objects.create(
                spawn_link_id=spawn_id,
                head_link_id=head_id,
                current_thought=
                f"Received Stimulus: {description}. Delegating...",
                status_id=ConsciousStatusID.THINKING)
        except Exception as e:
            logger.error(f"[FRONTAL] 💥 Stream Creation Failed: {e}")
            return None

    def _evaluate_necessity(self, spawn_id, event_type):
        """Decides if the stimulus requires deep reasoning."""
        # Quick peek (1000 tokens) to check for error signatures
        log_peek = read_build_log(spawn_id, max_token_budget=1000)
        has_errors = "ERROR SUMMARY" in log_peek

        if event_type == SignalTypeID.SPAWN_FAILED:
            logger.info("[FRONTAL] 🚨 Spawn FAILED. Analysis Required.")
            return True, "The build failed. Analyze the logs, identify the root cause, and suggest a fix."

        if event_type == SignalTypeID.SPAWN_SUCCESS and has_errors:
            logger.info(f"[FRONTAL] 🕵️ Paranoid Analysis initiated.")
            return True, "The build succeeded (Exit 0) but errors were detected in the logs. Perform a paranoid analysis."

        if event_type == SignalTypeID.MULTIPLAYER_DEBUG:
            logger.info(
                "[FRONTAL] 🕶️ Multiplayer Debug Discrepancy Analysis initiated."
            )
            return True, "Compare the Remote Server logs with the Local Client logs. Identify any replication issues, RPC failures, or state discrepancies (e.g. Server says X, Client sees Y)."

        return False, None

    def _initialize_cortex_session(self, spawn_id, initial_prompt):
        """Prepares the Reasoning Engine session with context."""
        # Re-read full log for the engine context
        full_log = read_build_log(spawn_id, max_token_budget=32000)

        session = ReasoningSession.objects.create(
            spawn_link_id=spawn_id,
            goal="Automated Build Analysis",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10)

        ReasoningGoal.objects.create(
            session=session,
            reasoning_prompt=f"{initial_prompt}\n\nCONTEXT DATA:\n{full_log}",
            status_id=ReasoningStatusID.ACTIVE)
        return session

    def _execute_auto_drive(self, session, stream):
        """Drives the engine in a loop until the goal is met."""
        engine = ReasoningEngine()
        logger.info(f"[FRONTAL] 🚀 Starting Auto-Drive for Session {session.id}")

        while True:
            session.refresh_from_db()

            # Stop conditions
            if session.status_id not in [
                    ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING
            ]:
                break

            active_goals = session.goals.filter(status_id__in=[
                ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING
            ])
            if not active_goals.exists():
                session.status_id = ReasoningStatusID.COMPLETED
                session.save()
                break

            # Tick
            engine.tick(session.id)

            # Feedback
            latest_turn = session.turns.last()
            if latest_turn:
                stream.current_thought = f"Turn {latest_turn.turn_number}: {latest_turn.thought_process[:200]}..."
                stream.save()

    def _finalize_stream(self, stream, message):
        """Closes the conscious stream."""
        stream.current_thought = message
        stream.status_id = ConsciousStatusID.DONE
        stream.save()
        logger.info(f"[FRONTAL] ✅ {message}")

    def _handle_crash(self, stream, error):
        """Handles unexpected failures in the logic loop."""
        msg = f"CRITICAL: Auto-Drive Crashed. {error}"
        logger.error(f"[FRONTAL] 💥 {msg}\n{traceback.format_exc()}")
        stream.current_thought = msg
        stream.status_id = ConsciousStatusID.DONE
        stream.save()


# Public API wrapper for backward compatibility/signals
def process_stimulus(stimulus):
    processor = StimulusProcessor()
    processor.process(stimulus)
