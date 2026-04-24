"""REST surface for the Modifier Garden.

List + detail GETs plus action endpoints that wrap the loader's
lifecycle operations. Each action emits an event via the loader, so the
event timeline stays the source of truth. After a successful lifecycle
call, the viewset fires an Acetylcholine so the frontend's NeuralModifier
dendrites refetch.

API is 100% standalone — endpoints return raw JSON state. A dumb UI
consumes what we emit; this module does not know the UI exists.
"""

from pathlib import Path

from asgiref.sync import async_to_sync
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from neuroplasticity import graph_walker, loader
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine

from .models import NeuralModifier
from .serializers import (
    NeuralModifierDetailSerializer,
    NeuralModifierSerializer,
)


def _broadcast(modifier, action_name: str, slug: str = None) -> None:
    """Fire an Acetylcholine so the garden view refetches."""
    if modifier is not None:
        dendrite_id = str(modifier.pk)
        bundle_slug = modifier.slug
    else:
        dendrite_id = None
        bundle_slug = slug
    async_to_sync(fire_neurotransmitter)(
        Acetylcholine(
            receptor_class='NeuralModifier',
            dendrite_id=dendrite_id,
            activity='updated',
            vesicle={
                'action': action_name,
                'slug': bundle_slug,
            },
        )
    )


def _save_upload_to_catalog(uploaded_file) -> Path:
    """Persist a multipart-upload archive into the on-disk genomes dir."""
    import io
    import zipfile

    catalog = loader.genomes_root()
    catalog.mkdir(parents=True, exist_ok=True)

    data = uploaded_file.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        top = sorted({n.split('/', 1)[0] for n in names if n.strip('/')})
        if not top:
            raise ValueError('[Neuroplasticity] Uploaded archive is empty.')
        if len(top) != 1:
            raise ValueError(
                '[Neuroplasticity] Uploaded archive must contain a single '
                'top-level directory; got {0}.'.format(top)
            )
        manifest_name = '{0}/manifest.json'.format(top[0])
        if manifest_name not in names:
            raise ValueError(
                '[Neuroplasticity] Uploaded archive missing {0}.'.format(
                    manifest_name
                )
            )
        import json as _json
        manifest = _json.loads(zf.read(manifest_name).decode('utf-8'))
    slug = manifest.get('slug')
    if not slug:
        raise ValueError(
            '[Neuroplasticity] Uploaded archive manifest missing slug.'
        )
    target = catalog / '{0}.zip'.format(slug)
    if target.exists():
        raise FileExistsError(
            '[Neuroplasticity] Catalog already contains {0}.zip; delete '
            'the existing entry first.'.format(slug)
        )
    target.write_bytes(data)
    return target


class NeuralModifierViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset; mutations flow through action endpoints."""

    lookup_field = 'slug'
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        # Canonical is a system-tier row — it owns every core fixture row
        # but cannot be installed, uninstalled, enabled, disabled, saved,
        # or graphed. Excluding it here makes every routed action
        # (list, retrieve, and every @action routed through _visible_or_404)
        # invisible.
        return NeuralModifier.objects.exclude(
            pk=NeuralModifier.CANONICAL
        ).order_by('slug')

    def _visible_or_404(self):
        """Return a 404 Response when the slug is canonical or missing.

        Detail actions call this at the top so the queryset exclusion is
        the single source of truth for which slugs are addressable.
        Returns ``None`` when the object is visible; the action then
        proceeds with the original slug kwarg.
        """
        try:
            self.get_object()
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return None

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NeuralModifierDetailSerializer
        return NeuralModifierSerializer

    def retrieve(self, request, *args, **kwargs):
        # Mirror the @action handler pattern — convert Http404 to an
        # explicit DRF Response(404) so an unhandled Http404 can't
        # escape to Django's default 404 handler (which returns a
        # TemplateResponse without ``accepted_renderer`` set).
        try:
            instance = self.get_object()
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='install')
    def install(self, request):
        """Install a bundle from an uploaded archive OR from an existing slug."""
        archive = request.FILES.get('archive')
        slug = request.data.get('slug')
        try:
            if archive is not None:
                archive_path = _save_upload_to_catalog(archive)
                modifier = loader.install_bundle_from_archive(archive_path)
            elif slug:
                archive_path = loader.genomes_root() / '{0}.zip'.format(slug)
                modifier = loader.install_bundle_from_archive(archive_path)
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
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            deleted_slug = loader.uninstall_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _broadcast(None, 'uninstall', slug=deleted_slug)
        return Response(
            {'slug': deleted_slug, 'uninstalled': True},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='enable')
    def enable(self, request, slug=None):
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            modifier = loader.enable_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _broadcast(modifier, 'enable')
        return Response(NeuralModifierSerializer(modifier).data)

    @action(detail=True, methods=['post'], url_path='disable')
    def disable(self, request, slug=None):
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            modifier = loader.disable_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _broadcast(modifier, 'disable')
        return Response(NeuralModifierSerializer(modifier).data)

    @action(detail=True, methods=['get'], url_path='impact')
    def impact(self, request, slug=None):
        """Legacy alias for ``uninstall-preview``.

        Kept wired so older clients stay functional; new callers should
        hit ``/uninstall-preview/`` directly. Payload shape matches
        :func:`loader.bundle_uninstall_preview` (direct / cascade /
        set_null / protected tree).
        """
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            return Response(loader.bundle_uninstall_preview(slug))
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['get'], url_path='uninstall-preview')
    def uninstall_preview(self, request, slug=None):
        """Cascade tree Django-admin-style for the uninstall dialog.

        Returns the full reach of ``modifier.delete()``: rows the
        bundle directly owns, rows Django's Collector walks via
        CASCADE, rows whose FK gets nulled (SET_NULL), and any rows
        that would PROTECT-block the delete. The UI renders the whole
        tree so Michael can SEE everything that disappears.
        """
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            return Response(loader.bundle_uninstall_preview(slug))
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='save')
    def save_to_genome(self, request, slug=None):
        """Serialize owned rows + graft code back into ``genomes/<slug>.zip``.

        Atomically replaces the on-disk archive. Returns bytes written,
        row count, and the absolute zip path. Fires Acetylcholine so
        subscribers re-sync.
        """
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            result = loader.save_bundle_to_archive(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        modifier = NeuralModifier.objects.get(slug=slug)
        _broadcast(modifier, 'save')
        return Response(result)

    @action(detail=True, methods=['get'], url_path='graph')
    def graph(self, request, slug=None):
        """Forward-FK graph of bundle-owned rows + reachable neighbours.

        Each reachable row is tagged with one of: ``owned`` / ``shared-with
        <slug>`` / ``orphan`` / ``core``. Walker is API-only.
        """
        missing = self._visible_or_404()
        if missing is not None:
            return missing
        try:
            return Response(graph_walker.build_bundle_graph(slug))
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='catalog')
    def catalog(self, request):
        """One row per zip under the genomes root."""
        entries = loader.read_catalog_manifests()
        slugs = [e['manifest'].get('slug') for e in entries]
        installed_slugs = set(
            NeuralModifier.objects.filter(slug__in=slugs).values_list(
                'slug', flat=True
            )
        )
        payload = []
        for entry in entries:
            manifest = entry['manifest']
            slug = manifest.get('slug')
            payload.append(
                {
                    'slug': slug,
                    'name': manifest.get('name', slug),
                    'version': manifest.get('version', ''),
                    'author': manifest.get('author', ''),
                    'license': manifest.get('license', ''),
                    'description': manifest.get('description', ''),
                    'archive_name': entry['archive_name'],
                    'installed': slug in installed_slugs,
                }
            )
        return Response(payload)

    @action(
        detail=False,
        methods=['post'],
        url_path=r'catalog/(?P<catalog_slug>[^/.]+)/install',
    )
    def catalog_install(self, request, catalog_slug=None):
        """Install the genome zip whose manifest slug matches ``catalog_slug``."""
        archive_path = loader.genomes_root() / '{0}.zip'.format(catalog_slug)
        if not archive_path.exists():
            return Response(
                {'detail': 'No catalog archive for slug {0!r}.'.format(catalog_slug)},
                status=status.HTTP_404_NOT_FOUND,
            )
        if NeuralModifier.objects.filter(slug=catalog_slug).exists():
            return Response(
                {
                    'detail': 'Bundle {0!r} already installed; uninstall '
                    'first.'.format(catalog_slug)
                },
                status=status.HTTP_409_CONFLICT,
            )
        try:
            modifier = loader.install_bundle_from_archive(archive_path)
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

    @action(
        detail=False,
        methods=['post'],
        url_path=r'catalog/(?P<catalog_slug>[^/.]+)/delete',
    )
    def catalog_delete(self, request, catalog_slug=None):
        """Remove a genome zip from disk. Refuses if a DB row exists."""
        archive_path = loader.genomes_root() / '{0}.zip'.format(catalog_slug)
        if NeuralModifier.objects.filter(slug=catalog_slug).exists():
            return Response(
                {'detail': 'Uninstall first, then delete.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not archive_path.exists():
            return Response(
                {'detail': 'No catalog archive for slug {0!r}.'.format(catalog_slug)},
                status=status.HTTP_404_NOT_FOUND,
            )
        archive_path.unlink()
        _broadcast(None, 'catalog_changed', slug=catalog_slug)
        return Response(
            {'slug': catalog_slug, 'deleted': True},
            status=status.HTTP_200_OK,
        )
