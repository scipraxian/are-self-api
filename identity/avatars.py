"""Avatar persistence + API surface for Identity / IdentityDisc.

Avatars are catalog rows on a small genome-owned model
(``Avatar`` in ``identity/models.py``). The catalog travels with the
bundle that ships it — Nano pack and HSH-aliens pack each contribute
their own rows. ``Identity`` and ``IdentityDisc`` carry a nullable
FK at ``avatar``; blueprint defines, disc may override.

Four shapes via ``AvatarSelectedDisplayType``:

* ``GENERATED`` (default) — no stored bytes; the frontend renders a
  Kandinsky-style abstract from the disc's composite vector
  (identity vector + sum of engram vectors, normalized) at fetch
  time. Always available because every disc has a vector.
* ``FILE`` — bytes live at
  ``neuroplasticity/grafts/<genome.slug>/media/<stored_filename>``.
  POST/PATCH on this viewset accepts an ``image`` multipart field
  and writes through to that path before saving the row.
* ``URL`` — externally-hosted image; the row stores the URL only.
* ``EMOJI`` — a glyph (multi-codepoint OK) tinted with
  ``tint_color`` if set.

Canonical genome cannot accept ``FILE`` uploads — it has no graft
tree to write into. ``GenomeWritableMixin`` already refuses every
API write that targets canonical, so this is enforced uniformly
without an Avatar-specific rule. Canonical Avatar rows arrive only
via fixtures and must use GENERATED / URL / EMOJI.
"""

from __future__ import annotations

import os

from rest_framework import serializers, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from common.constants import ALL_FIELDS
from neuroplasticity.serializer_mixins import (
    GenomeDisplayMixin,
    GenomeMoveRestartMixin,
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
)

from identity.avatar_storage import avatar_media_dir
from identity.models import Avatar, AvatarSelectedDisplayType


__all__ = (
    'AvatarNestingMixin',
    'AvatarSelectedDisplayTypeSerializer',
    'AvatarSelectedDisplayTypeViewSet',
    'AvatarSerializer',
    'AvatarViewSet',
    'avatar_media_dir',
)


class AvatarNestingMixin:
    """Read-side mixin: replaces the auto-generated ``avatar`` UUID on
    serializer output with the full nested ``AvatarSerializer.data`` so
    the UI can render avatar tiles without a follow-up fetch.

    Write contract is unchanged — the auto-generated
    ``PrimaryKeyRelatedField`` for ``avatar`` still accepts a UUID on
    POST/PATCH. This is read augmentation only. When the source
    instance has ``avatar=None``, the field stays ``None``; when the
    serializer doesn't expose an ``avatar`` key at all, the dict is
    returned untouched.
    """

    def to_representation(self, instance):
        data = super().to_representation(instance)
        avatar = getattr(instance, 'avatar', None)
        if avatar is not None and 'avatar' in data:
            data['avatar'] = AvatarSerializer(
                avatar, context=self.context,
            ).data
        return data


class AvatarSelectedDisplayTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvatarSelectedDisplayType
        fields = ALL_FIELDS


class AvatarSerializer(
    GenomeOwnedSerializerMixin,
    GenomeWritableMixin,
    GenomeDisplayMixin,
    serializers.ModelSerializer,
):
    """V2 serializer for Avatar.

    The layered Genome mixins handle:
      * ``genome_slug`` read-only mirror (``GenomeDisplayMixin``)
      * ``genome`` defaulted on create from ``selected_for_edit``
        (``GenomeOwnedSerializerMixin``)
      * ``genome`` writable with canonical-refusal on PATCH
        (``GenomeWritableMixin``)

    The companion ``AvatarViewSet`` accepts an ``image`` multipart
    field on create / partial_update and writes the bytes through to
    the genome's graft tree before saving the row. The serializer
    deliberately does NOT declare an ``image`` field; routing the
    upload through DRF's ``FileField`` would couple us to Django's
    storage system and we want bytes flowing directly into the
    graft tree.
    """

    display = AvatarSelectedDisplayTypeSerializer(read_only=True)
    display_id = serializers.PrimaryKeyRelatedField(
        source='display',
        queryset=AvatarSelectedDisplayType.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Avatar
        fields = ALL_FIELDS


class AvatarSelectedDisplayTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Protocol-enum surface — the four display kinds (GENERATED, FILE,
    URL, EMOJI) are referenced from code by integer PK and must not be
    mutated at runtime.
    """

    queryset = AvatarSelectedDisplayType.objects.all().order_by('id')
    serializer_class = AvatarSelectedDisplayTypeSerializer


class AvatarViewSet(GenomeMoveRestartMixin, viewsets.ModelViewSet):
    """V2 viewset for Avatar with multipart upload support.

    A POST or PATCH with ``Content-Type: multipart/form-data`` and an
    ``image`` field will write the file's bytes to the genome's graft
    tree at ``<grafts_root>/<genome.slug>/media/<stored_filename>``,
    where ``stored_filename`` is ``<row.id>.<ext>`` to avoid
    collisions across rows in the same genome, and
    ``original_filename`` preserves whatever the uploader called it.

    Refusal layering:
      * ``GenomeWritableMixin`` already refuses canonical-as-target on
        the ``genome`` field, so a multipart upload bound for
        canonical fails before reaching the file-write step.
      * If an ``image`` part is present but the row's ``display`` is
        not ``FILE``, the file is silently ignored (the row was
        not asking for bytes).
      * If ``display=FILE`` is created without an ``image`` part,
        the row is created with ``stored_filename=NULL`` and is
        treated as ready to receive bytes via a subsequent PATCH.
    """

    queryset = Avatar.objects.all().order_by('name')
    serializer_class = AvatarSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        if self._handle_uploaded_image(instance, request):
            instance = Avatar.objects.get(pk=instance.pk)
        return Response(
            self.get_serializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        instance = self.get_object()
        if self._handle_uploaded_image(instance, request):
            instance = Avatar.objects.get(pk=instance.pk)
            response.data = self.get_serializer(instance).data
        return response

    def _handle_uploaded_image(self, instance: Avatar, request) -> bool:
        """Write any uploaded ``image`` bytes through to the genome's graft.

        Returns ``True`` if a file was written (and the row was
        updated with ``original_filename`` / ``stored_filename``);
        ``False`` otherwise. Quietly no-ops when there is no
        ``image`` part or the row's ``display`` is not ``FILE``.
        """
        uploaded = request.FILES.get('image') if request.FILES else None
        if uploaded is None:
            return False
        if instance.display_id != AvatarSelectedDisplayType.FILE:
            return False
        target_dir = avatar_media_dir(instance.genome)
        target_dir.mkdir(parents=True, exist_ok=True)
        original_name = uploaded.name or ''
        ext = os.path.splitext(original_name)[1].lower()
        stored_name = f'{instance.id}{ext}' if ext else str(instance.id)
        target_path = target_dir / stored_name
        with open(target_path, 'wb') as fp:
            for chunk in uploaded.chunks():
                fp.write(chunk)
        Avatar.objects.filter(pk=instance.pk).update(
            original_filename=original_name,
            stored_filename=stored_name,
        )
        return True
