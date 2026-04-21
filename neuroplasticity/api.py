"""REST surface for the Modifier Garden.

List + detail GETs plus action endpoints that wrap the loader's
lifecycle operations. Each action emits an event via the loader, so the
event timeline stays the source of truth. After a successful lifecycle
call, the viewset fires an Acetylcholine so the frontend's NeuralModifier
dendrites refetch.
"""

from pathlib import Path

from asgiref.sync import async_to_sync
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from neuroplasticity import loader
from synaptic_cleft.axon_hillok import fire_neurotransmitter
from synaptic_cleft.neurotransmitters import Acetylcholine

from .models import NeuralModifier
from .serializers import (
    NeuralModifierDetailSerializer,
    NeuralModifierSerializer,
)


def _broadcast(modifier, action_name: str, slug: str = None) -> None:
    """Fire an Acetylcholine so the garden view refetches.

    `modifier` may be None for catalog-only events (delete/catalog_changed)
    where no DB row exists; pass `slug` so the vesicle still names the
    affected bundle.
    """
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
    """Persist a multipart-upload archive into the on-disk genomes dir.

    Reads the manifest out of the archive bytes to determine the slug,
    then writes ``genomes/<slug>.zip``. Refuses if a zip with that
    name already exists.
    """
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

    queryset = NeuralModifier.objects.all().order_by('slug')
    lookup_field = 'slug'
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NeuralModifierDetailSerializer
        return NeuralModifierSerializer

    @action(detail=False, methods=['post'], url_path='install')
    def install(self, request):
        """Install a bundle from an uploaded archive OR from an existing slug.

        - `archive` upload: saves the zip into the on-disk genomes dir
          under ``<slug>.zip`` and runs the archive-install flow.
        - `slug`: installs the already-committed ``genomes/<slug>.zip``.
        """
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
        try:
            deleted_slug = loader.uninstall_bundle(slug)
        except NeuralModifier.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # Under the AVAILABLE = no-DB-row ruling, uninstall deletes the
        # row — so there is no modifier object to serialize back to the
        # UI. Broadcast with slug-only and return a minimal payload.
        _broadcast(None, 'uninstall', slug=deleted_slug)
        return Response(
            {'slug': deleted_slug, 'uninstalled': True},
            status=status.HTTP_200_OK,
        )

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

    @action(detail=False, methods=['get'], url_path='catalog')
    def catalog(self, request):
        """One row per zip under the genomes root.

        Each entry is the unzipped manifest fields the UI needs to render
        an AVAILABLE row, plus an `installed` flag computed from a single
        bulk query against NeuralModifier.
        """
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
        """Remove a genome zip from disk. Refuses if a DB row exists.

        The garden page must call uninstall first; this only nukes the
        archive itself, returning the bundle to "gone" state.
        """
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
