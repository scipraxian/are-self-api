"""Filesystem path helpers for ``Avatar`` rows.

Lives in its own module (instead of ``identity/avatars.py``) so
``identity/models.py`` can import it without pulling in the DRF
viewset layer — which itself imports ``identity.models``.
"""

from __future__ import annotations

from pathlib import Path

from neuroplasticity.loader import grafts_root
from neuroplasticity.models import NeuralModifier


def avatar_media_dir(genome: NeuralModifier) -> Path:
    """Resolve the media directory for an avatar bound to this genome.

    Bytes for ``display=FILE`` Avatar rows live at
    ``<grafts_root>/<genome.slug>/media/<stored_filename>``. The
    directory is created on first write. INCUBATOR has no
    graft-of-record by spec (no manifest, no install path), but a
    media subdirectory is created under it on demand to hold user
    uploads that haven't been promoted into a real bundle yet;
    ``save_bundle_to_archive`` will bake them in once the user
    promotes the row.
    """
    return grafts_root() / genome.slug / 'media'
