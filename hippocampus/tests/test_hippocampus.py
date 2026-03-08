from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hippocampus.hippocampus import (
    HippocampusMemoryYield,
    TalosHippocampus,
)


class TestHippocampusVectors:
    """Tests the new Vector Memory Architecture for Auto-Recall Defense."""

    @pytest.mark.asyncio
    @patch('hippocampus.hippocampus.ModelRegistry.objects.get')
    @patch('hippocampus.hippocampus.sync_to_async')
    @patch('frontal_lobe.synapse.OllamaClient.embed')
    async def test_save_engram_intercepts_identical(self, mock_embed,
                                                    mock_sync_to_async,
                                                    mock_registry_get):
        """Tests that saving intercepts identical memories instead of writing them."""
        # Setup mocks
        mock_embed.return_value = [0.1, 0.2, 0.3]
        mock_registry_get.return_value = MagicMock(name='nomic-embed-text')

        # Mocking the sync_to_async call to return a pre-computed HippocampusMemoryYield
        msg = "Save rejected. High memory overlap detected."

        async def mock_second_call(*args, **kwargs):
            return HippocampusMemoryYield(message=msg,
                                          intercepted=True,
                                          similarity=0.95)

        def side_effect_func(func):
            if func is mock_registry_get:

                async def mock_get(*args, **kwargs):
                    registry_mock = MagicMock()
                    registry_mock.name = 'nomic-embed-text'
                    return registry_mock

                return mock_get

            if func is mock_embed:

                async def mock_embed_inner(*args, **kwargs):
                    return [0.1, 0.2, 0.3]

                return mock_embed_inner

            return mock_second_call

        mock_sync_to_async.side_effect = side_effect_func

        result = await TalosHippocampus.save_engram("session_123", "Concept",
                                                    "Fact about concept", 1)

        assert isinstance(result, HippocampusMemoryYield)
        assert result.intercepted is True
        assert "Save rejected" in result.message
        assert result.similarity == 0.95
        assert result.focus_yield == 0

    @pytest.mark.asyncio
    @patch('hippocampus.hippocampus.ModelRegistry.objects.get')
    @patch('hippocampus.hippocampus.sync_to_async')
    @patch('frontal_lobe.synapse.OllamaClient.embed')
    async def test_update_engram_vectors(self, mock_embed, mock_sync_to_async,
                                         mock_registry_get):
        """Tests that update properly fetches a new embedding."""
        mock_embed.return_value = [0.1, 0.2, 0.3]
        mock_registry_get.return_value = MagicMock(name='nomic-embed-text')

        async def mock_first_call(*args, **kwargs):
            return ("desc", "Concept")

        async def mock_second_call(*args, **kwargs):
            return HippocampusMemoryYield(intercepted=False,
                                          message="Success",
                                          similarity=0.5)

        def side_effect_func(func):
            if func is mock_registry_get:

                async def mock_get(*args, **kwargs):
                    registry_mock = MagicMock()
                    registry_mock.name = 'nomic-embed-text'
                    return registry_mock

                return mock_get

            if func is mock_embed:

                async def mock_embed_inner(*args, **kwargs):
                    return [0.1, 0.2, 0.3]

                return mock_embed_inner

            if hasattr(func,
                       "__name__") and func.__name__ == "_get_existing_sync":
                return mock_first_call

            return mock_second_call

        mock_sync_to_async.side_effect = side_effect_func

        result = await TalosHippocampus.update_engram("session_123", "Concept",
                                                      "Additional fact", 1)

        assert isinstance(result, HippocampusMemoryYield)
        assert result.intercepted is False
        assert result.similarity == 0.5
        assert result.focus_yield == 5
        assert result.xp_yield == 50
