from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from central_nervous_system.central_nervous_system import CNS
from identity.models import Identity, IdentityDisc
from temporal_lobe.models import (
    Iteration,
    IterationDefinition,
    IterationShift,
    IterationShiftDefinition,
    IterationShiftDefinitionParticipant,
    IterationShiftParticipant,
    IterationShiftParticipantStatus,
    IterationStatus,
    Shift,
)
from temporal_lobe.serializers import (
    IterationDefinitionSerializer,
    IterationSerializer,
    IterationShiftDefinitionSerializer,
    IterationShiftDetailSerializer,
    ShiftSerializer,
)
from temporal_lobe.temporal_lobe import (
    fetch_canonical_temporal_pathway,
    trigger_temporal_metronomes,
)


# DEPRECIATED
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

    @action(detail=False, methods=['post'])
    def trigger_tick(self, request):
        try:
            spawned_ids = trigger_temporal_metronomes()

            if not spawned_ids:
                return Response(
                    {'status': 'Standby', 'message': 'No active iterations.'},
                    status=status.HTTP_200_OK,
                )

            return Response(
                {
                    'status': 'Temporal Metronome Engaged',
                    'environments_triggered': len(spawned_ids),
                    'spike_train_ids': [str(uid) for uid in spawned_ids],
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class IterationViewSet(viewsets.ModelViewSet):
    """
    Command Center API for the Temporal Lobe Iterations.
    """

    queryset = (
        Iteration.objects.prefetch_related(
            'iterationshift_set__shift',
            'iterationshift_set__definition',
            'iterationshift_set__iterationshiftparticipant_set__iteration_participant',
        )
        .all()
        .order_by('-created')
    )

    serializer_class = IterationSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'], url_path='incept')
    def incept(self, request):
        """
        Triggers the IterationInceptionManager to build a new cycle from a blueprint.
        Expected payload: {"definition_id": 1, "environment_id": "optional-uuid"}
        """
        definition_id = request.data.get('definition_id')
        environment_id = request.data.get('environment_id')

        if not definition_id:
            return Response(
                {'error': 'definition_id is required for inception.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from temporal_lobe.inception import IterationInceptionManager

        try:
            # Trigger the biological engine
            iteration = IterationInceptionManager.incept_iteration(
                definition_id=definition_id, environment_id=environment_id
            )

            # Use your existing serializer to return the fully hydrated board
            serializer = self.get_serializer(iteration)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'Inception failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['post'], url_path='slot_disc')
    def slot_disc(self, request, pk=None):
        iteration = self.get_object()
        shift_id = request.data.get('shift_id')
        disc_id = request.data.get('disc_id')
        base_id = request.data.get('base_id')

        if not shift_id:
            return Response(
                {'error': 'shift_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shift = get_object_or_404(
            IterationShift, id=shift_id, shift_iteration=iteration
        )

        if base_id:
            from identity.forge import forge_identity_disc
            from identity.models import Identity

            base_identity = get_object_or_404(Identity, id=base_id)
            identity_disc = forge_identity_disc(base_identity)
        elif disc_id:
            identity_disc = get_object_or_404(IdentityDisc, id=disc_id)
            if not identity_disc.available:
                return Response(
                    {'error': 'Disc is offline.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {'error': 'disc_id or base_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        status_selected, _ = (
            IterationShiftParticipantStatus.objects.get_or_create(
                id=1, defaults={'name': 'Selected'}
            )
        )

        IterationShiftParticipant.objects.get_or_create(
            iteration_shift=shift,
            iteration_participant=identity_disc,
            defaults={'status': status_selected},
        )

        # CRITICAL FIX: Re-fetch the Iteration to bust the stale prefetch cache!
        fresh_iteration = self.get_queryset().get(pk=iteration.pk)
        return Response(
            self.get_serializer(fresh_iteration).data, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], url_path='remove_disc')
    def remove_disc(self, request, pk=None):
        """Fires a worker from a shift and returns them to the Barracks."""
        iteration = self.get_object()
        shift_id = request.data.get('shift_id')
        disc_id = request.data.get('disc_id')

        if not shift_id or not disc_id:
            return Response(
                {'error': 'shift_id and disc_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shift = get_object_or_404(
            IterationShift, id=shift_id, shift_iteration=iteration
        )
        identity_disc = get_object_or_404(IdentityDisc, id=disc_id)

        IterationShiftParticipant.objects.filter(
            iteration_shift=shift, iteration_participant=identity_disc
        ).delete()

        # CRITICAL FIX: Re-fetch the Iteration to bust the stale prefetch cache!
        fresh_iteration = self.get_queryset().get(pk=iteration.pk)
        return Response(
            self.get_serializer(fresh_iteration).data, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], url_path='initiate')
    def initiate(self, request, pk=None):
        """
        Flips the Iteration to RUNNING and wakes up the Temporal Metronome.
        """
        iteration = self.get_object()

        if iteration.status.name != 'Waiting':
            return Response(
                {'error': 'Already running or finished.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Flip the status
        from temporal_lobe.models import IterationStatus

        status_running, _ = IterationStatus.objects.get_or_create(
            id=2, defaults={'name': 'Running'}
        )
        iteration.status = status_running
        iteration.save(update_fields=['status'])

        # 2. Kick the Metronome manually
        from temporal_lobe.temporal_lobe import trigger_temporal_metronomes

        trigger_temporal_metronomes()

        # Re-fetch cache and return updated board
        fresh_iteration = self.get_queryset().get(pk=iteration.pk)
        return Response(
            self.get_serializer(fresh_iteration).data, status=status.HTTP_200_OK
        )


class ShiftViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only reference data for the 6 shift types."""

    queryset = Shift.objects.all().order_by('id')
    serializer_class = ShiftSerializer
    permission_classes = [AllowAny]


class IterationDefinitionViewSet(viewsets.ModelViewSet):
    """Provides the UI with the available blueprints for Inception. Supports editing
    definition participants (slot_disc / remove_disc) and incepting a new iteration.
    """

    permission_classes = [AllowAny]
    queryset = IterationDefinition.objects.prefetch_related(
        'iterationshiftdefinition_set__shift',
        'iterationshiftdefinition_set__iterationshiftdefinitionparticipant_set__identity_disc',
    ).all()
    serializer_class = IterationDefinitionSerializer

    def perform_create(self, serializer: IterationDefinitionSerializer) -> None:
        """Auto-populate one IterationShiftDefinition per Shift type."""
        definition = serializer.save()
        shifts = Shift.objects.all().order_by('id')
        for i, shift in enumerate(shifts):
            IterationShiftDefinition.objects.create(
                definition=definition,
                shift=shift,
                order=i,
                turn_limit=shift.default_turn_limit,
            )

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Re-fetch with prefetch to include the new shift definitions
        fresh = self.get_queryset().get(pk=serializer.instance.pk)
        return Response(
            self.get_serializer(fresh).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='incept')
    def incept(self, request, pk=None):
        """
        Triggers the IterationInceptionManager to build a new cycle from this blueprint.
        Payload: {"environment_id": "optional-uuid", "custom_name": "optional"}.
        """
        definition = self.get_object()
        environment_id = request.data.get('environment_id')
        custom_name = request.data.get('custom_name')

        from temporal_lobe.inception import IterationInceptionManager

        try:
            iteration = IterationInceptionManager.incept_iteration(
                definition_id=definition.id,
                environment_id=environment_id,
                custom_name=custom_name,
            )
            # Re-fetch with same prefetch as IterationViewSet for full payload
            fresh = Iteration.objects.prefetch_related(
                'iterationshift_set__shift',
                'iterationshift_set__definition',
                'iterationshift_set__iterationshiftparticipant_set__iteration_participant',
            ).get(pk=iteration.pk)
            return Response(
                IterationSerializer(fresh).data, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': f'Inception failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['post'], url_path='slot_disc')
    def slot_disc(self, request, pk=None):
        """
        Add a participant to a shift in the blueprint. Payload: shift_definition_id,
        and disc_id or base_id (Identity). If base_id, a new Disc is gestated and
        stored. Same contract as
        IterationViewSet.slot_disc but for the definition.
        """
        definition = self.get_object()
        shift_definition_id = request.data.get('shift_definition_id')
        disc_id = request.data.get('disc_id')
        base_id = request.data.get('base_id')

        if not shift_definition_id:
            return Response(
                {'error': 'shift_definition_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shift_def = get_object_or_404(
            IterationShiftDefinition,
            id=shift_definition_id,
            definition=definition,
        )

        if base_id:
            from identity.forge import forge_identity_disc

            identity = get_object_or_404(Identity, id=base_id)
            disc = forge_identity_disc(identity)
        elif disc_id:
            disc = get_object_or_404(IdentityDisc, id=disc_id)
        else:
            return Response(
                {'error': 'disc_id or base_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        IterationShiftDefinitionParticipant.objects.get_or_create(
            shift_definition=shift_def,
            identity_disc=disc,
        )

        fresh_definition = self.get_queryset().get(pk=definition.pk)
        return Response(
            self.get_serializer(fresh_definition).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='remove_disc')
    def remove_disc(self, request, pk=None):
        """
        Remove a participant from a shift in the blueprint. Payload: shift_definition_id,
        and disc_id to identify the participant (IdentityDisc). Same contract
        as IterationViewSet.remove_disc but for the definition.
        """
        definition = self.get_object()
        shift_definition_id = request.data.get('shift_definition_id')
        disc_id = request.data.get('disc_id')
        base_id = request.data.get('base_id')

        if not shift_definition_id:
            return Response(
                {'error': 'shift_definition_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if base_id:
            identity = get_object_or_404(Identity, id=base_id)
        elif disc_id:
            disc = get_object_or_404(IdentityDisc, id=disc_id)
        else:
            return Response(
                {'error': 'disc_id or base_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shift_def = get_object_or_404(
            IterationShiftDefinition,
            id=shift_definition_id,
            definition=definition,
        )

        qs = IterationShiftDefinitionParticipant.objects.filter(
            shift_definition=shift_def,
        )
        if disc_id:
            qs = qs.filter(identity_disc=disc)

        qs.delete()

        fresh_definition = self.get_queryset().get(pk=definition.pk)
        return Response(
            self.get_serializer(fresh_definition).data,
            status=status.HTTP_200_OK,
        )


class IterationShiftDefinitionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing IterationShiftDefinition objects.
    """

    queryset = (
        IterationShiftDefinition.objects.select_related('definition', 'shift')
        .prefetch_related(
            'iterationshiftdefinitionparticipant_set__identity_disc'
        )
        .all()
    )

    serializer_class = IterationShiftDefinitionSerializer
    permission_classes = [AllowAny]
