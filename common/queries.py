from dataclasses import dataclass
from typing import Type

from django.apps import apps
from django.db.models import Model


@dataclass
class GuessResult:
    success: bool
    app_label: str
    model_class: Type[Model] | None
    message: str


def guess_model(
    model_name: str,
) -> GuessResult:
    """Attempts to guess the model class from a model name.

    NOTE: Models by the same name, the first to be encountered is returned.

    Returns a GuessResult object with details about the model.
    """
    result = GuessResult(
        success=False, app_label='', model_class=None, message=''
    )

    exact_match = None
    close_matches = []

    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            if model.__name__.lower() == model_name.lower():
                exact_match = model
                result.success = True
                break
            elif model_name.lower() in model.__name__.lower():
                close_matches.append(model.__name__)
        if result.success:
            break

    if not exact_match:
        result.message = f"Error: No models found resembling '{model_name}'."
        if close_matches:
            result.message = (
                f"Error: Model '{model_name}' not found. "
                f'Did you mean: {", ".join(close_matches)}?'
            )

    if result.success:
        result.model_class = exact_match
        result.app_label = result.model_class._meta.app_label
        result.message = (
            f"Found model '{result.model_class.__name__}' "
            f"in app '{result.app_label}'."
        )

    return result
