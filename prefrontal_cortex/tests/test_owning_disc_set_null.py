"""FK-softening test: PFCAssignmentMixin.owning_disc -> SET_NULL.

PFC tasks, stories, and epics survive when their owning IdentityDisc
is removed — the work is more useful reassignable than cascade-deleted
along with a departing disc (common case: bundle uninstall takes the
owning disc with it).
"""

from common.tests.common_test_case import CommonFixturesAPITestCase
from identity.models import IdentityDisc, IdentityType
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask


class PFCTaskSurvivesOwningDiscRemovalTest(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.modifier = NeuralModifier.objects.create(
            name='FK Test Bundle',
            slug='fk-test-owning-disc-setnull',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        worker_type, _ = IdentityType.objects.get_or_create(
            id=IdentityType.WORKER, defaults={'name': 'Worker'}
        )
        self.bundle_disc = IdentityDisc.objects.create(
            name='FK Test Bundle Disc',
            identity_type=worker_type,
            system_prompt_template='',
            genome=self.modifier,
        )
        self.epic = PFCEpic.objects.create(
            name='FK Test Epic',
            description='',
            priority=3,
            owning_disc=self.bundle_disc,
        )
        self.story = PFCStory.objects.create(
            name='FK Test Story',
            epic=self.epic,
            owning_disc=self.bundle_disc,
        )
        self.task = PFCTask.objects.create(
            name='FK Test Task',
            story=self.story,
            owning_disc=self.bundle_disc,
        )

    def test_uninstall_nulls_owning_disc_on_pfc_rows(self):
        """Assert PFC rows survive with owning_disc=None after uninstall."""
        self.assertEqual(self.task.owning_disc_id, self.bundle_disc.pk)

        loader.uninstall_bundle(self.modifier.slug)

        self.assertFalse(
            IdentityDisc.objects.filter(pk=self.bundle_disc.pk).exists()
        )
        self.task.refresh_from_db()
        self.story.refresh_from_db()
        self.epic.refresh_from_db()
        self.assertIsNone(self.task.owning_disc_id)
        self.assertIsNone(self.story.owning_disc_id)
        self.assertIsNone(self.epic.owning_disc_id)
