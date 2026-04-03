import os
from unittest.mock import MagicMock, patch

from rest_framework import status

from common.tests.common_test_case import CommonFixturesAPITestCase
from hypothalamus.api import scrape_ollama_library
from hypothalamus.models import (
    AIMode,
    AIModel,
    AIModelCapabilities,
    AIModelCreator,
    AIModelDescription,
    AIModelFamily,
    AIModelPricing,
    AIModelProvider,
    AIModelTags,
    LLMProvider,
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

SYNC_LOCAL_URL = '/api/v2/ai-models/sync_local/'
FETCH_CATALOG_URL = '/api/v2/ai-models/fetch_catalog/'

MOCK_OLLAMA_TAGS = {
    'models': [
        {
            'name': 'gemma3:27b',
            'model': 'gemma3:27b',
            'size': 17079156736,
            'details': {
                'format': 'gguf',
                'family': 'gemma3',
                'families': ['gemma3'],
                'parameter_size': '27.2B',
                'quantization_level': 'Q4_K_M',
            },
        },
        {
            'name': 'llama3.2:3b',
            'model': 'llama3.2:3b',
            'size': 2019393189,
            'details': {
                'format': 'gguf',
                'family': 'llama',
                'families': ['llama'],
                'parameter_size': '3.2B',
                'quantization_level': 'Q4_0',
            },
        },
        {
            'name': 'nomic-embed-text:latest',
            'model': 'nomic-embed-text:latest',
            'size': 274302450,
            'details': {
                'format': 'gguf',
                'family': 'nomic-bert',
                'families': ['nomic-bert'],
                'parameter_size': '0.1B',
                'quantization_level': 'F16',
            },
        },
    ]
}

MOCK_OLLAMA_HTML = """
<html><body>
<ul>
  <li>
    <a href="/library/llama3.1">
      <h2>llama3.1</h2>
      <p>Meta's latest open-source model with strong reasoning capabilities</p>
      <span>tools</span>
      <span>vision</span>
      <span>8b</span>
      <span>70b</span>
      <span>405b</span>
      <span>112.5M Pulls</span>
    </a>
  </li>
  <li>
    <a href="/library/gemma3">
      <h2>gemma3</h2>
      <p>Google DeepMind's lightweight open model</p>
      <span>thinking</span>
      <span>4b</span>
      <span>27b</span>
      <span>50.1M Pulls</span>
    </a>
  </li>
  <li>
    <a href="/library/nomic-embed-text">
      <h2>nomic-embed-text</h2>
      <p>A high-performing open embedding model</p>
      <span>embedding</span>
      <span>0.1b</span>
      <span>10M Pulls</span>
    </a>
  </li>
</ul>
</body></html>
"""


def _mock_ollama_response(json_data):
    """Build a mock requests response with .json() and .raise_for_status()."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_html_response(text):
    """Build a mock requests response with .text and .raise_for_status()."""
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestSyncLocal(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.mode_chat, _ = AIMode.objects.get_or_create(name='chat')
        self.provider_ollama, _ = LLMProvider.objects.get_or_create(
            key='ollama',
            defaults={'name': 'Ollama', 'requires_api_key': False},
        )

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_sync_discovers_models(self, mock_get, mock_fire):
        """Assert sync_local creates AIModel, AIModelProvider, and AIModelPricing for each installed model."""
        mock_get.return_value = _mock_ollama_response(MOCK_OLLAMA_TAGS)

        resp = self.test_client.post(SYNC_LOCAL_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['synced'] == 3
        assert 'gemma3:27b' in resp.data['models']
        assert 'llama3.2:3b' in resp.data['models']
        assert 'nomic-embed-text:latest' in resp.data['models']

        for name in ['gemma3:27b', 'llama3.2:3b', 'nomic-embed-text:latest']:
            assert AIModel.objects.filter(name=name).exists()
            provider = AIModelProvider.objects.get(
                provider_unique_model_id=f'ollama/{name}'
            )
            assert provider.is_enabled is True
            assert AIModelPricing.objects.filter(
                model_provider=provider,
                is_current=True,
                is_active=True,
            ).exists()

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_sync_disables_uninstalled_models(self, mock_get, mock_fire):
        """Assert sync_local sets is_enabled=False on providers for models no longer installed."""
        # Disable all pre-existing Ollama providers from fixtures first
        AIModelProvider.objects.filter(
            provider=self.provider_ollama
        ).update(is_enabled=False)

        old_model, _ = AIModel.objects.get_or_create(
            name='old-model:7b',
            defaults={'context_length': 4096},
        )
        AIModelProvider.objects.create(
            ai_model=old_model,
            provider=self.provider_ollama,
            provider_unique_model_id='ollama/old-model:7b',
            mode=self.mode_chat,
            is_enabled=True,
        )

        mock_get.return_value = _mock_ollama_response(MOCK_OLLAMA_TAGS)
        resp = self.test_client.post(SYNC_LOCAL_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['disabled'] == 1

        old_provider = AIModelProvider.objects.get(
            provider_unique_model_id='ollama/old-model:7b'
        )
        assert old_provider.is_enabled is False

        assert AIModel.objects.filter(name='old-model:7b').exists()
        assert AIModelProvider.objects.filter(
            provider_unique_model_id='ollama/old-model:7b'
        ).exists()

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_sync_is_idempotent(self, mock_get, mock_fire):
        """Assert running sync_local twice does not create duplicate records."""
        mock_get.return_value = _mock_ollama_response(MOCK_OLLAMA_TAGS)

        self.test_client.post(SYNC_LOCAL_URL)
        resp = self.test_client.post(SYNC_LOCAL_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['synced'] == 3

        assert AIModel.objects.filter(name='gemma3:27b').count() == 1
        assert AIModelProvider.objects.filter(
            provider_unique_model_id='ollama/gemma3:27b'
        ).count() == 1
        assert AIModelPricing.objects.filter(
            model_provider__provider_unique_model_id='ollama/gemma3:27b',
            is_current=True,
        ).count() == 1

    @patch('hypothalamus.api.http_requests.get')
    def test_sync_ollama_unreachable_returns_503(self, mock_get):
        """Assert sync_local returns 503 when Ollama is not running."""
        import requests

        mock_get.side_effect = requests.ConnectionError('Connection refused')

        resp = self.test_client.post(SYNC_LOCAL_URL)

        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert 'Ollama is not running' in resp.data['error']

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_sync_parses_parameter_size(self, mock_get, mock_fire):
        """Assert sync_local correctly parses parameter_size from model details."""
        mock_get.return_value = _mock_ollama_response(MOCK_OLLAMA_TAGS)

        self.test_client.post(SYNC_LOCAL_URL)

        gemma = AIModel.objects.get(name='gemma3:27b')
        assert gemma.parameter_size == 27.2

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_sync_embedding_mode(self, mock_get, mock_fire):
        """Assert sync_local assigns embedding mode to models with 'embed' in the name."""
        mock_get.return_value = _mock_ollama_response(MOCK_OLLAMA_TAGS)

        self.test_client.post(SYNC_LOCAL_URL)

        embed_provider = AIModelProvider.objects.get(
            provider_unique_model_id='ollama/nomic-embed-text:latest'
        )
        assert embed_provider.mode.name == 'embedding'

        chat_provider = AIModelProvider.objects.get(
            provider_unique_model_id='ollama/gemma3:27b'
        )
        assert chat_provider.mode.name == 'chat'


class TestFetchCatalog(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_fetch_creates_models_and_descriptions(self, mock_get, mock_fire):
        """Assert fetch_catalog creates AIModel and AIModelDescription with correct M2M links."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        resp = self.test_client.post(FETCH_CATALOG_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['fetched'] == 3
        assert resp.data['created'] + resp.data['updated'] == 3

        for name in ['llama3.1', 'gemma3', 'nomic-embed-text']:
            ai_model = AIModel.objects.get(name=name)
            desc = AIModelDescription.objects.filter(
                ai_models=ai_model, is_current=True
            ).first()
            assert desc is not None
            assert desc.description != ''

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_fetch_creates_capability_tags(self, mock_get, mock_fire):
        """Assert fetch_catalog creates AIModelTags for capability badges."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        self.test_client.post(FETCH_CATALOG_URL)

        llama = AIModel.objects.get(name='llama3.1')
        desc = AIModelDescription.objects.filter(
            ai_models=llama, is_current=True
        ).first()
        tag_names = set(desc.tags.values_list('name', flat=True))
        assert 'tools' in tag_names
        assert 'vision' in tag_names

        assert llama.capabilities.filter(name='function_calling').exists()
        assert llama.capabilities.filter(name='vision').exists()

        gemma = AIModel.objects.get(name='gemma3')
        assert gemma.capabilities.filter(name='reasoning').exists()

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_fetch_creates_size_tags(self, mock_get, mock_fire):
        """Assert fetch_catalog stores size labels as tags on the description."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        self.test_client.post(FETCH_CATALOG_URL)

        llama = AIModel.objects.get(name='llama3.1')
        desc = AIModelDescription.objects.filter(
            ai_models=llama, is_current=True
        ).first()
        tag_names = set(desc.tags.values_list('name', flat=True))
        assert 'size:8b' in tag_names
        assert 'size:70b' in tag_names
        assert 'size:405b' in tag_names

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_fetch_updates_existing_description(self, mock_get, mock_fire):
        """Assert fetch_catalog updates existing description rather than creating duplicates."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        self.test_client.post(FETCH_CATALOG_URL)
        self.test_client.post(FETCH_CATALOG_URL)

        llama = AIModel.objects.get(name='llama3.1')
        desc_count = AIModelDescription.objects.filter(
            ai_models=llama, is_current=True
        ).count()
        assert desc_count == 1

    @patch('hypothalamus.api.http_requests.get')
    def test_fetch_ollama_unreachable_returns_502(self, mock_get):
        """Assert fetch_catalog returns 502 when ollama.com is unreachable."""
        import requests

        mock_get.side_effect = requests.ConnectionError('Connection refused')

        resp = self.test_client.post(FETCH_CATALOG_URL)

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'ollama.com' in resp.data['error']


class TestAIModelDescriptionCRUD(CommonFixturesAPITestCase):

    DESCRIPTIONS_URL = '/api/v2/model-descriptions/'

    def setUp(self):
        super().setUp()
        self.model_a, _ = AIModel.objects.get_or_create(
            name='desc-test-model-a',
            defaults={'context_length': 4096},
        )
        self.model_b, _ = AIModel.objects.get_or_create(
            name='desc-test-model-b',
            defaults={'context_length': 4096},
        )
        self.family, _ = AIModelFamily.objects.get_or_create(
            slug='desc-test-family',
            defaults={'name': 'Desc Test Family'},
        )

    def test_create_description_with_m2m_links(self):
        """Assert POST creates an AIModelDescription with M2M links to models and families."""
        payload = {
            'description': 'A test description for M2M.',
            'is_current': True,
            'ai_model_ids': [str(self.model_a.pk), str(self.model_b.pk)],
            'family_ids': [self.family.pk],
        }
        resp = self.test_client.post(
            self.DESCRIPTIONS_URL, payload, format='json'
        )

        assert resp.status_code == status.HTTP_201_CREATED
        desc = AIModelDescription.objects.get(pk=resp.data['id'])
        assert set(desc.ai_models.values_list('pk', flat=True)) == {
            self.model_a.pk,
            self.model_b.pk,
        }
        assert self.family in desc.families.all()

    def test_patch_updates_m2m_links(self):
        """Assert PATCH updates M2M links (add/remove models)."""
        desc = AIModelDescription.objects.create(
            description='Original', is_current=True
        )
        desc.ai_models.add(self.model_a)

        url = f'{self.DESCRIPTIONS_URL}{desc.pk}/'
        resp = self.test_client.patch(
            url,
            {'ai_model_ids': [str(self.model_b.pk)]},
            format='json',
        )

        assert resp.status_code == status.HTTP_200_OK
        desc.refresh_from_db()
        linked_ids = set(desc.ai_models.values_list('pk', flat=True))
        assert self.model_b.pk in linked_ids
        assert self.model_a.pk not in linked_ids

    def test_patch_updates_description_text(self):
        """Assert PATCH updates description text."""
        desc = AIModelDescription.objects.create(
            description='Original text', is_current=True
        )

        url = f'{self.DESCRIPTIONS_URL}{desc.pk}/'
        resp = self.test_client.patch(
            url,
            {'description': 'Updated text'},
            format='json',
        )

        assert resp.status_code == status.HTTP_200_OK
        desc.refresh_from_db()
        assert desc.description == 'Updated text'


class TestScrapeOllamaLibrary(CommonFixturesAPITestCase):

    def test_extracts_names_descriptions_badges_sizes(self):
        """Assert scrape_ollama_library extracts all fields from valid HTML."""
        entries = scrape_ollama_library(MOCK_OLLAMA_HTML)

        assert len(entries) == 3

        llama = entries[0]
        assert llama['name'] == 'llama3.1'
        assert 'latest open-source model' in llama['description']
        assert 'tools' in llama['badges']
        assert 'vision' in llama['badges']
        assert '8b' in llama['sizes']
        assert '70b' in llama['sizes']
        assert '405b' in llama['sizes']

        gemma = entries[1]
        assert gemma['name'] == 'gemma3'
        assert 'thinking' in gemma['badges']
        assert '27b' in gemma['sizes']

        nomic = entries[2]
        assert nomic['name'] == 'nomic-embed-text'
        assert 'embedding' in nomic['badges']

    def test_returns_empty_on_malformed_html(self):
        """Assert scrape_ollama_library returns empty list on garbage HTML."""
        result = scrape_ollama_library('<html><body>no models here</body></html>')
        assert result == []

    def test_returns_empty_on_empty_string(self):
        """Assert scrape_ollama_library returns empty list on empty input."""
        assert scrape_ollama_library('') == []


class TestFetchCatalogParserIntegration(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.llama_family, _ = AIModelFamily.objects.get_or_create(
            slug='llama',
            defaults={'name': 'Llama'},
        )
        self.meta_creator, _ = AIModelCreator.objects.get_or_create(
            name='Meta',
        )

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_parser_sets_family_and_creator(self, mock_get, mock_fire):
        """Assert fetch_catalog uses parse_model_string to enrich family and creator."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        self.test_client.post(FETCH_CATALOG_URL)

        llama = AIModel.objects.get(name='llama3.1')
        assert llama.family == self.llama_family
        assert llama.creator == self.meta_creator

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_parser_called_for_each_model(self, mock_get, mock_fire):
        """Assert parse_model_string is called for each scraped entry."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        with patch('hypothalamus.api.parse_model_string', wraps=__import__('hypothalamus.parsing_tools.llm_provider_parser.model_semantic_parser', fromlist=['parse_model_string']).parse_model_string) as mock_parse:
            self.test_client.post(FETCH_CATALOG_URL)
            assert mock_parse.call_count == 3

    @patch('hypothalamus.api.fire_neurotransmitter')
    @patch('hypothalamus.api.http_requests.get')
    def test_description_has_m2m_links(self, mock_get, mock_fire):
        """Assert fetch_catalog creates AIModelDescription with correct M2M links."""
        mock_get.return_value = _mock_html_response(MOCK_OLLAMA_HTML)

        self.test_client.post(FETCH_CATALOG_URL)

        llama = AIModel.objects.get(name='llama3.1')
        desc = AIModelDescription.objects.filter(
            ai_models=llama, is_current=True
        ).first()
        assert desc is not None
        assert llama in desc.ai_models.all()
        assert self.llama_family in desc.families.all()
