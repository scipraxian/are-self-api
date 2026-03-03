from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.models import IdentityDisc
from temporal_lobe.models import (
    Iteration,
    IterationShift,
    IterationShiftParticipant,
)
from temporal_lobe.serializers import IterationShiftDetailSerializer


class TemporalViewSet(viewsets.ViewSet):
    """
    Command Center API for the Temporal Lobe.
    Handles 3D topology generation and Shift runtime configurations.
    """

    @action(detail=False, methods=['get'])
    def graph_data(self, request):
        """Compiles the 3D visual graph of all runtime iterations and their shifts."""
        iterations = Iteration.objects.select_related(
            'status', 'current_shift'
        ).all()
        shifts = IterationShift.objects.select_related(
            'shift', 'definition', 'shift_iteration'
        ).all()

        nodes = []
        links = []

        # 1. Plot Iteration Hubs
        for it in iterations:
            nodes.append(
                {
                    'id': f'iter-{it.id}',
                    'name': it.name or f'Iteration {str(it.id)[:8]}',
                    'group': 'iteration',
                    'status': it.status.name if it.status else 'Unknown',
                    'is_root': True,
                }
            )

        # 2. Plot Shifts and Hub Links
        shift_map = {}
        for sh in shifts:
            node_id = f'shift-{sh.id}'
            is_active = sh.shift_iteration.current_shift_id == sh.id

            nodes.append(
                {
                    'id': node_id,
                    'name': sh.shift.name,
                    'group': 'shift',
                    'order': sh.definition.order,
                    'status': 'Running' if is_active else 'Waiting',
                    'is_root': False,
                    'db_id': str(sh.id),
                }
            )

            # Link Shift to its Parent Iteration Hub
            links.append(
                {
                    'source': f'iter-{sh.shift_iteration.id}',
                    'target': node_id,
                    'type': 'hub_link',
                }
            )

            # Group for sequential linking
            if sh.shift_iteration.id not in shift_map:
                shift_map[sh.shift_iteration.id] = []
            shift_map[sh.shift_iteration.id].append(sh)

        # 3. Plot Sequential Links
        for it_id, sh_list in shift_map.items():
            sh_list.sort(key=lambda x: x.definition.order)
            for i in range(len(sh_list) - 1):
                links.append(
                    {
                        'source': f'shift-{sh_list[i].id}',
                        'target': f'shift-{sh_list[i + 1].id}',
                        'type': 'sequence',
                    }
                )

        return Response({'nodes': nodes, 'links': links})

    @action(detail=False, methods=['get'], url_path=r'shift/(?P<pk>[^/.]+)')
    def shift_details(self, request, pk=None):
        """Fetches the state and participants for the right-hand inspector panel."""
        shift = get_object_or_404(IterationShift, pk=pk)
        serializer = IterationShiftDetailSerializer(shift)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['post'],
        url_path=r'shift/(?P<pk>[^/.]+)/participants',
    )
    def update_participants(self, request, pk=None):
        """Mutates the assigned Discs for a specific runtime shift."""
        shift = get_object_or_404(IterationShift, pk=pk)
        action_type = request.data.get('action')
        disc_id = request.data.get('disc_id')

        if not action_type or not disc_id:
            return Response(
                {'error': 'Missing action or disc_id'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        disc = get_object_or_404(IdentityDisc, pk=disc_id)

        if action_type == 'add':
            IterationShiftParticipant.objects.get_or_create(
                iteration_shift=shift, iteration_participant=disc
            )
        elif action_type == 'remove':
            IterationShiftParticipant.objects.filter(
                iteration_shift=shift, iteration_participant=disc
            ).delete()
        else:
            return Response(
                {'error': "Action must be 'add' or 'remove'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = IterationShiftDetailSerializer(shift)
        return Response(serializer.data)
