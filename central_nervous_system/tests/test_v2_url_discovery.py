"""Tests for the V2 URL discovery loop.

Exercises ``central_nervous_system.urls.v2_urls._discover_bundle_routers``
in isolation: each test materializes a fake NeuralModifier bundle on disk
under an ``@override_settings(NEURAL_MODIFIER_GRAFTS_ROOT=...)`` tempdir,
seeds an INSTALLED ``NeuralModifier`` row, then calls the discovery
function with a fresh ``SimpleRouter`` and asserts the resulting
registry. The real ``V2_CNS_ROUTER`` is never mutated.

Inheriting from ``CommonTestCase`` (not ``CommonFixturesAPITestCase``)
matches ``test_install_unreal_bundle.py``'s reasoning: avoid pre-loading
``modifier_data.json`` fixture rows that would collide with bundle
INSTALL operations the test itself performs.

Discovery contract under test:

  * No bundles installed -> no-op.
  * Bundle with no ``urls`` submodule -> silent skip (legit opt-out).
  * Bundle with ``urls.py`` but no ``V2_GENOME_ROUTER`` attr -> silent skip.
  * Bundle with empty ``entry_modules`` -> silent skip.
  * Bundle whose ``grafts/<slug>/`` runtime dir is missing -> silent skip.
  * Grafts root missing entirely -> silent no-op.
  * Bundle with valid ``V2_GENOME_ROUTER`` -> entries lifted onto the
    core router.
  * Prefix collision against the core router -> ``RuntimeError``.
  * Prefix collision between two bundles -> ``RuntimeError``.
  * ``urls.py`` exists but a transitive import is broken -> the
    ``ModuleNotFoundError`` propagates loudly (the spec's
    "broken urls.py fails loudly" guarantee).
"""

import shutil
import sys
import tempfile
from pathlib import Path

from django.test import override_settings
from rest_framework import routers
from rest_framework.viewsets import ViewSet

from central_nervous_system.urls._v2_bundle_discovery import (
    _discover_bundle_routers,
)
from common.tests.common_test_case import CommonTestCase
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


_BUNDLE_URLS_HAPPY = '''\
from rest_framework import routers
from rest_framework.viewsets import ViewSet


class _DiscoveryHappyViewSet(ViewSet):
    pass


V2_GENOME_ROUTER = routers.SimpleRouter()
V2_GENOME_ROUTER.register(
    r'discovery-test-prefix',
    _DiscoveryHappyViewSet,
    basename='discovery-test',
)
'''

_BUNDLE_URLS_NO_ROUTER = '''\
# urls.py present but does not export V2_GENOME_ROUTER -- legit opt-out.
SOMETHING_ELSE = 'not a router'
'''

_BUNDLE_URLS_BROKEN_IMPORT = '''\
# urls.py exists but its first import is broken -- raise loudly per spec.
from .does_not_exist_anywhere import never_reached  # noqa: F401
'''

_BUNDLE_URLS_COLLIDES_WITH_CORE = '''\
from rest_framework import routers
from rest_framework.viewsets import ViewSet


class _DiscoveryCollisionViewSet(ViewSet):
    pass


V2_GENOME_ROUTER = routers.SimpleRouter()
# 'core-canon-prefix' is registered on the test fixture's core router.
V2_GENOME_ROUTER.register(
    r'core-canon-prefix',
    _DiscoveryCollisionViewSet,
    basename='discovery-collision',
)
'''


class _CoreCanonicalViewSet(ViewSet):
    """Sentinel viewset registered on the fake core router for collision tests."""
    pass


