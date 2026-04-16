from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

# BTW: I really don't like this, but it seems necessary atm.
# Patch OllamaClient.embed globally so no test ever hits Ollama.
_EMBED_PATCH = patch(
    'frontal_lobe.synapse.OllamaClient.embed', return_value=None
)


class CommonTestCase(APITestCase):
    """A test case with the fundamentals."""

    fixtures = (
        'central_nervous_system/fixtures/genetic_immutables.json',
        'environments/fixtures/genetic_immutables.json',
        'frontal_lobe/fixtures/genetic_immutables.json',
        'hypothalamus/fixtures/genetic_immutables.json',
        'identity/fixtures/genetic_immutables.json',
        'parietal_lobe/fixtures/genetic_immutables.json',
        'peripheral_nervous_system/fixtures/genetic_immutables.json',
        'prefrontal_cortex/fixtures/genetic_immutables.json',
        'temporal_lobe/fixtures/genetic_immutables.json',
    )

    @classmethod
    def setUpClass(cls):
        if not _EMBED_PATCH.is_started:
            _EMBED_PATCH.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if _EMBED_PATCH.is_started:
            _EMBED_PATCH.stop()

    def setUp(self):
        self.test_user_name = 'Monty'
        self.test_user_password = 'Python'
        self.test_user_first_name = 'TestFirstName'
        self.test_user_last_name = 'TestLastName'
        self.test_user_email = 'Montys@Pythons.com'

        self.test_user = User.objects.create_user(
            username=self.test_user_name,
            password=self.test_user_password,
            first_name=self.test_user_first_name,
            last_name=self.test_user_last_name,
            email=self.test_user_email,
        )
        self.test_user.is_active = True
        self.test_user.save()
        self.test_user_login = self.client.login(
            username=self.test_user_name, password=self.test_user_password
        )
        self.test_client = APIClient()
        self.test_client.force_authenticate(user=self.test_user)

        return super(CommonTestCase, self).setUp()


class CommonFixturesAPITestCase(CommonTestCase):
    fixtures = [
        # gi tier
        'central_nervous_system/fixtures/genetic_immutables.json',
        'environments/fixtures/genetic_immutables.json',
        'frontal_lobe/fixtures/genetic_immutables.json',
        'hypothalamus/fixtures/genetic_immutables.json',
        'identity/fixtures/genetic_immutables.json',
        'parietal_lobe/fixtures/genetic_immutables.json',
        'peripheral_nervous_system/fixtures/genetic_immutables.json',
        'prefrontal_cortex/fixtures/genetic_immutables.json',
        'temporal_lobe/fixtures/genetic_immutables.json',
        # zygote tier
        'central_nervous_system/fixtures/zygote.json',
        'environments/fixtures/zygote.json',
        'hypothalamus/fixtures/zygote.json',
        'identity/fixtures/zygote.json',
        'parietal_lobe/fixtures/zygote.json',
        'temporal_lobe/fixtures/zygote.json',
        # initial_phenotypes tier
        'central_nervous_system/fixtures/initial_phenotypes.json',
        'environments/fixtures/initial_phenotypes.json',
        'hypothalamus/fixtures/initial_phenotypes.json',
        'identity/fixtures/initial_phenotypes.json',
        'parietal_lobe/fixtures/initial_phenotypes.json',
        'temporal_lobe/fixtures/initial_phenotypes.json',
        # unreal_modifier (temporary — until UE bundle extraction, Task 5d)
        'central_nervous_system/fixtures/unreal_modifier.json',
        'environments/fixtures/unreal_modifier.json',
        # petri_dish tier
        'central_nervous_system/fixtures/petri_dish.json',
        'environments/fixtures/petri_dish.json',
        'hypothalamus/fixtures/petri_dish.json',
        'identity/fixtures/petri_dish.json',
        'parietal_lobe/fixtures/petri_dish.json',
        'temporal_lobe/fixtures/petri_dish.json',
        # FORBIDDEN: NEVER ADD THIS AGAIN FORBIDDEN
        # 'peripheral_nervous_system/fixtures/test_agents.json',
    ]
