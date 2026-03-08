from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import (
    Axon,
    Effector,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeTrain,
)
from central_nervous_system.serializers_v2 import (
    AxonSerializer,
    EffectorLightSerializer,
    NeuralPathwayDetailSerializer,
    NeuralPathwaySerializer,
    NeuronSerializer,
    SpikeDetailSerializer,
    SpikeTrainSerializer,
)


class SpikeTrainViewSetV2(viewsets.ModelViewSet):
    """
    CNS View (Swimlanes): Fetch running/historical sequences.
    """

    queryset = (
        SpikeTrain.objects.all()
        .select_related('status', 'pathway')
        .prefetch_related(
            'spikes', 'spikes__status', 'spikes__effector', 'spikes__target'
        )
        .order_by('-created')
    )

    serializer_class = SpikeTrainSerializer

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

    queryset = Spike.objects.all()
    serializer_class = SpikeDetailSerializer


class NeuralPathwayViewSetV2(viewsets.ModelViewSet):
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


class NeuronViewSetV2(viewsets.ModelViewSet):
    """
    React Canvas Hook: Directly mutate Nodes (Neurons)
    e.g., PATCH {"ui_json": "{\"x\": 250, \"y\": 150}"}
    """

    queryset = Neuron.objects.all()
    serializer_class = NeuronSerializer


class AxonViewSetV2(viewsets.ModelViewSet):
    """
    React Canvas Hook: Directly mutate Edges (Wires)
    """

    queryset = Axon.objects.all()
    serializer_class = AxonSerializer


class EffectorViewSetV2(viewsets.ReadOnlyModelViewSet):
    """
    Editor Palette: The actionable toolsets to drag onto the canvas.
    """

    queryset = Effector.objects.all().order_by('name')
    serializer_class = EffectorLightSerializer
