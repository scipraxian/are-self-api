import json
import logging

from django_filters.rest_framework import DjangoFilterBackend
from djangorestframework_mcp.decorators import mcp_viewset
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .filters import SpikeFilter, SpikeTrainFilter
from .central_nervous_system import CNS
from .models import (
    Spike,
    SpikeTrain,
    Effector,
    NeuralPathway,
    Axon,
    Neuron,
    NeuronContext,
)
from .serializers import (
    CNSGraphLayoutSerializer,
    SpikeSerializer,
    NeuronDetailsSerializer,
    NeuronTelemetrySerializer,
    SpikeTrainCreateSerializer,
    SpikeTrainLightSerializer,
    SpikeTrainSerializer,
    SpikeTrainStatusSerializer,
    CNSNeuralPathwayConnectionWireSerializer,
    EffectorBookNodeContextSerializer,
    CNSNeuralPathwayNodeSerializer,
    CNSNeuralPathwaySerializer,
    EffectorSerializer,
)

logger = logging.getLogger(__name__)

# API Constants
CATEGORY_SPELLS = 'Spells'
CATEGORY_SUBGRAPHS = 'Sub-Graphs'
STATUS_OK = 'ok'


@mcp_viewset()
class EffectorViewSet(viewsets.ReadOnlyModelViewSet):
    """Registry of all available effectors."""

    queryset = (Effector.objects.all().select_related(
        'distribution_mode', 'talos_executable').order_by('name'))
    serializer_class = EffectorSerializer


@mcp_viewset()
class CNSNeuralPathwayViewSet(viewsets.ModelViewSet):
    """Library of available Protocols (NeuralPathways)."""

    queryset = NeuralPathway.objects.all().order_by('name')
    serializer_class = CNSNeuralPathwaySerializer
    filterset_fields = ['is_favorite']

    @action(detail=True, methods=['get'])
    def layout(self, request, pk=None):
        """Returns the flattened graph data for the Canvas Editor."""
        book = self.get_object()

        # Architectural Anchor: Enforce BeginPlay exists
        Neuron.objects.get_or_create(
            pathway=book,
            effector_id=Effector.BEGIN_PLAY,
            defaults={
                'is_root': True,
                'ui_json': json.dumps({
                    'x': 100,
                    'y': 100
                }),
            },
        )

        serializer = CNSGraphLayoutSerializer(book)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def library(self, request, pk=None):
        """Returns the combined palette of Effectors and Sub-graphs."""
        book = self.get_object()

        effectors = list(
            Effector.objects.values('id', 'name', 'distribution_mode__name'))
        for s in effectors:
            s['category'] = CATEGORY_SPELLS

        # Exclude self to prevent infinite recursion
        subgraphs = list(
            NeuralPathway.objects.exclude(id=book.id).values('id', 'name'))
        for b in subgraphs:
            b['category'] = CATEGORY_SUBGRAPHS
            b['is_book'] = True

        return Response({'library': effectors + subgraphs})

    @action(detail=True, methods=['post'])
    def toggle_favorite(self, request, pk=None):
        """Toggles the star status."""
        book = self.get_object()
        book.is_favorite = not book.is_favorite
        book.save(update_fields=['is_favorite'])
        return Response({'status': STATUS_OK, 'is_favorite': book.is_favorite})


@mcp_viewset()
class CNSNeuralPathwayNodeViewSet(viewsets.ModelViewSet):
    """Graph Nodes CRUD."""

    queryset = Neuron.objects.all()
    serializer_class = CNSNeuralPathwayNodeSerializer

    def perform_create(self, serializer):
        """Auto-flags the Begin Play node as root if applicable."""
        effector_id = self.request.data.get('effector')
        invoked_pathway_id = self.request.data.get('invoked_pathway')

        is_root = False
        if not invoked_pathway_id and int(effector_id) == Effector.BEGIN_PLAY:
            is_root = True

        serializer.save(is_root=is_root)

    def perform_destroy(self, instance):
        """Graph Protection: Cannot delete the core anchor node."""
        is_delegated = bool(instance.invoked_pathway_id)
        if not is_delegated and instance.effector_id == Effector.BEGIN_PLAY:
            raise ValidationError(
                'Cannot delete the core BeginPlay anchor node.')
        instance.delete()

    @action(detail=True, methods=['get'])
    def inspector_details(self, request, pk=None):
        """Returns the fully resolved variable context matrix for a node."""
        node = self.get_object()
        serializer = NeuronDetailsSerializer(node)
        return Response(serializer.data)


@mcp_viewset()
class CNSNeuralPathwayConnectionWireViewSet(mixins.CreateModelMixin,
                                            mixins.DestroyModelMixin,
                                            viewsets.GenericViewSet):
    """Graph Wires."""

    queryset = Axon.objects.all()
    serializer_class = CNSNeuralPathwayConnectionWireSerializer


class EffectorBookNodeContextViewSet(viewsets.ModelViewSet):
    """Manages variable overrides on specific neurons."""

    queryset = NeuronContext.objects.all()
    serializer_class = EffectorBookNodeContextSerializer
    filterset_fields = ['neuron']


class SpikeTrainViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        viewsets.GenericViewSet,
):
    """Mission Control and Spawns."""

    queryset = SpikeTrain.objects.all().select_related('status', 'pathway',
                                                       'environment')

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_class = SpikeTrainFilter
    ordering_fields = '__all__'
    ordering = ['-created']  # Default ordering
    search_fields = ['pathway__name', 'status__name']

    def get_serializer_class(self):
        if self.action == 'create':
            return SpikeTrainCreateSerializer
        elif self.action == 'list':
            return SpikeTrainLightSerializer
        return SpikeTrainSerializer

    def create(self, request, *args, **kwargs):
        """Launch Protocol."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pathway_id = serializer.validated_data['pathway_id']

        try:
            controller = CNS(pathway_id=pathway_id)
            controller.start()
            read_serializer = SpikeTrainSerializer(controller.spike_train)
            return Response(read_serializer.data,
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception(f'Failed to launch pathway {pathway_id}')
            return Response(
                {'error': f'Launch Failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'])
    def live_status(self, request, pk=None):
        """Fast-polling endpoint for the UI."""
        spike_train = self.get_object()
        serializer = SpikeTrainStatusSerializer(spike_train)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def spikes(self, request, pk=None):
        """Lightweight list of spikes for a spike_train."""
        spike_train = self.get_object()
        spikes = spike_train.spikes.all().order_by('created')
        serializer = SpikeSerializer(spikes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Graceful stop."""
        controller = CNS(spike_train_id=self.get_object().id)
        controller.stop_gracefully()
        return Response({'status': 'Stopping signaled.'})

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Hard Kill."""
        controller = CNS(spike_train_id=self.get_object().id)
        controller.terminate()
        return Response({'status': 'Termination complete.'})


@mcp_viewset()
class SpikeViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin,
                   viewsets.GenericViewSet):
    """Forensics Unit. Retrieves heavy telemetry/logs."""

    queryset = Spike.objects.all().select_related('status', 'effector',
                                                  'target')

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_class = SpikeFilter
    ordering_fields = '__all__'
    ordering = ['created']  # Default ordering for spikes (chronological)
    search_fields = ['effector__name', 'status__name', 'target__hostname']

    def get_serializer_class(self):
        if self.action == 'list':
            return SpikeSerializer
        return NeuronTelemetrySerializer

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Lightweight polling endpoint for the UI Spike Cards."""
        spike = self.get_object()
        serializer = SpikeSerializer(spike)
        return Response(serializer.data)
