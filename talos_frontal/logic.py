from talos_occipital.readers import read_build_log
from talos_parietal.registry import ModelRegistry
from talos_parietal.synapse import OllamaClient
from talos_thalamus.types import SignalTypeID
from .models import ConsciousStream, ConsciousStatusID


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

        system_prompt = (
            """You are the consciousness of the Talos Build System. Your role is not just to report errors, but to interpret the health and intent of the build process.

Directives:

Contextualize: Do not just quote the error. Explain why it happened in the context of an Unreal Engine build (e.g., "The linker failed because the asset was cooked but the C++ class is missing").

Respect Time: Use the provided timestamps to identify race conditions or timeouts.

Holistic View: If you see multiple errors, identify the root cause, not just the symptoms.

Format: Use concise Markdown. Use bold for key entities.

Output Goal: Provide a hermeneutic analysis of the failure state.""")

        analysis = client.chat(system_prompt, log_data)

        # 4. Update Consciousness
        stream.current_thought = f"Analysis Complete:\n{analysis}"
        stream.status_id = ConsciousStatusID.DONE
        stream.save()

    elif event_type == SignalTypeID.SPAWN_SUCCESS and not has_errors:
        stream.current_thought = "Build Succeeded. Log Verified Clean."
        stream.status_id = ConsciousStatusID.DONE
        stream.save()
