import os

import pytest
from django.test import TestCase

from hypothalamus.model_semantic_parser import parse_model_string


@pytest.mark.skip(reason='Requires populated fixture.')
class SemanticParserTestCase(TestCase):
    # Relies on the JSON data seeded previously to test DB interaction
    fixtures = ['hypothalamus/fixtures/initial_data.json']

    def test_parse_standard_openrouter(self):
        """Proves we can strip noise (:free), find the DB items, and extract math."""
        payload = parse_model_string('openrouter/qwen/qwen3.5-35b-a3b:free')

        self.assertTrue(payload.success)
        self.assertEqual(payload.parameter_size, 35.0)
        self.assertEqual(payload.family.name, 'Qwen')
        self.assertEqual(payload.version.name, '3.5')

        # Ensure ':free' was stripped as noise, but 'a3b' was saved as a tag
        tag_names = [t.name for t in payload.tags]
        self.assertNotIn('free', tag_names)
        self.assertIn('a3b', tag_names)

    def test_parse_ollama_with_colon_and_quantization(self):
        """Proves we don't destroy local routing data by blinding splitting on colons."""
        payload = parse_model_string('ollama/llama3.1:8b-instruct-q4_K_M')

        self.assertTrue(payload.success)
        self.assertEqual(payload.parameter_size, 8.0)
        self.assertEqual(payload.family.name, 'Llama')
        self.assertEqual(payload.version.name, '3.1')

        # Instruct should be pulled from the Role DB table
        self.assertTrue(any(role.name == 'Instruct' for role in payload.roles))

        # The quantization format safely lands in tags (or quantizations if in DB)
        quants_and_tags = [q.name.lower() for q in payload.quantizations] + [
            t.name.lower() for t in payload.tags
        ]
        self.assertIn('q4_k_m', quants_and_tags)

    def test_parse_identity_crisis_model(self):
        """Proves we bypass 5 layers of folders and extract multiple tags."""
        payload = parse_model_string(
            'fireworks_ai/accounts/fireworks/models/deepseek-r1-0528-distill-qwen3-8b'
        )

        self.assertTrue(payload.success)
        self.assertEqual(payload.parameter_size, 8.0)
        self.assertEqual(payload.family.name, 'DeepSeek')
        self.assertEqual(payload.version.name, 'r1')

        # 'distill' and 'qwen3' should cleanly become tags
        tag_names = [t.name.lower() for t in payload.tags]
        self.assertIn('distill', tag_names)
        self.assertIn('qwen3', tag_names)

    def test_unknown_trailing_tag(self):
        """Proves user's rule: if it ends in ':hiimnew', it becomes a tag, not stripped."""
        payload = parse_model_string('openrouter/mistral/mistral-7b:hiimnew')

        self.assertTrue(payload.success)
        tag_names = [t.name.lower() for t in payload.tags]
        self.assertIn('hiimnew', tag_names)

    @pytest.mark.skip(reason='Integration test, not a unit test.')
    def test_full_catalog_gauntlet(self):
        """
        Reads the 2000+ model list and ensures the parser doesn't crash.
        Prints a report of 'Ghosts' (models that yielded no family and no size).
        """
        # Resolve the path to example_model_list.txt in the same directory
        current_dir = os.path.dirname(__file__)
        file_path = os.path.join(current_dir, 'example_model_list.txt')

        # Ensure the file exists before we try to read it
        self.assertTrue(
            os.path.exists(file_path), f'Could not find {file_path}'
        )

        with open(file_path, 'r', encoding='utf-8') as f:
            raw_models = [line.strip() for line in f if line.strip()]

        ghosts = []
        success_count = 0

        for raw_string in raw_models:
            with self.subTest(raw_string=raw_string):
                # 1. The primary assertion: It must not throw an unhandled exception
                payload = parse_model_string(raw_string)

                # 2. It must return our dataclass
                self.assertIsNotNone(payload)
                self.assertIsInstance(payload.success, bool)

                # 3. Track our "Ghosts"
                # If it's a valid string but we couldn't find a family AND we couldn't find a size,
                # it means our heuristics completely missed it.
                if (
                    payload.success
                    and not payload.family
                    and not payload.parameter_size
                ):
                    ghosts.append(raw_string)
                elif payload.success:
                    success_count += 1

        # Print the anomaly report to the console so we can see what slipped through
        print(f'\n--- THE GAUNTLET REPORT ---')
        print(f'Total Processed: {len(raw_models)}')
        print(f'Successfully Grokked (Found Family or Size): {success_count}')
        print(f'Ghosts (Slipped through as pure tags): {len(ghosts)}')

        if ghosts:
            print('\nTop 20 Ghosts for the README Rant:')
            for ghost in ghosts[:20]:
                print(f' - {ghost}')
        print('---------------------------\n')
