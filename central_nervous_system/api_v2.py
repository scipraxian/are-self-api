import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.filters import SpikeFilter, SpikeTrainFilter
from central_nervous_system.models import (
    Axon,
    CNSDistributionMode,
    Effector,
    EffectorArgumentAssignment,
    EffectorContext,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeTrain,
)
from central_nervous_system.serializers_v2 import (
    AxonSerializer,
    CNSDistributionModeSerializer,
    EffectorArgumentAssignmentSerializer,
    EffectorContextSerializer,
    EffectorDetailSerializer,
    EffectorLightSerializer,
    NeuralPathwayDetailSerializer,
    NeuralPathwaySerializer,
    NeuronSerializer,
    SpikeDetailSerializer,
    SpikeTrainSerializer,
)
from neuroplasticity.serializer_mixins import GenomeMoveRestartMixin


class SpikeTrainViewSetV2(viewsets.ModelViewSet):
    """
    CNS View (Swimlanes): Fetch running/historical sequences.
    """

    queryset = (
        SpikeTrain.objects.all()
        .select_related('status', 'pathway')
        .prefetch_related(
            'spikes',
            'spikes__status',
            'spikes__effector',
            'spikes__target',
            'spikes__neuron',
            'spikes__neuron__pathway',
            'spikes__neuron__invoked_pathway',
            'spikes__provenance__spike_train',
        )
        .order_by('-created')
    )

    serializer_class = SpikeTrainSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]
    filterset_class = SpikeTrainFilter
    ordering_fields = '__all__'

    @action(detail=False, methods=['post'])
    def launch(self, request):
        """Ignites the sequence."""
        pathway_id = request.data.get('pathway_id')
        try:
            controller = CNS(pathway_id=pathway_id)
            controller.start()
            serializer = self.get_serializer(controller.spike_train)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        controller = CNS(spike_train_id=self.get_object().id)
        controller.stop_gracefully()
        return Response({'status': 'Stopping signaled.'})

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        controller = CNS(spike_train_id=self.get_object().id)
        controller.terminate()
        return Response({'status': 'Termination complete.'})


class SpikeViewSetV2(viewsets.ReadOnlyModelViewSet):
    """Forensics & Telemetry: Fetch massive log payloads only when requested."""

    queryset = Spike.objects.all().select_related(
        'status', 'effector', 'target'
    )
    serializer_class = SpikeDetailSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = SpikeFilter
    ordering_fields = '__all__'


