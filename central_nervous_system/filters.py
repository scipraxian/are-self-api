import django_filters

from .models import Spike, SpikeStatus, SpikeTrain, SpikeTrainStatus


class SpikeTrainFilter(django_filters.FilterSet):
    is_root = django_filters.BooleanFilter(
        field_name='parent_spike', lookup_expr='isnull'
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
        model = SpikeTrain
        fields = ['pathway', 'status', 'environment', 'parent_spike']

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                status_id__in=SpikeTrainStatus.IS_ALIVE_STATUS_LIST
            )
        return queryset.filter(
            status_id__in=SpikeTrainStatus.IS_TERMINAL_STATUS_LIST
        )


class SpikeFilter(django_filters.FilterSet):
    spike_train_id = django_filters.UUIDFilter(field_name='spike_train')
    celery_task_id = django_filters.UUIDFilter(field_name='celery_task_id')
    modified__gt = django_filters.IsoDateTimeFilter(
        field_name='modified', lookup_expr='gt'
    )

    is_active = django_filters.BooleanFilter(method='filter_is_active')
    target_hostname = django_filters.CharFilter(
        field_name='target__hostname', lookup_expr='exact'
    )

    class Meta:
        model = Spike
        fields = ['spike_train', 'status', 'neuron', 'effector', 'target', 'celery_task_id']

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                status_id__in=SpikeStatus.IS_ALIVE_STATUS_LIST
            )
        return queryset.filter(
            status_id__in=SpikeStatus.IS_TERMINAL_STATUS_LIST
        )
