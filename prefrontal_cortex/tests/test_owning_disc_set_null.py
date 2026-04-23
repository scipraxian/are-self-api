"""FK-softening test: PFCAssignmentMixin.owning_disc -> CASCADE.

Bundle uninstall is a clean removal: PFC tasks, stories, and epics
assigned to an IdentityDisc owned by a bundle cascade away with the
bundle. No dangling-null reassignment cleanup required.
"""

from common.tests.common_test_case import CommonFixturesAPITestCase
from identity.models import IdentityDisc, IdentityType
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask


class PFCRowsCascadeOnOwningDiscRemovalTest(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.modifier = NeuralModifier.objects.create(
            name='FK Test Bundle',
            slug='fk-test-owning-disc-cascade',
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

    def test_uninstall_cascades_pfc_rows_with_owning_disc(self):
        """Assert PFC epic/story/task rows cascade when their owning disc goes."""
        self.assertEqual(self.task.owning_disc_id, self.bundle_disc.pk)
        task_pk = self.task.pk
        story_pk = self.story.pk
        epic_pk = self.epic.pk

        loader.uninstall_bundle(self.modifier.slug)

        self.assertFalse(
            IdentityDisc.objects.filter(pk=self.bundle_disc.pk).exists()
        )
        self.assertFalse(
            PFCTask.objects.filter(pk=task_pk).exists(),
            'PFCTask should cascade with its bundle-owned disc.',
        )
        self.assertFalse(
            PFCStory.objects.filter(pk=story_pk).exists(),
            'PFCStory should cascade with its bundle-owned disc.',
        )
        self.assertFalse(
            PFCEpic.objects.filter(pk=epic_pk).exists(),
            'PFCEpic should cascade with its bundle-owned disc.',
        )
