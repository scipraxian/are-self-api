from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase


class CommonTestCase(APITestCase):
    """A test case with the fundamentals."""

    fixtures = ('initial_data.json',)

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
        'parietal_lobe/fixtures/initial_data.json',
        'hypothalamus/fixtures/initial_data.json',
        'identity/fixtures/initial_data.json',
        'temporal_lobe/fixtures/initial_data.json',
        'prefrontal_cortex/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
    ]
