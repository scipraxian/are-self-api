import django_filters

from .models import (
    AIModelCategory,
    AIModelDescription,
    AIModelFamily,
    AIModelTags,
)


class AIModelDescriptionFilter(django_filters.FilterSet):
    """FilterSet for AIModelDescription with M2M support."""

    ai_models = django_filters.UUIDFilter(field_name='ai_models')
    families = django_filters.ModelMultipleChoiceFilter(
        field_name='families',
        queryset=AIModelFamily.objects.all(),
    )
    categories = django_filters.ModelMultipleChoiceFilter(
        field_name='categories',
        queryset=AIModelCategory.objects.all(),
    )
    tags = django_filters.ModelMultipleChoiceFilter(
        field_name='tags',
        queryset=AIModelTags.objects.all(),
    )
    is_current = django_filters.BooleanFilter(field_name='is_current')

    class Meta:
        model = AIModelDescription
        fields = [
            'ai_models',
            'families',
            'categories',
            'tags',
            'is_current',
        ]
