from typing import Any, Dict, List

from central_nervous_system.utils import resolve_environment_context
from environments.variable_renderer import VariableRenderer
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import ReasoningTurn


def prompt_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: TERMINAL)
    Injects the rendered prompt context variable as the session instruction.
    The prompt is resolved from the spike's NeuronContext chain and template-rendered
    with environment variables.
    STRICTLY SYNCHRONOUS.
    """
    if not turn or not turn.session:
        return []

    # Get the spike from the session
    spike = turn.session.spike
    if not spike:
        return []

    spike_id = spike.id

    # Resolve environment context synchronously
    raw_context = resolve_environment_context(spike_id=spike_id)
    if not raw_context:
        return []

    # Extract the prompt from raw_context
    raw_prompt = raw_context.get(
        FrontalLobeConstants.KEY_PROMPT,
        raw_context.get(
            FrontalLobeConstants.KEY_OBJECTIVE,
            None,
        ),
    )

    # If no prompt found, return empty list
    if not raw_prompt:
        return []

    # Render the prompt with environment variables
    rendered_prompt = VariableRenderer.render_string(str(raw_prompt), raw_context)

    # Return as a single user message if rendered prompt has content
    if rendered_prompt.strip():
        return [{'role': 'user', 'content': rendered_prompt}]

    return []
