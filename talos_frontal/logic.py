import logging
import traceback
from hydra.models import HydraSpawn
from talos_occipital.readers import read_build_log
from talos_parietal.registry import ModelRegistry
from talos_parietal.synapse import OllamaClient
from talos_thalamus.types import SignalTypeID
from .models import ConsciousStatusID, ConsciousStream, SystemDirective, SystemDirectiveIdentifierID
from .utils import parse_ai_actions
from talos_parietal.tools import ai_read_file, ai_execute_task

logger = logging.getLogger(__name__)


def process_stimulus(stimulus):
    """
    The Executive Function. Decides what to do with a signal.
    """
    # 1. Capture the thought
    logger.info(f"[FRONTAL] 🧠 Stimulus Received: {stimulus.description}")

    spawn_id = stimulus.context_data.get('spawn_id')
    head_id = stimulus.context_data.get('head_id')
    event_type = stimulus.context_data.get('event_type')

    if not spawn_id:
        logger.error("[FRONTAL] ❌ No spawn_id in stimulus data. Aborting.")
        return

    # Create Conscious Stream Entry (Initial State)
    try:
        stream = ConsciousStream.objects.create(
            spawn_link_id=spawn_id,
            head_link_id=head_id,
            current_thought=f"Received Stimulus: {stimulus.description}. Initializing Cortex...",
            status_id=ConsciousStatusID.THINKING
        )
    except Exception as e:
        logger.error(f"[FRONTAL] 💥 Failed to create ConsciousStream: {e}")
        return

    # 1. FETCH DIRECTIVE
    # We do this early to get the token budget
    directive = None
    try:
        directive = SystemDirective.objects.get(
            identifier_id=SystemDirectiveIdentifierID.ANALYSIS_CORE,
            is_active=True
        )
        token_budget = directive.context_window_size
        max_output = directive.max_output_tokens
        temp = directive.temperature
        logger.info(f"[FRONTAL] 📜 Loaded Directive v{directive.version} (Budget: {token_budget})")
    except SystemDirective.DoesNotExist:
        logger.warning("[FRONTAL] ⚠️ No Directive found. Using Safety Fallbacks.")
        token_budget = 128000
        max_output = 1024
        temp = 0.1

    # 2. PERCEPTION (Occipital)
    logger.info(f"[FRONTAL] 👀 Reading Logs for Spawn {spawn_id}...")
    log_data = read_build_log(spawn_id, max_token_budget=token_budget)

    error_count = log_data.count("Error:") + log_data.count("Exception:")
    has_errors = "ERROR SUMMARY" in log_data
    logger.info(f"[FRONTAL] 📊 Log Analysis: {len(log_data)} chars, {error_count} errors detected.")

    # 3. DECISION LOGIC
    should_analyze = False
    if event_type == SignalTypeID.SPAWN_FAILED:
        should_analyze = True
        logger.info("[FRONTAL] 🚨 Spawn FAILED. Analysis Required.")
    elif event_type == SignalTypeID.SPAWN_SUCCESS and has_errors:
        msg = "Build 'Succeeded' (Exit 0), but Errors detected in logs. Paranoid Analysis initiated."
        stream.current_thought = msg
        stream.save()
        logger.info(f"[FRONTAL] 🕵️ {msg}")
        should_analyze = True

    if should_analyze:
        if not log_data or "No execution heads" in log_data:
            msg = "Analysis Aborted: No log data found in Occipital scan."
            stream.current_thought = msg
            stream.status_id = ConsciousStatusID.DONE
            stream.save()
            logger.warning(f"[FRONTAL] {msg}")
            return

        # 4. COGNITION (Parietal)
        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        options = {
            "num_ctx": token_budget,
            "num_predict": max_output,
            "temperature": temp,
        }

        # Context Gathering
        try:
            spawn_obj = HydraSpawn.objects.get(id=spawn_id)
            # Default to "Unknown" if env missing, safe access
            if spawn_obj.environment and spawn_obj.environment.project_environment:
                project_root = spawn_obj.environment.project_environment.project_root
            else:
                project_root = "Unknown/Project/Root"
        except Exception as e:
            logger.error(f"[FRONTAL] Failed to resolve Project Root: {e}")
            project_root = "Error_Resolving_Path"

        # Prompt Formatting
        if directive:
            try:
                system_prompt = directive.format_prompt(
                    log_data=log_data,
                    spawn_id=str(spawn_id),
                    head_id=str(head_id) if head_id else "Unknown",
                    error_count=str(error_count),
                    event_type=str(event_type),
                    project_root=project_root  # <--- INJECTED
                )
            except KeyError as e:
                msg = f"**SYSTEM ERROR:** Prompt template missing variable: {e}"
                logger.error(f"[FRONTAL] 💥 {msg}")
                stream.current_thought = msg
                stream.status_id = ConsciousStatusID.DONE
                stream.save()
                return
        else:
            system_prompt = f"Analyze this log:\n{log_data}"

        # --- THE SPELLCASTER LOOP ---
        MAX_TURNS = 5
        turn = 0
        conversation_history = log_data  # Initial context
        total_tokens_in = 0
        total_tokens_out = 0
        final_thought = ""

        logger.info(f"[FRONTAL] ⚡ Starting Cognitive Loop (Max Turns: {MAX_TURNS})...")

        try:
            while turn < MAX_TURNS:
                turn += 1
                logger.info(f"[FRONTAL] 🔄 Turn {turn}/{MAX_TURNS}: Querying {model_name}...")

                # Update stream so user sees we are thinking
                if turn > 1:
                    stream.current_thought = final_thought + f"\n\n*(Thinking... Turn {turn})*"
                    stream.save()

                result = client.chat(system_prompt, conversation_history, options=options)

                content = result.get('content', "")
                total_tokens_in += result.get('tokens_input', 0)
                total_tokens_out += result.get('tokens_output', 0)

                # Append to thought stream
                final_thought += content + "\n\n"

                # Parse Actions
                actions = parse_ai_actions(content)
                if not actions:
                    logger.info("[FRONTAL] 🛑 No actions requested. Loop complete.")
                    break

                logger.info(f"[FRONTAL] 🛠️ Tool Use Requested: {len(actions)} actions.")

                # Execute Actions
                tool_results = []
                for action in actions:
                    tool_name = action.get('tool')
                    args = action.get('args', {})

                    logger.info(f"[FRONTAL] 🔨 Executing {tool_name} with {args}")

                    if tool_name == 'ai_read_file':
                        res = ai_read_file(args.get('path'))
                        tool_results.append(f"Result (ai_read_file): {res}")
                    elif tool_name == 'ai_execute_task':
                        res = ai_execute_task(args.get('head_id'))
                        tool_results.append(f"Result (ai_execute_task): {res}")
                    else:
                        res = f"Error: Unknown tool '{tool_name}'"
                        tool_results.append(res)

                    # Log result length to console
                    logger.info(f"[FRONTAL]    > Result length: {len(str(res))}")

                # Update conversation for next turn
                # We feed the tool results back into the history so the AI can read them
                conversation_history += f"\n\nAssistant Response:\n{content}"
                conversation_history += f"\n\nSystem Tool Results:\n" + "\n".join(tool_results)

                # Update the visual log for the user
                final_thought += "--- TOOL EXECUTION ---\n" + "\n".join(tool_results) + "\n\n"

            # Final Save
            stream.current_thought = final_thought
            stream.used_prompt = system_prompt
            stream.tokens_input = total_tokens_in
            stream.tokens_output = total_tokens_out
            stream.model_name = result.get('model', model_name)
            stream.status_id = ConsciousStatusID.DONE
            stream.save()
            logger.info("[FRONTAL] ✅ Cognitive Loop Finished successfully.")

        except Exception as e:
            err_msg = f"**CRITICAL FAILURE:** Logic Loop Crashed.\nError: {str(e)}\nTraceback:\n{traceback.format_exc()}"
            logger.error(f"[FRONTAL] 💥 {err_msg}")
            stream.current_thought += f"\n\n{err_msg}"
            stream.status_id = ConsciousStatusID.DONE
            stream.save()
            raise e  # Re-raise to ensure Celery marks task as failed

    elif event_type == SignalTypeID.SPAWN_SUCCESS and not has_errors:
        stream.current_thought = "Build Succeeded. Log Verified Clean."
        stream.status_id = ConsciousStatusID.DONE
        stream.save()
        logger.info("[FRONTAL] ✅ Build Clean. No analysis needed.")