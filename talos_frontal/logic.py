import logging
import traceback

from hydra.models import HydraSpawn
from talos_occipital.readers import read_build_log
from talos_parietal.registry import ModelRegistry
from talos_parietal.synapse import OllamaClient
from talos_parietal.tools import ai_execute_task, ai_read_file, ai_search_file
from talos_thalamus.types import SignalTypeID
from .models import ConsciousStatusID, ConsciousStream, SystemDirective, SystemDirectiveIdentifierID
from .utils import parse_command_string

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
            current_thought=
            f"Received Stimulus: {stimulus.description}. Initializing Cortex...",
            status_id=ConsciousStatusID.THINKING)
    except Exception as e:
        logger.error(f"[FRONTAL] 💥 Failed to create ConsciousStream: {e}")
        return

    # 1. FETCH CONFIG
    directive = None
    try:
        directive = SystemDirective.objects.get(
            identifier_id=SystemDirectiveIdentifierID.ANALYSIS_CORE,
            is_active=True)
        token_budget = directive.context_window_size
        max_output = directive.max_output_tokens
        temp = directive.temperature
        logger.info(
            f"[FRONTAL] 📜 Loaded Directive v{directive.version} (Budget: {token_budget})"
        )
    except SystemDirective.DoesNotExist:
        logger.warning(
            "[FRONTAL] ⚠️ No Directive found. Using Safety Fallbacks.")
        token_budget = 32768
        max_output = 1024
        temp = 0.1

    # 2. PERCEPTION (Occipital)
    logger.info(f"[FRONTAL] 👀 Reading Logs for Spawn {spawn_id}...")
    log_data = read_build_log(spawn_id, max_token_budget=token_budget)

    error_count = log_data.count("Error:") + log_data.count("Exception:")
    has_errors = "ERROR SUMMARY" in log_data
    logger.info(
        f"[FRONTAL] 📊 Log Analysis: {len(log_data)} chars, {error_count} errors detected."
    )

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
        # Use COMMANDER (Gemma 27B) if available, fallback to Scout
        model_name = ModelRegistry.get_model(ModelRegistry.COMMANDER)
        client = OllamaClient(model=model_name)

        options = {
            "num_ctx": token_budget,
            "num_predict": max_output,
            "temperature": temp,
        }

        # Context Gathering
        try:
            spawn_obj = HydraSpawn.objects.get(id=spawn_id)
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
                    project_root=str(project_root))
            except KeyError as e:
                msg = f"**SYSTEM ERROR:** Prompt template missing variable: {e}"
                logger.error(f"[FRONTAL] 💥 {msg}")
                stream.current_thought = msg
                stream.status_id = ConsciousStatusID.DONE
                stream.save()
                return
        else:
            system_prompt = f"Analyze log. Use READ_FILE: <path> to see files.\n{log_data}"

        # --- THE SPELLCASTER LOOP ---
        MAX_TURNS = 5
        turn = 0
        conversation_history = ""
        total_in = 0
        total_out = 0
        final_thought = ""

        logger.info(
            f"[FRONTAL] ⚡ Starting Cognitive Loop (Max Turns: {MAX_TURNS})...")

        try:
            while turn < MAX_TURNS:
                turn += 1
                logger.info(
                    f"[FRONTAL] 🔄 Turn {turn}/{MAX_TURNS}: Querying {model_name}..."
                )

                if turn > 1:
                    stream.current_thought = final_thought + f"\n\n*(Thinking... Turn {turn})*"
                    stream.save()

                # INJECT REMINDER (CLI SYNTAX)
                reminder = "\n\nSYSTEM: Waiting for command (e.g. READ_FILE: <path>). Do not hallucinate results."

                current_context = conversation_history + reminder

                result = client.chat(system_prompt,
                                     current_context,
                                     options=options)
                logger.info(f"[FRONTAL] Response processing.")

                content = result.get('content', "")
                total_in += result.get('tokens_input', 0)
                total_out += result.get('tokens_output', 0)

                final_thought += content + "\n\n"
                conversation_history += f"\n\nASSISTANT:\n{content}"

                # Parse Actions (Using New CLI Parser)
                action = parse_command_string(content)
                if not action:
                    logger.info(
                        "[FRONTAL] 🛑 No valid command found. Loop complete.")
                    break

                # Support list for loop logic compatibility
                actions = [action]

                logger.info(
                    f"[FRONTAL] 🛠️ Tool Use Requested: {len(actions)} actions.")

                tool_output_block = "\n\nSYSTEM (TOOL RESULTS):"

                for action in actions:
                    tool_name = action.get('tool')
                    args = action.get('args', {})

                    if tool_name in ['ai_read_file', 'ai_search_file'] and project_root:
                        args['root_path'] = project_root

                    logger.info(
                        f"[FRONTAL] 🔨 Executing {tool_name} with {args}")

                    res = ""
                    if tool_name == 'ai_read_file':
                        try:
                            s_line = int(args.get('start_line', 1))
                            requested_max = int(args.get('max_lines', 50))
                            m_lines = min(requested_max, 150)
                        except ValueError:
                            s_line = 1
                            m_lines = 50

                        res = ai_read_file(args.get('path'),
                                           root_path=args.get('root_path'),
                                           start_line=s_line,
                                           max_lines=m_lines)
                        tool_results_str = f"Result (ai_read_file lines {s_line}-{s_line + m_lines}): \n{res}"
                        tool_output_block += f"\n{tool_results_str}"
                        final_thought += f"> **read_file** executed.\n"

                    elif tool_name == 'ai_search_file':
                        res = ai_search_file(args.get('path'),
                                             args.get('pattern'),
                                             root_path=args.get('root_path'))
                        tool_output_block += f"\nResult (ai_search_file): {res}"
                        final_thought += f"> **search_file** executed.\n"

                    elif tool_name == 'ai_list_files':
                        from talos_parietal.tools import ai_list_files
                        res = ai_list_files(args.get('path'), root_path=args.get('root_path'))
                        tool_output_block += f"\nResult (ai_list_files): {res}"
                        final_thought += f"> **list_files** executed.\n"

                    elif tool_name == 'ai_execute_task':
                        res = ai_execute_task(args.get('head_id'))
                        tool_output_block += f"\nResult (ai_execute_task): {res}"
                        final_thought += f"> **execute_task** executed.\n"

                    else:
                        res = f"Error: Unknown tool '{tool_name}'"
                        tool_output_block += f"\n{res}"

                    logger.info(
                        f"[FRONTAL]    > Result length: {len(str(res))}")

                conversation_history += tool_output_block

            stream.current_thought = final_thought
            stream.used_prompt = system_prompt
            stream.tokens_input = total_in
            stream.tokens_output = total_out
            stream.model_name = result.get('model', model_name)
            stream.status_id = ConsciousStatusID.DONE
            stream.save()
            logger.info("[FRONTAL] ✅ Cognitive Loop Finished successfully.")

        except Exception as e:
            err_msg = f"**CRITICAL FAILURE:** Logic Loop Crashed.\n{str(e)}\n{traceback.format_exc()}"
            logger.error(f"[FRONTAL] 💥 {err_msg}")
            stream.current_thought += f"\n\n{err_msg}"
            stream.status_id = ConsciousStatusID.DONE
            stream.save()
            raise e

    elif event_type == SignalTypeID.SPAWN_SUCCESS and not has_errors:
        stream.current_thought = "Build Succeeded. Log Verified Clean."
        stream.status_id = ConsciousStatusID.DONE
        stream.save()
        logger.info("[FRONTAL] ✅ Build Clean. No analysis needed.")