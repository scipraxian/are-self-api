"""REST surface for the Modifier Garden.

List + detail GETs plus action endpoints that wrap the loader's
lifecycle operations. Each action emits an event via the loader, so the
event timeline stays the source of truth. After a successful lifecycle
call, the viewset fires an Acetylcholine so the frontend's NeuralModifier
dendrites refetch.
"""

from asgiref.sync import async_to_sync
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from neuroplasticity import loader
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine

from .models import NeuralModifier
from .serializers import (
    NeuralModifierDetailSerializer,
    NeuralModifierSerializer,
)


def _broadcast(modifier: NeuralModifier, action_name: str) -> None:
    """Fire an Acetylcholine so the garden view refetches."""
    async_to_sync(fire_neurotransmitter)(
        Acetylcholine(
            receptor_class='NeuralModifier',
            dendrite_id=str(modifier.pk) if modifier is not None else None,
            activity='updated',
            vesicle={
                'action': action_name,
                'slug': modifier.slug if modifier is not None else None,
            },
        )
    )


class NeuralModifierViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset; mutations flow through action endpoints."""

    queryset = NeuralModifier.objects.all().order_by('slug')
    lookup_field = 'slug'
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NeuralModifierDetailSerializer
        return NeuralModifierSerializer

    @action(detail=False, methods=['post'], url_path='install')
    def install(self, request):
        """Install a bundle from an uploaded archive OR from an existing slug."""
        archive = request.FILES.get('archive')
        slug = request.data.get('slug')
        try:
            if archive is not None:
                modifier = loader.install_bundle_from_archive(archive)
            elif slug:
                modifier = loader.install_bundle(slug)
            else:
                return Response(
                    {'detail': 'Provide either archive upload or slug.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except FileExistsError as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_409_CONFLICT
            )
        except FileNotFoundError as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        _broadcast(modifier, 'install')
        return Response(NeuralModifierDetailSerializer(modifier).data)

    @action(detail=True, methods=['post'], url_path='uninstall')
    def uninstall(self, request, slug=None):
        try:
            modifier = loader.uninstall_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _broadcast(modifier, 'uninstall')
        return Response(NeuralModifierDetailSerializer(modifier).data)

    @action(detail=True, methods=['post'], url_path='enable')
    def enable(self, request, slug=None):
        try:
            modifier = loader.enable_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _broadcast(modifier, 'enable')
        return Response(NeuralModifierSerializer(modifier).data)

    @action(detail=True, methods=['post'], url_path='disable')
    def disable(self, request, slug=None):
        try:
            modifier = loader.disable_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _broadcast(modifier, 'disable')
        return Response(NeuralModifierSerializer(modifier).data)

    @action(detail=True, methods=['get'], url_path='impact')
    def impact(self, request, slug=None):
        """Contribution-count breakdown by ContentType for uninstall preview."""
        try:
            return Response(loader.bundle_impact(slug))
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
