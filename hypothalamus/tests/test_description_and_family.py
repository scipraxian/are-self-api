import os

from rest_framework import status

from common.tests.common_test_case import CommonFixturesAPITestCase
from hypothalamus.models import (
    AIModel,
    AIModelCategory,
    AIModelDescription,
    AIModelFamily,
    AIModelTags,
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


class TestCurrentDescription(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.family = AIModelFamily.objects.create(
            name='Test Family', slug='test-family'
        )
        self.ai_model = AIModel.objects.create(
            name='test-desc-model',
            context_length=4096,
            family=self.family,
        )

    def test_model_specific_description(self):
        """Assert current_description returns model-specific description."""
        desc = AIModelDescription.objects.create(
            description='Model-level description.', is_current=True
        )
        desc.ai_models.add(self.ai_model)

        url = f'/api/v2/ai-models/{self.ai_model.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['current_description'] == 'Model-level description.'

    def test_family_fallback_description(self):
        """Assert current_description falls back to family-linked description."""
        fam_desc = AIModelDescription.objects.create(
            description='Family-level description.', is_current=True
        )
        fam_desc.families.add(self.family)

        url = f'/api/v2/ai-models/{self.ai_model.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['current_description'] == 'Family-level description.'

    def test_model_specific_takes_precedence_over_family(self):
        """Assert model-specific description wins over family fallback."""
        fam_desc = AIModelDescription.objects.create(
            description='Family-level description.', is_current=True
        )
        fam_desc.families.add(self.family)

        model_desc = AIModelDescription.objects.create(
            description='Model-level wins.', is_current=True
        )
        model_desc.ai_models.add(self.ai_model)

        url = f'/api/v2/ai-models/{self.ai_model.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['current_description'] == 'Model-level wins.'

    def test_no_description_returns_none(self):
        """Assert current_description is None when no descriptions exist."""
        url = f'/api/v2/ai-models/{self.ai_model.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['current_description'] is None


class TestAIModelDescriptionViewSet(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.category = AIModelCategory.objects.create(name='Chat')
        self.tag = AIModelTags.objects.create(name='fast')
        self.ai_model = AIModel.objects.create(
            name='desc-viewset-model', context_length=4096
        )
        self.family = AIModelFamily.objects.create(
            name='Desc Family', slug='desc-family'
        )

    def test_list_descriptions(self):
        """Assert GET model-descriptions returns descriptions."""
        desc = AIModelDescription.objects.create(
            description='Test desc.', is_current=True
        )
        desc.ai_models.add(self.ai_model)

        resp = self.test_client.get('/api/v2/model-descriptions/')
        assert resp.status_code == status.HTTP_200_OK
        descriptions = [d['description'] for d in resp.data]
        assert 'Test desc.' in descriptions

    def test_create_description(self):
        """Assert POST model-descriptions creates a description with M2M links."""
        payload = {
            'description': 'Created via API.',
            'is_current': True,
            'ai_model_ids': [str(self.ai_model.pk)],
            'family_ids': [self.family.pk],
            'category_ids': [self.category.pk],
            'tag_ids': [self.tag.pk],
        }
        resp = self.test_client.post(
            '/api/v2/model-descriptions/', payload, format='json'
        )
        assert resp.status_code == status.HTTP_201_CREATED
        desc = AIModelDescription.objects.get(pk=resp.data['id'])
        assert desc.description == 'Created via API.'
        assert self.ai_model in desc.ai_models.all()
        assert self.family in desc.families.all()
        assert self.category in desc.categories.all()
        assert self.tag in desc.tags.all()

    def test_retrieve_description(self):
        """Assert GET model-descriptions/<pk>/ returns nested relations."""
        desc = AIModelDescription.objects.create(
            description='Detailed desc.', is_current=True
        )
        desc.ai_models.add(self.ai_model)
        desc.families.add(self.family)

        url = f'/api/v2/model-descriptions/{desc.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['description'] == 'Detailed desc.'
        assert len(resp.data['ai_models']) == 1
        assert resp.data['ai_models'][0]['name'] == 'desc-viewset-model'
        assert len(resp.data['families']) == 1
        assert resp.data['families'][0]['name'] == 'Desc Family'

    def test_delete_description(self):
        """Assert DELETE model-descriptions/<pk>/ removes the description."""
        desc = AIModelDescription.objects.create(
            description='To delete.', is_current=True
        )
        url = f'/api/v2/model-descriptions/{desc.pk}/'
        resp = self.test_client.delete(url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not AIModelDescription.objects.filter(pk=desc.pk).exists()


class TestAIModelFamilyParent(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.parent_family, _ = AIModelFamily.objects.get_or_create(
            slug='test-parent-fam',
            defaults={'name': 'Test Parent Family'},
        )
        self.child_family = AIModelFamily.objects.create(
            name='Test Child Family',
            slug='test-child-fam',
            parent=self.parent_family,
        )

    def test_subfamily_serialization(self):
        """Assert GET model-families returns parent as nested dict."""
        url = f'/api/v2/model-families/{self.child_family.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['parent'] is not None
        assert resp.data['parent']['id'] == self.parent_family.pk
        assert resp.data['parent']['name'] == self.parent_family.name
        assert resp.data['parent']['slug'] == 'test-parent-fam'

    def test_top_level_family_parent_is_none(self):
        """Assert GET model-families returns null parent for top-level family."""
        url = f'/api/v2/model-families/{self.parent_family.pk}/'
        resp = self.test_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['parent'] is None

    def test_subfamilies_reverse_relation(self):
        """Assert parent.subfamilies contains the child family."""
        subfamilies = self.parent_family.subfamilies.all()
        assert self.child_family in subfamilies
