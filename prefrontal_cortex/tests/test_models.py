from django.test import TransactionTestCase
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask, PFCItemStatus, PFCComment


class PrefrontalCortexTest(TransactionTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
        'identity/fixtures/initial_data.json',
        'parietal_lobe/fixtures/initial_data.json',
        'prefrontal_cortex/fixtures/initial_data.json',
        'temporal_lobe/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Create an Epic, Story, and Task
        self.epic = PFCEpic.objects.create(name="Test Epic",
                                           description="Epic Description",
                                           priority=1,
                                           assertions="Assert epic")
        self.story = PFCStory.objects.create(name="Test Story",
                                             epic=self.epic,
                                             complexity=5)
        self.task = PFCTask.objects.create(name="Test Task", story=self.story)

    def test_tree_relationships(self):
        self.assertEqual(self.epic.stories.count(), 1)
        self.assertEqual(self.story.tasks.count(), 1)
        self.assertEqual(self.epic.stories.first(), self.story)
        self.assertEqual(self.story.tasks.first(), self.task)

    def test_pfc_comments(self):
        # Valid comment attached to exactly one target
        comment = PFCComment(text="This is a test comment", epic=self.epic)
        comment.clean()  # should not raise
        comment.save()

        self.assertEqual(comment.epic, self.epic)
        self.assertIsNone(comment.story)
        self.assertIsNone(comment.task)

        # Test clean method raises error if multiple targets
        comment_invalid = PFCComment(text="Invalid",
                                     epic=self.epic,
                                     story=self.story)

        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            comment_invalid.clean()
