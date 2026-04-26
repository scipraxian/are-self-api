"""Pytest bootstrap — runs before Django setup.

Sets ``NEUROPLASTICITY_SKIP_BOOT=1`` so ``NeuroplasticityConfig.ready()``
does NOT connect ``request_started`` to ``boot_bundles()``. Without this,
the first ``APIClient`` call in any test fires ``boot_bundles()`` against
the *real* ``neuroplasticity/grafts/`` directory — its orphan sweep then
``rmtree``s every bundle dir lacking an INSTALLED row in the (test) DB.

Tests that legitimately need the boot pass call ``loader.boot_bundles()``
directly under ``override_settings(NEURAL_MODIFIER_GRAFTS_ROOT=...)``;
see ``test_modifier_lifecycle.py`` and ``test_install_unreal_bundle.py``.
"""

import os

os.environ.setdefault('NEUROPLASTICITY_SKIP_BOOT', '1')
