import asyncio
from unittest.mock import patch

from common.tests.common_test_case import CommonFixturesAPITestCase

from identity.models import IdentityDisc, IdentityType
from frontal_lobe.models import ModelProvider, ModelRegistry, ReasoningSession, ReasoningStatusID
from frontal_lobe.synapse import OllamaClient
from frontal_lobe.synapse_open_router import OpenRouterClient
from parietal_lobe.parietal_lobe import ParietalLobe
from central_nervous_system.models import Spike


class RoutingTest(CommonFixturesAPITestCase):
    def setUp(self):
        # Reuse the minimal ReasoningSession setup pattern from existing tests.
        # Let defaults/wiring from migrations handle FK relations to avoid
        # having to bootstrap all lookup tables here.
        self.session = ReasoningSession.objects.create()

        worker_type, _ = IdentityType.objects.get_or_create(
            id=IdentityType.WORKER, defaults={'name': 'Worker'}
        )
        self.disc = IdentityDisc.objects.create(
            name='Routing Disc',
            identity_type=worker_type,
            system_prompt_template='Route me',
        )
        self.session.identity_disc = self.disc
        self.session.save(update_fields=['identity_disc'])

    def test_local_provider_uses_ollama_client(self):
        # Use the fixture-backed Ollama provider (id=ModelProvider.OLLAMA)
        provider = ModelProvider.objects.get(pk=ModelProvider.OLLAMA)
        registry = ModelRegistry.objects.get(name='llama3.2:3b')
        registry.provider = provider
        registry.save(update_fields=['provider'])
        self.disc.ai_model = registry
        self.disc.save(update_fields=['ai_model'])

        lobe = ParietalLobe(self.session, log_callback=lambda *_: None)

        asyncio.run(lobe.initialize_client(self.disc))
        self.assertIsInstance(lobe.client, OllamaClient)

    def test_openrouter_provider_uses_openrouter_client(self):
        provider = ModelProvider.objects.get(pk=ModelProvider.OPENROUTER)
        registry = ModelRegistry.objects.create(
            name='openrouter/model',
            description='Remote OpenRouter model',
            provider=provider,
        )
        self.disc.ai_model = registry
        self.disc.save(update_fields=['ai_model'])

        lobe = ParietalLobe(self.session, log_callback=lambda *_: None)

        asyncio.run(lobe.initialize_client(self.disc))
        self.assertIsInstance(lobe.client, OpenRouterClient)

