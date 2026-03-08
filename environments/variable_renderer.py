import socket
from typing import Any, Dict

from django.template import Context, Template

from central_nervous_system.constants import KEY_SERVER


class VariableRenderer:
    """
    Handles the interpolation of variables into strings using Django's template engine.
    Also provides utilities for extracting context from ProjectEnvironment objects.
    """

    @staticmethod
    def extract_variables(environment) -> Dict[str, Any]:
        """
        Extracts all context variables associated with a ProjectEnvironment.
        Returns a dictionary suitable for use in a Template Context.
        """
        # Local import to avoid circular dependency
        from environments.models import ContextVariable

        context_data = {KEY_SERVER: socket.gethostname()}

        if not environment:
            return context_data

        env_vars = ContextVariable.objects.filter(
            environment=environment).select_related('key')

        for variable in env_vars:
            if variable.key and variable.key.name:
                context_data[variable.key.name] = variable.value

        return context_data

    @staticmethod
    def render_string(template_string: str, context_dict: Dict[str,
                                                               Any]) -> str:
        """
        Safe wrapper around Django Template rendering.
        """
        if not template_string:
            return ""
        if "{{" not in template_string:
            return template_string

        try:
            template = Template(template_string)
            context = Context(context_dict)
            return template.render(context)
        except Exception:
            # Fallback to returning original string on error to prevent crashes
            return template_string
