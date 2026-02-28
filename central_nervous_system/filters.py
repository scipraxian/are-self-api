import django_filters

from .models import CNSHead, CNSHeadStatus, CNSSpawn, CNSSpawnStatus


class CNSSpawnFilter(django_filters.FilterSet):
    is_root = django_filters.BooleanFilter(
        field_name='parent_head', lookup_expr='isnull'
    )

    # Delta Cursors
    modified__gt = django_filters.IsoDateTimeFilter(
        field_name='modified', lookup_expr='gt'
    )
    created__gt = django_filters.IsoDateTimeFilter(
        field_name='created', lookup_expr='gt'
    )

    is_active = django_filters.BooleanFilter(method='filter_is_active')

    class Meta:
        model = CNSSpawn
        fields = ['spellbook', 'status', 'environment', 'parent_head']

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                status_id__in=CNSSpawnStatus.IS_ALIVE_STATUS_LIST
            )
        return queryset.filter(
            status_id__in=CNSSpawnStatus.IS_TERMINAL_STATUS_LIST
        )


class CNSHeadFilter(django_filters.FilterSet):
    spawn_id = django_filters.UUIDFilter(field_name='spawn_id')
    modified__gt = django_filters.IsoDateTimeFilter(
        field_name='modified', lookup_expr='gt'
    )

    is_active = django_filters.BooleanFilter(method='filter_is_active')

    class Meta:
        model = CNSHead
        fields = ['spawn', 'status', 'node', 'spell', 'target']

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                status_id__in=CNSHeadStatus.IS_ALIVE_STATUS_LIST
            )
        return queryset.filter(
            status_id__in=CNSHeadStatus.IS_TERMINAL_STATUS_LIST
        )
