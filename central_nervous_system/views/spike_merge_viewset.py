"""V2 API ViewSet for N-way spike log merging."""

import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

import ue_tools.log_parser  # noqa: F401  # registers UE strategies with LogParserFactory
from central_nervous_system.models import Spike, SpikeStatus
from occipital_lobe.merge_logs_nway import (
    merge_delta,
    merge_logs_nway,
    serialize_result,
)

logger = logging.getLogger(__name__)

MIN_SPIKES = 2
MAX_SPIKES = 4
SPIKE_PARAM_KEYS = ['s1', 's2', 's3', 's4']
ERR_MIN_SPIKES = 'At least 2 spike IDs required (s1, s2).'
ERR_MAX_SPIKES = 'At most 4 spike IDs supported.'
ERR_SPIKE_NOT_FOUND = 'Spike %s not found.'
ERR_MISSING_SPIKES_BODY = 'Request body must contain "spikes" dict.'


def _get_spike_label(spike: Spike) -> str:
    """Derive a human-readable label for a spike column."""
    if spike.effector:
        return spike.effector.name
    if spike.target:
        return spike.target.hostname
    return str(spike.id)


def _any_spike_active(spikes: list[Spike]) -> bool:
    """Return True if any spike is in a non-terminal status."""
    return any(
        s.status_id not in SpikeStatus.IS_TERMINAL_STATUS_LIST
        for s in spikes
    )


def _get_spike_log(spike: Spike) -> str:
    """Return application_log, falling back to execution_log."""
    return spike.application_log or spike.execution_log or ''


class SpikeLogMergeViewSet(ViewSet):
    """N-way spike log merge endpoints."""

    @action(detail=False, methods=['get'], url_path='merge')
    def merge(self, request) -> Response:
        """Full N-way merge of spike logs.

        Query params: s1, s2, s3, s4 (UUIDs). At least 2 required.
        """
        spike_ids = [
            request.query_params.get(key)
            for key in SPIKE_PARAM_KEYS
            if request.query_params.get(key)
        ]

        if len(spike_ids) < MIN_SPIKES:
            return Response(
                {'error': ERR_MIN_SPIKES},
                status=status.HTTP_400_BAD_REQUEST,
            )

        spikes = []
        for spike_id in spike_ids:
            try:
                spikes.append(Spike.objects.select_related(
                    'effector', 'target', 'status',
                ).get(id=spike_id))
            except Spike.DoesNotExist:
                logger.warning(
                    '[SpikeLogMerge] %s', ERR_SPIKE_NOT_FOUND % spike_id
                )
                return Response(
                    {'error': ERR_SPIKE_NOT_FOUND % spike_id},
                    status=status.HTTP_404_NOT_FOUND,
                )

        sources = []
        for spike in spikes:
            label = _get_spike_label(spike)
            sources.append((label, _get_spike_log(spike)))

        result = merge_logs_nway(sources)

        # Replace label-keyed cursors with spike-id-keyed cursors
        cursor_map = {}
        for spike, (label, _) in zip(spikes, sources):
            cursor_map[str(spike.id)] = result.cursors.get(label, 0)
        result.cursors = cursor_map

        any_active = _any_spike_active(spikes)

        return Response(serialize_result(result, any_active))

    @action(
        detail=False, methods=['post'], url_path='merge-delta'
    )
    def merge_delta(self, request) -> Response:
        """Incremental delta merge from frontend chunks.

        Body:
        {
            "spikes": {
                "uuid1": {"cursor": 123, "chunk": "new text..."},
                "uuid2": {"cursor": 456}
            }
        }
        """
        spikes_data = request.data.get('spikes')
        if not spikes_data or not isinstance(spikes_data, dict):
            return Response(
                {'error': ERR_MISSING_SPIKES_BODY},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(spikes_data) < MIN_SPIKES:
            return Response(
                {'error': ERR_MIN_SPIKES},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(spikes_data) > MAX_SPIKES:
            return Response(
                {'error': ERR_MAX_SPIKES},
                status=status.HTTP_400_BAD_REQUEST,
            )

        spikes = []
        for spike_id in spikes_data:
            try:
                spikes.append(Spike.objects.select_related(
                    'effector', 'target', 'status',
                ).get(id=spike_id))
            except Spike.DoesNotExist:
                return Response(
                    {'error': ERR_SPIKE_NOT_FOUND % spike_id},
                    status=status.HTTP_404_NOT_FOUND,
                )

        chunks = []
        cursor_map = {}
        for spike in spikes:
            spike_id = str(spike.id)
            entry = spikes_data[spike_id]
            cursor = int(entry.get('cursor', 0))
            chunk = entry.get('chunk')
            label = _get_spike_label(spike)

            if chunk is not None:
                content = chunk
            else:
                full_log = _get_spike_log(spike)
                content = full_log[cursor:]

            chunks.append((label, content))
            cursor_map[spike_id] = (
                cursor + len(content) if content else cursor
            )

        result = merge_delta(chunks)
        result.cursors = cursor_map

        any_active = _any_spike_active(spikes)

        return Response(serialize_result(result, any_active))