class V2UrlDiscoveryTestCase(CommonTestCase):
    """Asserts the bundle URL discovery contract in isolation."""

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(tempfile.mkdtemp(prefix='v2disc_'))
        self._grafts_root = self._tmp_root / 'grafts'
        self._grafts_root.mkdir()
        self._setting_overrider = override_settings(
            NEURAL_MODIFIER_GRAFTS_ROOT=str(self._grafts_root),
        )
        self._setting_overrider.enable()
        self._sys_path_snapshot = list(sys.path)
        self._sys_modules_snapshot = set(sys.modules)

    def tearDown(self):
        # Drop any modules imported during the test so siblings get a
        # clean slate. Mirror the snapshot-restore pattern used by
        # test_install_unreal_bundle.py.
        for key in list(sys.modules):
            if key not in self._sys_modules_snapshot:
                del sys.modules[key]
        sys.path[:] = self._sys_path_snapshot
        self._setting_overrider.disable()
        shutil.rmtree(self._tmp_root, ignore_errors=True)
        super().tearDown()

    def _fresh_core_router(self):
        """Return a SimpleRouter with one canonical-shaped registration.

        Used as the input ``core_router`` to ``_discover_bundle_routers``
        so each test gets an isolated router (the real V2_CNS_ROUTER is
        never touched).
        """
        router = routers.SimpleRouter()
        router.register(
            r'core-canon-prefix',
            _CoreCanonicalViewSet,
            basename='core-canon',
        )
        return router

    def _write_bundle(
        self,
        slug,
        entry_module,
        urls_content=None,
        write_disk=True,
        register_db=True,
        include_entry_modules=True,
    ):
        """Materialize a fake bundle on disk and/or in the DB.

        ``write_disk=False`` skips the ``grafts/<slug>/code/...`` tree
        (used to test the "INSTALLED row but no runtime dir" case).
        ``register_db=False`` skips the NeuralModifier row creation.
        ``include_entry_modules=False`` writes a manifest with empty
        ``entry_modules`` (used to test that path).
        """
        if write_disk:
            code_dir = (
                self._grafts_root / slug / 'code' / entry_module
            )
            code_dir.mkdir(parents=True)
            (code_dir / '__init__.py').write_text('')
            if urls_content is not None:
                (code_dir / 'urls.py').write_text(urls_content)

        if register_db:
            manifest = {
                'slug': slug,
                'name': slug.title(),
                'version': '1.0.0',
                'author': 'discovery-test',
                'license': 'MIT',
                'entry_modules': (
                    [entry_module] if include_entry_modules else []
                ),
            }
            NeuralModifier.objects.create(
                slug=slug,
                name=manifest['name'],
                version=manifest['version'],
                author=manifest['author'],
                license=manifest['license'],
                manifest_hash='a' * 64,
                manifest_json=manifest,
                status_id=NeuralModifierStatus.INSTALLED,
            )

    # --- happy paths -------------------------------------------------

    def test_no_bundles_installed_is_noop(self):
        """Assert discovery is a no-op when zero bundles are installed."""
        router = self._fresh_core_router()
        before = list(router.registry)
        _discover_bundle_routers(router)
        self.assertEqual(router.registry, before)

    def test_valid_bundle_extends_core_router(self):
        """Assert a bundle's V2_GENOME_ROUTER entries land on the core router."""
        self._write_bundle(
            slug='disc_happy',
            entry_module='_v2disc_happy_pkg',
            urls_content=_BUNDLE_URLS_HAPPY,
        )
        router = self._fresh_core_router()
        _discover_bundle_routers(router)
        prefixes = [prefix for prefix, _, _ in router.registry]
        self.assertIn('discovery-test-prefix', prefixes)
        # Original core registration still present.
        self.assertIn('core-canon-prefix', prefixes)

    # --- silent-skip paths (per spec) --------------------------------

    def test_bundle_without_urls_py_is_silent_skip(self):
        """Assert a bundle with no urls submodule is skipped silently."""
        self._write_bundle(
            slug='disc_no_urls',
            entry_module='_v2disc_no_urls_pkg',
            urls_content=None,
        )
        router = self._fresh_core_router()
        before = list(router.registry)
        _discover_bundle_routers(router)
        self.assertEqual(router.registry, before)

    def test_bundle_with_urls_but_no_router_is_silent_skip(self):
        """Assert urls.py without V2_GENOME_ROUTER attr is skipped silently."""
        self._write_bundle(
            slug='disc_no_router',
            entry_module='_v2disc_no_router_pkg',
            urls_content=_BUNDLE_URLS_NO_ROUTER,
        )
        router = self._fresh_core_router()
        before = list(router.registry)
        _discover_bundle_routers(router)
        self.assertEqual(router.registry, before)

    def test_bundle_with_no_entry_modules_is_skipped(self):
        """Assert a bundle whose manifest has no entry_modules is skipped."""
        self._write_bundle(
            slug='disc_no_entry',
            entry_module='_v2disc_no_entry_pkg',
            urls_content=_BUNDLE_URLS_HAPPY,
            include_entry_modules=False,
        )
        router = self._fresh_core_router()
        before = list(router.registry)
        _discover_bundle_routers(router)
        self.assertEqual(router.registry, before)

    def test_bundle_with_missing_runtime_dir_is_skipped(self):
        """Assert an INSTALLED row whose runtime dir is missing is skipped."""
        self._write_bundle(
            slug='disc_orphan',
            entry_module='_v2disc_orphan_pkg',
            urls_content=None,
            write_disk=False,
            register_db=True,
        )
        router = self._fresh_core_router()
        before = list(router.registry)
        _discover_bundle_routers(router)
        self.assertEqual(router.registry, before)

    def test_grafts_dir_missing_is_noop(self):
        """Assert discovery is a silent no-op when the grafts root is missing."""
        # Remove the grafts dir entirely; the override still points at
        # the (now nonexistent) path.
        shutil.rmtree(self._grafts_root)
        router = self._fresh_core_router()
        before = list(router.registry)
        _discover_bundle_routers(router)
        self.assertEqual(router.registry, before)

    # --- raise-loud paths --------------------------------------------

    def test_collision_with_core_prefix_raises(self):
        """Assert RuntimeError when a bundle prefix collides with core."""
        self._write_bundle(
            slug='disc_colcore',
            entry_module='_v2disc_colcore_pkg',
            urls_content=_BUNDLE_URLS_COLLIDES_WITH_CORE,
        )
        router = self._fresh_core_router()
        with self.assertRaises(RuntimeError) as cm:
            _discover_bundle_routers(router)
        message = str(cm.exception)
        self.assertIn('disc_colcore', message)
        self.assertIn('core-canon-prefix', message)

    def test_collision_between_two_bundles_raises(self):
        """Assert RuntimeError when two bundles register the same prefix."""
        self._write_bundle(
            slug='disc_first',
            entry_module='_v2disc_first_pkg',
            urls_content=_BUNDLE_URLS_HAPPY,
        )
        # Second bundle, distinct slug + entry_module, but identical
        # registered prefix -- whichever bundle goes second will hit
        # the collision branch.
        second_urls = _BUNDLE_URLS_HAPPY.replace(
            "basename='discovery-test'",
            "basename='discovery-test-2'",
        ).replace(
            '_DiscoveryHappyViewSet',
            '_DiscoverySecondViewSet',
        )
        self._write_bundle(
            slug='disc_second',
            entry_module='_v2disc_second_pkg',
            urls_content=second_urls,
        )
        router = self._fresh_core_router()
        with self.assertRaises(RuntimeError) as cm:
            _discover_bundle_routers(router)
        message = str(cm.exception)
        self.assertIn('discovery-test-prefix', message)

    def test_broken_urls_py_propagates(self):
        """Assert ModuleNotFoundError from a broken urls.py propagates."""
        self._write_bundle(
            slug='disc_broken',
            entry_module='_v2disc_broken_pkg',
            urls_content=_BUNDLE_URLS_BROKEN_IMPORT,
        )
        router = self._fresh_core_router()
        with self.assertRaises(ModuleNotFoundError):
            _discover_bundle_routers(router)
