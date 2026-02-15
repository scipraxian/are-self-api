import json
import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .filters import HydraHeadFilter, HydraSpawnFilter
from .hydra import Hydra
from .models import (
    HydraHead,
    HydraSpawn,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraSpellBookNodeContext,
)
from .serializers import (
    HydraGraphLayoutSerializer,
    HydraHeadSerializer,
    HydraNodeDetailsSerializer,
    HydraNodeTelemetrySerializer,
    HydraSpawnCreateSerializer,
    HydraSpawnLightSerializer,
    HydraSpawnSerializer,
    HydraSpawnStatusSerializer,
    HydraSpellbookConnectionWireSerializer,
    HydraSpellBookNodeContextSerializer,
    HydraSpellbookNodeSerializer,
    HydraSpellbookSerializer,
    HydraSpellSerializer,
)

logger = logging.getLogger(__name__)


# API Constants
CATEGORY_SPELLS = 'Spells'
CATEGORY_SUBGRAPHS = 'Sub-Graphs'
STATUS_OK = 'ok'


class HydraSpellViewSet(viewsets.ReadOnlyModelViewSet):
    """Registry of all available spells."""

    queryset = (
        HydraSpell.objects.all()
        .select_related('distribution_mode', 'talos_executable')
        .order_by('name')
    )
    serializer_class = HydraSpellSerializer


class HydraSpellbookViewSet(viewsets.ModelViewSet):
    """Library of available Protocols (Spellbooks)."""

    queryset = HydraSpellbook.objects.all().order_by('name')
    serializer_class = HydraSpellbookSerializer
    filterset_fields = ['is_favorite']

    @action(detail=True, methods=['get'])
    def layout(self, request, pk=None):
        """Returns the flattened graph data for the Canvas Editor."""
        book = self.get_object()

        # Architectural Anchor: Enforce BeginPlay exists
        HydraSpellbookNode.objects.get_or_create(
            spellbook=book,
            spell_id=HydraSpell.BEGIN_PLAY,
            defaults={
                'is_root': True,
                'ui_json': json.dumps({'x': 100, 'y': 100}),
            },
        )

        serializer = HydraGraphLayoutSerializer(book)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def library(self, request, pk=None):
        """Returns the combined palette of Spells and Sub-graphs."""
        book = self.get_object()

        spells = list(
            HydraSpell.objects.values('id', 'name', 'distribution_mode__name')
        )
        for s in spells:
            s['category'] = CATEGORY_SPELLS

        # Exclude self to prevent infinite recursion
        subgraphs = list(
            HydraSpellbook.objects.exclude(id=book.id).values('id', 'name')
        )
        for b in subgraphs:
            b['category'] = CATEGORY_SUBGRAPHS
            b['is_book'] = True

        return Response({'library': spells + subgraphs})

    @action(detail=True, methods=['post'])
    def toggle_favorite(self, request, pk=None):
        """Toggles the star status."""
        book = self.get_object()
        book.is_favorite = not book.is_favorite
        book.save(update_fields=['is_favorite'])
        return Response({'status': STATUS_OK, 'is_favorite': book.is_favorite})


class HydraSpellbookNodeViewSet(viewsets.ModelViewSet):
    """Graph Nodes CRUD."""

    queryset = HydraSpellbookNode.objects.all()
    serializer_class = HydraSpellbookNodeSerializer

    def perform_create(self, serializer):
        """Auto-flags the Begin Play node as root if applicable."""
        spell_id = self.request.data.get('spell')
        invoked_book_id = self.request.data.get('invoked_spellbook')

        is_root = False
        if not invoked_book_id and int(spell_id) == HydraSpell.BEGIN_PLAY:
            is_root = True

        serializer.save(is_root=is_root)

    def perform_destroy(self, instance):
        """Graph Protection: Cannot delete the core anchor node."""
        is_delegated = bool(instance.invoked_spellbook_id)
        if not is_delegated and instance.spell_id == HydraSpell.BEGIN_PLAY:
            raise ValidationError(
                'Cannot delete the core BeginPlay anchor node.'
            )
        instance.delete()

    @action(detail=True, methods=['get'])
    def inspector_details(self, request, pk=None):
        """Returns the fully resolved variable context matrix for a node."""
        node = self.get_object()
        serializer = HydraNodeDetailsSerializer(node)
        return Response(serializer.data)


class HydraSpellbookConnectionWireViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Graph Wires."""

    queryset = HydraSpellbookConnectionWire.objects.all()
    serializer_class = HydraSpellbookConnectionWireSerializer


class HydraSpellBookNodeContextViewSet(viewsets.ModelViewSet):
    """Manages variable overrides on specific nodes."""

    queryset = HydraSpellBookNodeContext.objects.all()
    serializer_class = HydraSpellBookNodeContextSerializer
    filterset_fields = ['node']


class HydraSpawnViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Mission Control and Spawns."""

    queryset = HydraSpawn.objects.all().select_related(
        'status', 'spellbook', 'environment'
    )

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_class = HydraSpawnFilter
    ordering_fields = '__all__'
    ordering = ['-created']  # Default ordering
    search_fields = ['spellbook__name', 'status__name']

    def get_serializer_class(self):
        if self.action == 'create':
            return HydraSpawnCreateSerializer
        elif self.action == 'list':
            return HydraSpawnLightSerializer
        return HydraSpawnSerializer

    def create(self, request, *args, **kwargs):
        """Launch Protocol."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book_id = serializer.validated_data['spellbook_id']

        try:
            controller = Hydra(spellbook_id=book_id)
            controller.start()
            read_serializer = HydraSpawnSerializer(controller.spawn)
            return Response(
                read_serializer.data, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.exception(f'Failed to launch spellbook {book_id}')
            return Response(
                {'error': f'Launch Failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'])
    def live_status(self, request, pk=None):
        """Fast-polling endpoint for the UI."""
        spawn = self.get_object()
        serializer = HydraSpawnStatusSerializer(spawn)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def heads(self, request, pk=None):
        """Lightweight list of heads for a spawn."""
        spawn = self.get_object()
        heads = spawn.heads.all().order_by('created')
        serializer = HydraHeadSerializer(heads, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Graceful stop."""
        controller = Hydra(spawn_id=self.get_object().id)
        controller.stop_gracefully()
        return Response({'status': 'Stopping signaled.'})

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Hard Kill."""
        controller = Hydra(spawn_id=self.get_object().id)
        controller.terminate()
        return Response({'status': 'Termination complete.'})


class HydraHeadViewSet(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """Forensics Unit. Retrieves heavy telemetry/logs."""

    queryset = HydraHead.objects.all().select_related(
        'status', 'spell', 'target'
    )

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_class = HydraHeadFilter
    ordering_fields = '__all__'
    ordering = ['created']  # Default ordering for heads (chronological)
    search_fields = ['spell__name', 'status__name', 'target__hostname']

    def get_serializer_class(self):
        if self.action == 'list':
            return HydraHeadSerializer
        return HydraNodeTelemetrySerializer

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Lightweight polling endpoint for the UI Head Cards."""
        head = self.get_object()
        serializer = HydraHeadSerializer(head)
        return Response(serializer.data)
