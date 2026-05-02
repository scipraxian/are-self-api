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
    directory is created on first write. INCUBATOR is now a real
    grafted genome — its graft tree is bootstrapped on every Django
    boot via :func:`neuroplasticity.loader.graft_incubator`, so the
    ``media/`` subdir is guaranteed to exist alongside the manifest
    by the time any avatar write reaches it. Uploads stamped
    ``genome=INCUBATOR`` land here until the user promotes the row
    into another genome via the V2 PATCH path or
    ``save_graft_to_genome`` bakes it into the genome's zip.
    """
    return grafts_root() / genome.slug / 'media'
