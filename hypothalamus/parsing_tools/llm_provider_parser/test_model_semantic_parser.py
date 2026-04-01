"""Tests for the standalone model semantic parser."""

import os

from hypothalamus.parsing_tools.llm_provider_parser.model_semantic_parser import (
    parse_model_string,
)


def test_basic_gpt():
    r = parse_model_string('gpt-4o')
    assert r.success
    assert r.family == 'GPT'
    assert r.creator == 'OpenAI'
    assert r.provider is None


def test_claude_with_provider():
    r = parse_model_string('openrouter/anthropic/claude-opus-4.6')
    assert r.success
    assert r.family == 'Claude'
    assert r.creator == 'Anthropic'
    assert r.provider == 'openrouter'


def test_claude_thinking_tag():
    r = parse_model_string('openrouter/anthropic/claude-3.7-sonnet:thinking')
    assert r.success
    assert r.family == 'Claude'
    assert 'thinking' in r.tags


def test_bedrock_region():
    r = parse_model_string('bedrock/us-east-1/anthropic.claude-v2:1')
    assert r.success
    assert r.provider == 'bedrock'
    assert r.provider_region == 'us-east-1'
    assert r.creator == 'Anthropic'
    assert r.family == 'Claude'


def test_azure_region():
    r = parse_model_string('azure/eu/gpt-5.1-chat')
    assert r.success
    assert r.provider == 'azure'
    assert r.provider_region == 'eu'
    assert r.creator == 'OpenAI'
    assert r.family == 'GPT'


def test_ollama_size():
    r = parse_model_string('ollama/llama3:8b')
    assert r.success
    assert r.family == 'Llama'
    assert r.parameter_size == '8B'
    assert r.provider == 'ollama'


def test_deepseek_distill_priority():
    """DeepSeek should be detected as family, not Qwen."""
    r = parse_model_string(
        'fireworks_ai/accounts/fireworks/models/deepseek-r1-distill-qwen-7b'
    )
    assert r.success
    assert r.family == 'DeepSeek'
    assert r.parameter_size == '7B'


def test_fine_tuned():
    r = parse_model_string('ft:gpt-4o-2024-08-06')
    assert r.success
    assert r.family == 'GPT'
    assert 'fine-tuned' in r.tags


def test_o_series():
    r = parse_model_string('o3-pro')
    assert r.success
    assert r.family == 'o-series'
    assert r.creator == 'OpenAI'


def test_quantization():
    r = parse_model_string(
        'meta_llama/Llama-4-Scout-17B-16E-Instruct-FP8'
    )
    assert r.success
    assert r.family == 'Llama'
    assert 'FP8' in r.quantizations
    assert r.parameter_size == '17B'


def test_stability_provider_family():
    r = parse_model_string('stability/erase')
    assert r.success
    assert r.family == 'Stability-Erase'
    assert r.creator == 'Stability AI'


def test_deepgram_provider_family():
    r = parse_model_string('deepgram/nova-2-general')
    assert r.success
    assert r.family == 'Deepgram-Nova'
    assert r.creator == 'Deepgram'


def test_gemini():
    r = parse_model_string('gemini-2.5-flash')
    assert r.success
    assert r.family == 'Gemini'
    assert r.creator == 'Google'


def test_command_r_plus():
    r = parse_model_string('command-r-plus-08-2024')
    assert r.success
    assert r.family == 'Command'
    assert r.creator == 'Cohere'


def test_vertex_ai_at_version():
    r = parse_model_string('vertex_ai/claude-3-5-sonnet@20240620')
    assert r.success
    assert r.provider == 'vertex_ai'
    assert r.family == 'Claude'


def test_unmanageable_search():
    r = parse_model_string('tavily/search-advanced')
    assert r.unmanageable
    assert not r.success


def test_unmanageable_pricing_tier():
    r = parse_model_string('together-ai-4.1b-8b')
    assert r.unmanageable


def test_glm():
    r = parse_model_string('zai/glm-4.7')
    assert r.success
    assert r.family == 'GLM'
    assert r.creator == 'Zhipu AI'


def test_eu_bedrock_prefix():
    r = parse_model_string('eu.anthropic.claude-opus-4-6-v1')
    assert r.success
    assert r.family == 'Claude'
    assert r.creator == 'Anthropic'


def test_image_size_prefix():
    r = parse_model_string('hd/1024-x-1024/dall-e-3')
    assert r.success
    assert r.family == 'DALL-E'
    assert r.creator == 'OpenAI'


def test_empty_string():
    r = parse_model_string('')
    assert not r.success
    assert r.unmanageable


def test_flux():
    r = parse_model_string('black_forest_labs/flux-kontext-pro')
    assert r.success
    assert r.family == 'FLUX'
    assert r.creator == 'Black Forest Labs'


def test_full_catalog_no_crashes():
    """Run against all models; none should crash."""
    current_dir = os.path.dirname(__file__)
    file_path = os.path.join(current_dir, 'example_model_list.txt')
    if not os.path.exists(file_path):
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        raw_models = [line.strip() for line in f if line.strip()]

    failures = 0
    no_family = 0
    unmanageable = 0

    for raw in raw_models:
        result = parse_model_string(raw)
        assert result is not None
        if result.unmanageable:
            unmanageable += 1
        elif result.success:
            if not result.family:
                no_family += 1
        else:
            failures += 1

    total = len(raw_models)
    success_rate = (total - failures - unmanageable) / total
    assert success_rate >= 0.98, f'Success rate {success_rate:.1%} < 98%'
    assert failures == 0, f'{failures} models failed to parse'
    assert no_family == 0, f'{no_family} models have no family'
    assert unmanageable < 50, f'{unmanageable} unmanageable (expected < 50)'


if __name__ == '__main__':
    # Run all test functions
    import traceback
    test_funcs = [v for k, v in globals().items() if k.startswith('test_')]
    passed = 0
    failed = 0
    for func in test_funcs:
        try:
            func()
            passed += 1
            print(f'  PASS: {func.__name__}')
        except Exception as e:
            failed += 1
            print(f'  FAIL: {func.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{passed} passed, {failed} failed out of {passed + failed} tests')