class NeuralPathwayViewSetV2(GenomeMoveRestartMixin, viewsets.ModelViewSet):
    """
    CNS Editor: If retrieving a list, gets light metadata.
    If retrieving one by ID, fetches the entire node/wire topology.
    """

    queryset = (
        NeuralPathway.objects.all()
        .prefetch_related(
            'tags',
            'neurons',
            'axons',
            'neurons__effector',
            'neurons__invoked_pathway',
            'axons__type',
        )
        .order_by('name')
    )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NeuralPathwayDetailSerializer
        return NeuralPathwaySerializer

    def perform_create(self, serializer):
        pathway = serializer.save()
        # Every new pathway gets a Begin Play root neuron automatically.
        # Mirror the pathway's genome so the auto-created neuron lands
        # in the same workspace bundle the user just created the pathway
        # under — otherwise it would default to INCUBATOR and diverge.
        Neuron.objects.create(
            pathway=pathway,
            effector_id=Effector.BEGIN_PLAY,
            is_root=True,
            ui_json='{"x": 100, "y": 200}',
            genome=pathway.genome,
        )

    @action(detail=True, methods=['post'])
    def toggle_favorite(self, request, pk=None):
        pathway = self.get_object()
        pathway.is_favorite = not pathway.is_favorite
        pathway.save(update_fields=['is_favorite'])
        return Response({'is_favorite': pathway.is_favorite})

    @action(detail=True, methods=['post'])
    def launch(self, request, pk=None):
        """Ignites the sequence."""
        pathway_id = self.get_object().id
        try:
            controller = CNS(pathway_id=pathway_id)
            controller.start()
            serializer = SpikeTrainSerializer(controller.spike_train)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def sample(self, request, pk=None):
        """
        Export this pathway as a portable fixture JSON.
        Objects already present in baseline fixtures are excluded.

        Query params:
            include_dependencies (bool, default true):
                Walk the Effector/Executable FK chain.
        """
        from central_nervous_system.sample_pathway import sample_pathway

        include_deps = (
            request.query_params.get('include_dependencies', 'true').lower()
            != 'false'
        )

        try:
            fixture = sample_pathway(
                str(pk), include_dependencies=include_deps
            )
        except NeuralPathway.DoesNotExist:
            return Response(
                {'error': 'Pathway not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        pathway = self.get_object()
        filename = f'{pathway.name.lower().replace(" ", "_")}_sample.json'

        response = HttpResponse(
            json.dumps(fixture, indent=2, ensure_ascii=False),
            content_type='application/json',
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{filename}"'
        )
        return response


class NeuronViewSetV2(GenomeMoveRestartMixin, viewsets.ModelViewSet):
    """
    React Canvas Hook: Directly mutate Nodes (Neurons)
    e.g., PATCH {"ui_json": "{\"x\": 250, \"y\": 150}"}
    """

    queryset = Neuron.objects.all()
    serializer_class = NeuronSerializer

    def destroy(self, request, *args, **kwargs):
        # Translate the model-level Begin-Play guard
        # (``Neuron.delete()`` raises ``django.core.exceptions.ValidationError``)
        # into a clean DRF 400. Other neurons delete normally.
        try:
            return super().destroy(request, *args, **kwargs)
        except DjangoValidationError as exc:
            detail = (
                exc.messages[0]
                if getattr(exc, 'messages', None)
                else str(exc)
            )
            return Response(
                {'detail': detail}, status=status.HTTP_400_BAD_REQUEST
            )


class AxonViewSetV2(GenomeMoveRestartMixin, viewsets.ModelViewSet):
    """
    React Canvas Hook: Directly mutate Edges (Wires)
    """

    queryset = Axon.objects.all()
    serializer_class = AxonSerializer


class EffectorViewSetV2(GenomeMoveRestartMixin, viewsets.ModelViewSet):
    """
    Effector CRUD: Light list for the palette, full detail for the editor.
    """

    queryset = (
        Effector.objects.all()
        .select_related('executable', 'distribution_mode')
        .prefetch_related(
            'switches',
            'tags',
            'effectorargumentassignment_set',
            'effectorargumentassignment_set__argument',
            'effectorcontext_set',
            'executable__switches',
            'executable__executableargumentassignment_set',
            'executable__executableargumentassignment_set__argument',
            'executable__executablesupplementaryfileorpath_set',
        )
        .order_by('name')
    )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EffectorDetailSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return EffectorDetailSerializer
        return EffectorLightSerializer


class EffectorContextViewSetV2(GenomeMoveRestartMixin, viewsets.ModelViewSet):
    """CRUD for EffectorContext key/value pairs."""

    queryset = EffectorContext.objects.all()
    serializer_class = EffectorContextSerializer
    filterset_fields = ['effector']


class EffectorArgumentAssignmentViewSetV2(
    GenomeMoveRestartMixin, viewsets.ModelViewSet
):
    """
    CRUD for the join table linking arguments to effectors (with order).
    Filterable by effector FK.
    """

    queryset = (
        EffectorArgumentAssignment.objects.all()
        .select_related('argument')
        .order_by('order')
    )
    serializer_class = EffectorArgumentAssignmentSerializer
    filterset_fields = ['effector']


class CNSDistributionModeViewSetV2(viewsets.ReadOnlyModelViewSet):
    """Lookup table for distribution modes."""

    queryset = CNSDistributionMode.objects.all().order_by('name')
    serializer_class = CNSDistributionModeSerializer
