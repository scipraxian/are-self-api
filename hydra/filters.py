import django_filters

from .models import HydraHead, HydraHeadStatus, HydraSpawn, HydraSpawnStatus


class HydraSpawnFilter(django_filters.FilterSet):
    # ?is_root=true translates to parent_head__isnull=True
    is_root = django_filters.BooleanFilter(
        field_name='parent_head', lookup_expr='isnull'
    )

    # ?modified__gt=2026-02-15T12:00:00Z
    modified__gt = django_filters.DateTimeFilter(
        field_name='modified', lookup_expr='gt'
    )

    # ?is_active=true
    is_active = django_filters.BooleanFilter(method='filter_is_active')

    class Meta:
        model = HydraSpawn
        fields = ['spellbook', 'status', 'environment']

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                status_id__in=HydraSpawnStatus.IS_ALIVE_STATUS_LIST
            )
        return queryset.filter(
            status_id__in=HydraSpawnStatus.IS_TERMINAL_STATUS_LIST
        )


class HydraHeadFilter(django_filters.FilterSet):
    # ?spawn_id=...
    spawn_id = django_filters.UUIDFilter(field_name='spawn__id')

    # ?modified__gt=...
    modified__gt = django_filters.DateTimeFilter(
        field_name='modified', lookup_expr='gt'
    )

    # ?is_active=true
    is_active = django_filters.BooleanFilter(method='filter_is_active')

    class Meta:
        model = HydraHead
        fields = ['spawn_id', 'status', 'node', 'spell']

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                status_id__in=HydraHeadStatus.IS_ALIVE_STATUS_LIST
            )
        return queryset.filter(
            status_id__in=HydraHeadStatus.IS_TERMINAL_STATUS_LIST
        )
