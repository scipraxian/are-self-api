"""Prompt handler — injects the rendered NeuronContext prompt at TERMINAL."""
from typing import Any, Dict, List

from central_nervous_system.utils import resolve_environment_context
from environments.variable_renderer import VariableRenderer
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.models import ReasoningTurn
from identity.addons._handler import IdentityAddonHandler


class Prompt(IdentityAddonHandler):
    def on_terminal(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        if not turn or not turn.session:
            return []

        spike = turn.session.spike
        if not spike:
            return []

        raw_context = resolve_environment_context(spike_id=spike.id)
        if not raw_context:
            return []

        raw_prompt = raw_context.get(
            FrontalLobeConstants.KEY_PROMPT,
            raw_context.get(FrontalLobeConstants.KEY_OBJECTIVE, None),
        )
        if not raw_prompt:
            return []

        rendered_prompt = VariableRenderer.render_string(
            str(raw_prompt), raw_context
        )
        if rendered_prompt.strip():
            return [{'role': 'user', 'content': rendered_prompt}]
        return []
