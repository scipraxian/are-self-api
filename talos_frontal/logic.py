from talos_occipital.readers import read_build_log
from talos_parietal.registry import ModelRegistry
from talos_parietal.synapse import OllamaClient
from talos_thalamus.types import SignalTypeID
from .models import ConsciousStatusID, ConsciousStream, SystemDirective, SystemDirectiveIdentifierID


def process_stimulus(stimulus):
    """
    The Executive Function. Decides what to do with a signal.
    """
    # 1. Capture the thought (Log it)
    print(f"[FRONTAL] Processing Stimulus: {stimulus}")

    # We assume stimulus.source is 'hydra' and description implies failure
    # or we check the context.
    spawn_id = stimulus.context_data.get('spawn_id')
    head_id = stimulus.context_data.get('head_id')
    event_type = stimulus.context_data.get('event_type')

    if not spawn_id:
        return

    # Create Conscious Stream Entry
    stream = ConsciousStream.objects.create(
        spawn_link_id=spawn_id,
        head_link_id=head_id,
        current_thought=
        f"Received Stimulus: {stimulus.description}. Analyzing...",
        status_id=ConsciousStatusID.THINKING)

    # 2. Perception (Occipital) - ALWAYS Read
    log_data = read_build_log(spawn_id)
    has_errors = "ERROR SUMMARY" in log_data

    # 3. Decision Logic
    should_analyze = False

    if event_type == SignalTypeID.SPAWN_FAILED:
        should_analyze = True
    elif event_type == SignalTypeID.SPAWN_SUCCESS and has_errors:
        stream.current_thought = "Build 'Succeeded' (Exit 0), but Errors detected in logs. Analyzing..."
        stream.save()
        should_analyze = True

    if should_analyze:
        if not log_data or log_data == "Spawn not found." or log_data == "No execution heads found for this spawn.":
            stream.current_thought = "Analysis Failed: No log data found."
            stream.status_id = ConsciousStatusID.DONE
            stream.save()
            return

        # 3. Cognition (Parietal)
        model_name = ModelRegistry.get_model('scout_light')
        client = OllamaClient(model=model_name)

        try:
            directive = SystemDirective.objects.get(
                identifier_id=SystemDirectiveIdentifierID.ANALYSIS_CORE,
                is_active=True
            )
            system_prompt = directive.format_prompt(log_data=log_data)
        except SystemDirective.DoesNotExist:
            # Fallback (Safety net)
            system_prompt = "Analyze this log: " + log_data
        except KeyError:
            # Handle missing variables
            return

        analysis = client.chat(system_prompt, log_data)

        # 4. Update Consciousness
        stream.current_thought = f"Analysis Complete:\n{analysis}"
        stream.status_id = ConsciousStatusID.DONE
        stream.save()

    elif event_type == SignalTypeID.SPAWN_SUCCESS and not has_errors:
        stream.current_thought = "Build Succeeded. Log Verified Clean."
        stream.status_id = ConsciousStatusID.DONE
        stream.save()
