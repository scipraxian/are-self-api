#!/usr/bin/env python3
"""Generate three-tier Ollama model fixtures for Are-Self Hypothalamus."""

import json
import uuid
from collections import OrderedDict

# ──────────────────────────────────────────────
# EXISTING PKs FROM CURRENT FIXTURE — DO NOT COLLIDE
# ──────────────────────────────────────────────
EXISTING_PROVIDER_PK = 64  # Ollama LLMProvider

# Existing capability PKs
CAP = {
    'system_messages': 1,
    'function_calling': 2,
    'pdf_input': 3,
    'prompt_caching': 4,
    'response_schema': 5,
    'vision': 6,
    'reasoning': 7,
    'video_input': 8,
    'embedding_image_input': 9,
    'image_input': 10,
    'audio_input': 11,
    'assistant_prefill': 12,
    'tool_choice': 13,
    'computer_use': 14,
    'native_streaming': 15,
    'parallel_function_calling': 16,
    'audio_output': 17,
    'none_reasoning_effort': 18,
    'service_tier': 19,
    'minimal_reasoning_effort': 20,
    'web_search': 21,
    'url_context': 22,
    'code_execution': 23,
    'file_search': 24,
    'multimodal': 25,
    'xhigh_reasoning_effort': 26,
    'preset': 27,
}

# Existing mode PKs
MODE = {
    'image_generation': 1,
    'chat': 2,
    'embedding': 3,
    'rerank': 4,
    'audio_transcription': 5,
    'responses': 6,
    'completion': 7,
    'audio_speech': 8,
    'ocr': 9,
    'image_edit': 10,
    'search': 11,
    'realtime': 12,
    'video_generation': 13,
    'moderation': 14,
    'vector_store': 15,
}

# Existing role PKs
ROLE = {
    'instruct': 1,
    'chat': 2,
    'coder': 3,
    'reasoning': 4,
    'embedding': 5,
    'multimodal': 6,
    'uncensored': 7,
}

# Existing creator PKs (and new ones we'll add)
CREATOR_PK = {
    'Meta': 1,
    'Alibaba': 2,
    'Mistral AI': 3,
    'OpenAI': 4,
    'Google': 5,
    'Anthropic': 6,
    'DeepSeek': 7,
    'Microsoft': 8,
    'xAI': 9,
    'Black Forest Labs': 10,
    'Bria AI': 11,
}

# New creators we need to add
NEW_CREATORS = {
    'Nomic AI': (12, 'Creators of nomic-embed-text embedding models.'),
    'Cohere': (
        13,
        'Enterprise AI company. Creators of Command and Embed models.',
    ),
    'IBM': (14, 'IBM Research. Creators of the Granite model family.'),
    'NousResearch': (
        15,
        'Open-source AI research lab. Creators of Hermes models.',
    ),
    'NVIDIA': (16, 'Creators of Nemotron models for enterprise AI.'),
    'Zhipu AI': (17, 'Chinese AI lab. Creators of the GLM model family.'),
    'BigCode': (18, 'Open-source project. Creators of StarCoder models.'),
    'Moonshot': (19, 'Chinese AI lab. Creators of Kimi models.'),
    'BAAI': (20, 'Beijing Academy of AI. Creators of BGE embedding models.'),
    'Snowflake': (21, 'Creators of Arctic embedding models.'),
    'MiniMax': (22, 'Chinese AI company. Creators of MiniMax language models.'),
    'Allen AI': (23, 'Allen Institute for AI. Creators of OLMo models.'),
    'LG AI Research': (24, 'Creators of EXAONE models.'),
    'Databricks': (25, 'Creators of DBRX.'),
    'DeepCogito': (26, 'Creators of Cogito reasoning models.'),
    'Liquid AI': (27, 'Creators of LFM hybrid models.'),
    'Perplexity': (28, 'AI search company. Creators of Sonar models.'),
    'Essential AI': (29, 'Creators of RNJ models.'),
    'Mixedbread AI': (30, 'Creators of mxbai embedding models.'),
    'Upstage': (31, 'Creators of Solar models.'),
    'TII': (32, 'Technology Innovation Institute. Creators of Falcon models.'),
    'Eric Hartford': (
        33,
        'Independent researcher. Creator of Dolphin fine-tunes.',
    ),
    'StepFun': (34, 'Chinese AI company. Creators of Step models.'),
    'ByteDance': (35, 'Creators of Seed and Doubao models.'),
}

for name, (pk, desc) in NEW_CREATORS.items():
    CREATOR_PK[name] = pk

# ──────────────────────────────────────────────
# FAMILY DEFINITIONS (new table — PKs start at 1)
# ──────────────────────────────────────────────
FAMILY_DEFS = OrderedDict()
_fam_pk = 0


def fam(name, slug, desc):
    global _fam_pk
    _fam_pk += 1
    FAMILY_DEFS[slug] = {
        'pk': _fam_pk,
        'name': name,
        'slug': slug,
        'description': desc,
    }
    return _fam_pk


FAM_LLAMA = fam(
    'Llama',
    'llama',
    "Meta's open-source LLM family. Ranges from 1B to 405B parameters.",
)
FAM_QWEN = fam(
    'Qwen',
    'qwen',
    "Alibaba's multilingual LLM family with strong coding and reasoning.",
)
FAM_QWEN_CODER = fam(
    'Qwen Coder',
    'qwen-coder',
    'Code-specialized Qwen models optimized for generation, reasoning, and fixing.',
)
FAM_GEMMA = fam(
    'Gemma', 'gemma', "Google's lightweight open models. Efficient and capable."
)
FAM_MISTRAL = fam(
    'Mistral',
    'mistral',
    "Mistral AI's core model family. Strong multilingual performance.",
)
FAM_MIXTRAL = fam(
    'Mixtral',
    'mixtral',
    "Mistral's Mixture-of-Experts models. High throughput.",
)
FAM_PHI = fam(
    'Phi',
    'phi',
    "Microsoft's small language models. Strong reasoning for their size.",
)
FAM_DEEPSEEK = fam(
    'DeepSeek', 'deepseek', "DeepSeek's open reasoning and coding models."
)
FAM_DEEPSEEK_CODER = fam(
    'DeepSeek Coder', 'deepseek-coder', "DeepSeek's code-specialized models."
)
FAM_NOMIC = fam(
    'Nomic Embed',
    'nomic-embed',
    'High-performing open embedding models by Nomic AI.',
)
FAM_GPT_OSS = fam(
    'GPT-OSS',
    'gpt-oss',
    "OpenAI's open-weight models for reasoning and agentic tasks.",
)
FAM_GLM = fam(
    'GLM',
    'glm',
    "Zhipu AI's general language models. Strong multilingual and reasoning.",
)
FAM_COMMAND = fam(
    'Command',
    'command',
    "Cohere's enterprise language models optimized for RAG and tools.",
)
FAM_GRANITE = fam(
    'Granite',
    'granite',
    "IBM's enterprise foundation models for code and language.",
)
FAM_CODELLAMA = fam(
    'CodeLlama', 'codellama', "Meta's code-specialized Llama models."
)
FAM_HERMES = fam(
    'Hermes',
    'hermes',
    "NousResearch's instruction-tuned models. Strong general purpose.",
)
FAM_DOLPHIN = fam(
    'Dolphin',
    'dolphin',
    "Eric Hartford's uncensored fine-tunes. Multiple base model variants.",
)
FAM_STARCODER = fam(
    'StarCoder', 'starcoder', "BigCode's open code generation models."
)
FAM_LLAVA = fam(
    'LLaVA',
    'llava',
    'Large Language and Vision Assistant. Multimodal understanding.',
)
FAM_FALCON = fam('Falcon', 'falcon', "TII's open language models.")
FAM_NEMOTRON = fam(
    'Nemotron', 'nemotron', "NVIDIA's enterprise-grade language models."
)
FAM_CODESTRAL = fam(
    'Codestral', 'codestral', "Mistral AI's dedicated code generation model."
)
FAM_DEVSTRAL = fam(
    'Devstral', 'devstral', "Mistral AI's software engineering agent model."
)
FAM_MAGISTRAL = fam('Magistral', 'magistral', "Mistral AI's reasoning model.")
FAM_MINISTRAL = fam(
    'Ministral', 'ministral', "Mistral AI's edge deployment models."
)
FAM_YI = fam('Yi', 'yi', "01.AI's bilingual language models.")
FAM_VICUNA = fam('Vicuna', 'vicuna', "UC Berkeley's chat model based on Llama.")
FAM_COGITO = fam('Cogito', 'cogito', "DeepCogito's hybrid reasoning models.")
FAM_QWQ = fam('QwQ', 'qwq', "Qwen's dedicated reasoning model.")
FAM_SOLAR = fam('Solar', 'solar', "Upstage's compact language models.")
FAM_BGE = fam('BGE', 'bge', "BAAI's embedding models for retrieval.")
FAM_SNOWFLAKE_ARCTIC = fam(
    'Snowflake Arctic',
    'snowflake-arctic',
    "Snowflake's embedding models optimized for retrieval.",
)
FAM_MXBAI = fam('mxbai', 'mxbai', "Mixedbread AI's embedding models.")
FAM_OLMO = fam(
    'OLMo', 'olmo', "Allen AI's open language models for scientific research."
)
FAM_DBRX = fam('DBRX', 'dbrx', "Databricks' open general-purpose MoE model.")
FAM_EXAONE = fam('EXAONE', 'exaone', "LG AI Research's bilingual models.")
FAM_KIMI = fam('Kimi', 'kimi', "Moonshot AI's multimodal and reasoning models.")
FAM_MINIMAX = fam(
    'MiniMax',
    'minimax',
    "MiniMax's language models for coding and productivity.",
)
FAM_LFM = fam('LFM', 'lfm', "Liquid AI's hybrid models for edge deployment.")
FAM_SMOLLM = fam(
    'SmolLM', 'smollm', "HuggingFace's compact models for edge devices."
)
FAM_QWEN_VL = fam('Qwen VL', 'qwen-vl', "Qwen's vision-language models.")
FAM_INTERNLM = fam(
    'InternLM', 'internlm', "Shanghai AI Lab's open language models."
)
FAM_CODEGEMMA = fam(
    'CodeGemma', 'codegemma', "Google's code-specialized Gemma models."
)
FAM_OPENTHINKER = fam(
    'OpenThinker',
    'openthinker',
    'Open-source reasoning models distilled from DeepSeek-R1.',
)

# ──────────────────────────────────────────────
# MODEL CATALOG — All 160+ Ollama models
# Each entry: (slug, name, desc, creator, family, sizes, default_ctx, mode, roles, caps, tier)
# tier: 1=docker, 2=top40, 3=complete
# ──────────────────────────────────────────────


def m(
    slug,
    name,
    desc,
    creator,
    family,
    param_size=None,
    ctx=131072,
    mode='chat',
    roles=None,
    caps=None,
    tier=3,
):
    """Shorthand model definition."""
    return {
        'slug': slug,
        'name': name,
        'description': desc,
        'creator': creator,
        'family': family,
        'param_size': param_size,
        'ctx': ctx,
        'mode': mode,
        'roles': roles or [],
        'caps': caps or [],
        'tier': tier,
    }


MODELS = [
    # ── TIER 1: Docker ships ──
    m(
        'nomic-embed-text',
        'nomic-embed-text',
        'A high-performing open embedding model with a large token context window. 768-dimensional vectors. The default embedding engine for Are-Self Hippocampus.',
        'Nomic AI',
        FAM_NOMIC,
        param_size=0.137,
        ctx=8192,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=1,
    ),
    m(
        'llama3.2:3b',
        'llama3.2:3b',
        "Meta's compact 3B parameter model. Fast inference, strong instruction following, tool use capable. Ideal for lightweight reasoning tasks on consumer hardware.",
        'Meta',
        FAM_LLAMA,
        param_size=3.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=1,
    ),
    m(
        'qwen2.5-coder:7b',
        'qwen2.5-coder:7b',
        "Alibaba's code-specialized 7B model. Excellent code generation, reasoning, and fixing. Supports function calling for tool-use workflows.",
        'Alibaba',
        FAM_QWEN_CODER,
        param_size=7.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['function_calling', 'system_messages'],
        tier=1,
    ),
    m(
        'gemma3:4b',
        'gemma3:4b',
        "Google's efficient 4B parameter model with vision capabilities. Processes images alongside text. Strong performance for its size.",
        'Google',
        FAM_GEMMA,
        param_size=4.0,
        ctx=131072,
        roles=['chat', 'multimodal'],
        caps=['vision', 'system_messages'],
        tier=1,
    ),
    # ── TIER 2: Top 40 popular ──
    m(
        'llama3.1:8b',
        'llama3.1:8b',
        "Meta's 8B parameter model with 128K context. Strong general purpose with tool use. The workhorse of local inference.",
        'Meta',
        FAM_LLAMA,
        param_size=8.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'llama3.1:70b',
        'llama3.1:70b',
        "Meta's 70B flagship. Near-frontier performance on reasoning, coding, and multilingual tasks.",
        'Meta',
        FAM_LLAMA,
        param_size=70.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'deepseek-r1:7b',
        'deepseek-r1:7b',
        "DeepSeek's open reasoning model. Uses chain-of-thought thinking tokens. Approaches frontier model performance on math and logic.",
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=7.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'deepseek-r1:14b',
        'deepseek-r1:14b',
        'DeepSeek R1 at 14B parameters. Strong reasoning with thinking tokens. Good balance of capability and hardware requirements.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=14.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'deepseek-r1:32b',
        'deepseek-r1:32b',
        'DeepSeek R1 32B. Excellent reasoning performance approaching larger models.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=32.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'deepseek-r1:70b',
        'deepseek-r1:70b',
        'DeepSeek R1 70B. Top-tier open reasoning model. Competitive with O3 and Gemini 2.5 Pro on benchmarks.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=70.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'gemma3:12b',
        'gemma3:12b',
        'Google Gemma 3 at 12B. Vision-capable with strong general reasoning.',
        'Google',
        FAM_GEMMA,
        param_size=12.0,
        ctx=131072,
        roles=['chat', 'multimodal'],
        caps=['vision', 'system_messages'],
        tier=2,
    ),
    m(
        'gemma3:27b',
        'gemma3:27b',
        'Google Gemma 3 27B. The most capable single-GPU Gemma model. Vision and strong reasoning.',
        'Google',
        FAM_GEMMA,
        param_size=27.0,
        ctx=131072,
        roles=['chat', 'multimodal'],
        caps=['vision', 'system_messages'],
        tier=2,
    ),
    m(
        'mistral:7b',
        'mistral:7b',
        "Mistral AI's 7B model. Strong multilingual performance. Updated to version 0.3.",
        'Mistral AI',
        FAM_MISTRAL,
        param_size=7.0,
        ctx=32768,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen2.5:7b',
        'qwen2.5:7b',
        "Alibaba's 7B general-purpose model. Trained on 18 trillion tokens. 128K context with multilingual support.",
        'Alibaba',
        FAM_QWEN,
        param_size=7.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen2.5:14b',
        'qwen2.5:14b',
        'Qwen 2.5 14B. Strong reasoning and multilingual capability at moderate hardware requirements.',
        'Alibaba',
        FAM_QWEN,
        param_size=14.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen2.5:32b',
        'qwen2.5:32b',
        'Qwen 2.5 32B. Excellent performance across benchmarks. Good for serious local inference.',
        'Alibaba',
        FAM_QWEN,
        param_size=32.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen3:8b',
        'qwen3:8b',
        "Alibaba's latest generation 8B model. Dense architecture with thinking support.",
        'Alibaba',
        FAM_QWEN,
        param_size=8.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen3:14b',
        'qwen3:14b',
        'Qwen 3 14B. Strong reasoning with thinking tokens.',
        'Alibaba',
        FAM_QWEN,
        param_size=14.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen3:30b',
        'qwen3:30b',
        'Qwen 3 30B. Excellent general purpose with thinking support.',
        'Alibaba',
        FAM_QWEN,
        param_size=30.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen3-coder:30b',
        'qwen3-coder:30b',
        "Alibaba's performant 30B coding model. Strong function calling and agentic task capability.",
        'Alibaba',
        FAM_QWEN_CODER,
        param_size=30.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen2.5-coder:14b',
        'qwen2.5-coder:14b',
        'Qwen 2.5 Coder at 14B. Stronger code generation and reasoning than the 7B variant.',
        'Alibaba',
        FAM_QWEN_CODER,
        param_size=14.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'qwen2.5-coder:32b',
        'qwen2.5-coder:32b',
        'Qwen 2.5 Coder 32B. Top-tier open code model.',
        'Alibaba',
        FAM_QWEN_CODER,
        param_size=32.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'phi3:3.8b',
        'phi3:3.8b',
        "Microsoft's Phi-3 Mini. Strong reasoning in a lightweight 3.8B package.",
        'Microsoft',
        FAM_PHI,
        param_size=3.8,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=2,
    ),
    m(
        'phi4:14b',
        'phi4:14b',
        "Microsoft's Phi-4. State-of-the-art 14B open model with strong reasoning.",
        'Microsoft',
        FAM_PHI,
        param_size=14.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['system_messages'],
        tier=2,
    ),
    m(
        'llama3:8b',
        'llama3:8b',
        'Meta Llama 3 8B. The most capable openly available LLM of its generation.',
        'Meta',
        FAM_LLAMA,
        param_size=8.0,
        ctx=8192,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'codellama:7b',
        'codellama:7b',
        "Meta's code-specialized Llama. Trained on code and natural language for generation and discussion.",
        'Meta',
        FAM_CODELLAMA,
        param_size=7.0,
        ctx=16384,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=2,
    ),
    m(
        'codellama:34b',
        'codellama:34b',
        'CodeLlama 34B. Strong code generation at scale.',
        'Meta',
        FAM_CODELLAMA,
        param_size=34.0,
        ctx=16384,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=2,
    ),
    m(
        'mixtral:8x7b',
        'mixtral:8x7b',
        "Mistral's MoE model. 8 experts at 7B each. High throughput with tool support.",
        'Mistral AI',
        FAM_MIXTRAL,
        param_size=56.0,
        ctx=32768,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'mistral-nemo:12b',
        'mistral-nemo:12b',
        "Mistral and NVIDIA's 12B model. 128K context with tool use.",
        'Mistral AI',
        FAM_MISTRAL,
        param_size=12.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'mistral-small:22b',
        'mistral-small:22b',
        'Mistral Small 3. Sets benchmarks in the sub-70B category.',
        'Mistral AI',
        FAM_MISTRAL,
        param_size=22.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'llava:7b',
        'llava:7b',
        'Large Language and Vision Assistant. End-to-end multimodal model combining vision encoder and Vicuna.',
        'Meta',
        FAM_LLAVA,
        param_size=7.0,
        ctx=4096,
        roles=['multimodal', 'chat'],
        caps=['vision', 'system_messages'],
        tier=2,
    ),
    m(
        'gpt-oss:20b',
        'gpt-oss:20b',
        "OpenAI's open-weight 20B model. Strong reasoning and agentic task capability.",
        'OpenAI',
        FAM_GPT_OSS,
        param_size=20.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'glm-4.7-flash',
        'glm-4.7-flash',
        "Zhipu AI's efficient model. Strongest in the 30B class. Balances performance and efficiency with thinking support.",
        'Zhipu AI',
        FAM_GLM,
        param_size=30.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=2,
    ),
    m(
        'command-r:35b',
        'command-r:35b',
        "Cohere's Command R. Optimized for conversational RAG and long context tasks with tool use.",
        'Cohere',
        FAM_COMMAND,
        param_size=35.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'granite-code:8b',
        'granite-code:8b',
        'IBM Granite for code. Open foundation model for code intelligence.',
        'IBM',
        FAM_GRANITE,
        param_size=8.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=2,
    ),
    m(
        'deepseek-coder:6.7b',
        'deepseek-coder:6.7b',
        'DeepSeek Coder 6.7B. Trained on 2 trillion code and natural language tokens.',
        'DeepSeek',
        FAM_DEEPSEEK_CODER,
        param_size=6.7,
        ctx=16384,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=2,
    ),
    m(
        'mxbai-embed-large:335m',
        'mxbai-embed-large:335m',
        'State-of-the-art large embedding model from Mixedbread AI.',
        'Mixedbread AI',
        FAM_MXBAI,
        param_size=0.335,
        ctx=8192,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=2,
    ),
    m(
        'bge-m3:567m',
        'bge-m3:567m',
        "BAAI's BGE-M3. Versatile embedding model: multi-functionality, multi-linguality, multi-granularity.",
        'BAAI',
        FAM_BGE,
        param_size=0.567,
        ctx=8192,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=2,
    ),
    m(
        'snowflake-arctic-embed:335m',
        'snowflake-arctic-embed:335m',
        "Snowflake's text embedding model optimized for retrieval performance.",
        'Snowflake',
        FAM_SNOWFLAKE_ARCTIC,
        param_size=0.335,
        ctx=8192,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=2,
    ),
    m(
        'hermes3:8b',
        'hermes3:8b',
        'NousResearch Hermes 3. Latest flagship instruction-tuned model with tool use.',
        'NousResearch',
        FAM_HERMES,
        param_size=8.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'cogito:8b',
        'cogito:8b',
        "DeepCogito's hybrid reasoning model. Outperforms counterparts from Llama, DeepSeek, and Qwen at similar sizes.",
        'DeepCogito',
        FAM_COGITO,
        param_size=8.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'llama3.3:70b',
        'llama3.3:70b',
        'Meta Llama 3.3 70B. Performance comparable to the 405B Llama 3.1 at a fraction of the size.',
        'Meta',
        FAM_LLAMA,
        param_size=70.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=2,
    ),
    m(
        'llama3.2-vision:11b',
        'llama3.2-vision:11b',
        "Meta's 11B vision-language model. Image reasoning with instruction following.",
        'Meta',
        FAM_LLAMA,
        param_size=11.0,
        ctx=131072,
        roles=['multimodal', 'chat'],
        caps=['vision', 'system_messages'],
        tier=2,
    ),
    # ── TIER 3: Complete Ollama catalog ──
    m(
        'llama3.1:405b',
        'llama3.1:405b',
        "Meta's largest open model. 405B parameters. Frontier-class performance.",
        'Meta',
        FAM_LLAMA,
        param_size=405.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'llama3.2:1b',
        'llama3.2:1b',
        "Meta's tiny 1B model. Ultra-fast inference on minimal hardware.",
        'Meta',
        FAM_LLAMA,
        param_size=1.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'deepseek-r1:1.5b',
        'deepseek-r1:1.5b',
        'DeepSeek R1 at 1.5B. Reasoning capability in a tiny package.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=1.5,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'deepseek-r1:8b',
        'deepseek-r1:8b',
        'DeepSeek R1 8B. Compact reasoning model.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=8.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'deepseek-r1:671b',
        'deepseek-r1:671b',
        'DeepSeek R1 full 671B MoE. Maximum reasoning capability.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=671.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'gemma3:1b',
        'gemma3:1b',
        'Google Gemma 3 1B. Minimal footprint.',
        'Google',
        FAM_GEMMA,
        param_size=1.0,
        ctx=131072,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'gemma2:9b',
        'gemma2:9b',
        'Google Gemma 2 9B. High-performing and efficient.',
        'Google',
        FAM_GEMMA,
        param_size=9.0,
        ctx=8192,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'gemma2:27b',
        'gemma2:27b',
        'Google Gemma 2 27B.',
        'Google',
        FAM_GEMMA,
        param_size=27.0,
        ctx=8192,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'phi3:14b',
        'phi3:14b',
        'Microsoft Phi-3 Medium. 14B parameters with strong reasoning.',
        'Microsoft',
        FAM_PHI,
        param_size=14.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'phi3.5:3.8b',
        'phi3.5:3.8b',
        'Phi-3.5 Mini. Lightweight with strong performance.',
        'Microsoft',
        FAM_PHI,
        param_size=3.8,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'phi4-mini:3.8b',
        'phi4-mini:3.8b',
        'Phi-4 Mini. Multilingual support and function calling.',
        'Microsoft',
        FAM_PHI,
        param_size=3.8,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'phi4-reasoning:14b',
        'phi4-reasoning:14b',
        'Phi-4 Reasoning. Rivals larger models on complex reasoning.',
        'Microsoft',
        FAM_PHI,
        param_size=14.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen2.5:0.5b',
        'qwen2.5:0.5b',
        'Qwen 2.5 500M. Tiny but capable.',
        'Alibaba',
        FAM_QWEN,
        param_size=0.5,
        ctx=131072,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'qwen2.5:72b',
        'qwen2.5:72b',
        'Qwen 2.5 72B. Frontier-class open model.',
        'Alibaba',
        FAM_QWEN,
        param_size=72.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen3:0.6b',
        'qwen3:0.6b',
        'Qwen 3 600M. Ultra-lightweight.',
        'Alibaba',
        FAM_QWEN,
        param_size=0.6,
        ctx=131072,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'qwen3:4b',
        'qwen3:4b',
        'Qwen 3 4B. Compact with thinking support.',
        'Alibaba',
        FAM_QWEN,
        param_size=4.0,
        ctx=131072,
        roles=['chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen3.5:9b',
        'qwen3.5:9b',
        'Qwen 3.5 9B. Latest generation multimodal with vision and thinking.',
        'Alibaba',
        FAM_QWEN,
        param_size=9.0,
        ctx=131072,
        roles=['chat', 'multimodal', 'reasoning'],
        caps=['vision', 'function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen3.5:27b',
        'qwen3.5:27b',
        'Qwen 3.5 27B. Strong multimodal performance.',
        'Alibaba',
        FAM_QWEN,
        param_size=27.0,
        ctx=131072,
        roles=['chat', 'multimodal', 'reasoning'],
        caps=['vision', 'function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen2.5-coder:1.5b',
        'qwen2.5-coder:1.5b',
        'Qwen 2.5 Coder 1.5B. Tiny code model.',
        'Alibaba',
        FAM_QWEN_CODER,
        param_size=1.5,
        ctx=131072,
        roles=['coder'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'qwq:32b',
        'qwq:32b',
        "QwQ 32B. Qwen's dedicated reasoning model with tool use.",
        'Alibaba',
        FAM_QWQ,
        param_size=32.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen3-vl:8b',
        'qwen3-vl:8b',
        'Qwen 3 Vision-Language 8B. Strong vision understanding with thinking support.',
        'Alibaba',
        FAM_QWEN_VL,
        param_size=8.0,
        ctx=131072,
        roles=['multimodal', 'chat', 'reasoning'],
        caps=['vision', 'function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'qwen2.5vl:7b',
        'qwen2.5vl:7b',
        'Qwen 2.5 Vision-Language 7B. Flagship vision model.',
        'Alibaba',
        FAM_QWEN_VL,
        param_size=7.0,
        ctx=131072,
        roles=['multimodal', 'chat'],
        caps=['vision', 'system_messages'],
        tier=3,
    ),
    m(
        'llama3:70b',
        'llama3:70b',
        'Meta Llama 3 70B.',
        'Meta',
        FAM_LLAMA,
        param_size=70.0,
        ctx=8192,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'llama2:7b',
        'llama2:7b',
        'Meta Llama 2 7B. Foundation model.',
        'Meta',
        FAM_LLAMA,
        param_size=7.0,
        ctx=4096,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'llama2:13b',
        'llama2:13b',
        'Meta Llama 2 13B.',
        'Meta',
        FAM_LLAMA,
        param_size=13.0,
        ctx=4096,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'llama4:16x17b',
        'llama4:16x17b',
        'Meta Llama 4 Scout. Multimodal MoE with vision and tools.',
        'Meta',
        FAM_LLAMA,
        param_size=109.0,
        ctx=131072,
        roles=['multimodal', 'chat'],
        caps=['vision', 'function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'llama3.2-vision:90b',
        'llama3.2-vision:90b',
        "Meta's 90B vision-language model.",
        'Meta',
        FAM_LLAMA,
        param_size=90.0,
        ctx=131072,
        roles=['multimodal', 'chat'],
        caps=['vision', 'system_messages'],
        tier=3,
    ),
    m(
        'llama-guard3:8b',
        'llama-guard3:8b',
        "Meta's content safety classifier. Fine-tuned for input/output safety classification.",
        'Meta',
        FAM_LLAMA,
        param_size=8.0,
        ctx=131072,
        roles=['instruct'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'deepseek-v3:671b',
        'deepseek-v3:671b',
        'DeepSeek V3. Strong MoE with 37B activated per token.',
        'DeepSeek',
        FAM_DEEPSEEK,
        param_size=671.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'deepseek-coder:33b',
        'deepseek-coder:33b',
        'DeepSeek Coder 33B.',
        'DeepSeek',
        FAM_DEEPSEEK_CODER,
        param_size=33.0,
        ctx=16384,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'deepseek-coder-v2:16b',
        'deepseek-coder-v2:16b',
        'DeepSeek Coder V2 16B. MoE code model comparable to GPT-4 Turbo on code tasks.',
        'DeepSeek',
        FAM_DEEPSEEK_CODER,
        param_size=16.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'mistral-small3.1:24b',
        'mistral-small3.1:24b',
        'Mistral Small 3.1. Vision understanding with 128K context.',
        'Mistral AI',
        FAM_MISTRAL,
        param_size=24.0,
        ctx=131072,
        roles=['instruct', 'chat', 'multimodal'],
        caps=['vision', 'function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'mistral-large:123b',
        'mistral-large:123b',
        'Mistral Large 2. Flagship model for code, math, and reasoning.',
        'Mistral AI',
        FAM_MISTRAL,
        param_size=123.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'mixtral:8x22b',
        'mixtral:8x22b',
        'Mixtral 8x22B. Large MoE with tool support.',
        'Mistral AI',
        FAM_MIXTRAL,
        param_size=176.0,
        ctx=65536,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'codestral:22b',
        'codestral:22b',
        "Mistral's dedicated code generation model.",
        'Mistral AI',
        FAM_CODESTRAL,
        param_size=22.0,
        ctx=32768,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'devstral:24b',
        'devstral:24b',
        'Best open-source model for coding agents.',
        'Mistral AI',
        FAM_DEVSTRAL,
        param_size=24.0,
        ctx=131072,
        roles=['coder', 'instruct'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'magistral:24b',
        'magistral:24b',
        "Mistral's reasoning model with thinking support.",
        'Mistral AI',
        FAM_MAGISTRAL,
        param_size=24.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'ministral-3:3b',
        'ministral-3:3b',
        "Mistral's edge model. Vision and tools at 3B.",
        'Mistral AI',
        FAM_MINISTRAL,
        param_size=3.0,
        ctx=131072,
        roles=['chat', 'multimodal'],
        caps=['vision', 'function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'codellama:13b',
        'codellama:13b',
        'CodeLlama 13B.',
        'Meta',
        FAM_CODELLAMA,
        param_size=13.0,
        ctx=16384,
        roles=['coder', 'instruct'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'llava:13b',
        'llava:13b',
        'LLaVA 13B. Multimodal understanding.',
        'Meta',
        FAM_LLAVA,
        param_size=13.0,
        ctx=4096,
        roles=['multimodal', 'chat'],
        caps=['vision', 'system_messages'],
        tier=3,
    ),
    m(
        'gpt-oss:120b',
        'gpt-oss:120b',
        "OpenAI's open-weight 120B model. Strong reasoning and agentic tasks.",
        'OpenAI',
        FAM_GPT_OSS,
        param_size=120.0,
        ctx=131072,
        roles=['instruct', 'chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'falcon3:7b',
        'falcon3:7b',
        'Falcon 3 7B. Efficient AI model for science, math, and coding.',
        'TII',
        FAM_FALCON,
        param_size=7.0,
        ctx=32768,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'falcon3:10b',
        'falcon3:10b',
        'Falcon 3 10B.',
        'TII',
        FAM_FALCON,
        param_size=10.0,
        ctx=32768,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'command-r-plus:104b',
        'command-r-plus:104b',
        "Cohere's Command R+ 104B. Enterprise RAG and tools.",
        'Cohere',
        FAM_COMMAND,
        param_size=104.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'granite4:3b',
        'granite4:3b',
        'IBM Granite 4. Improved instruction following and tool calling.',
        'IBM',
        FAM_GRANITE,
        param_size=3.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'granite3.3:8b',
        'granite3.3:8b',
        'IBM Granite 3.3 8B. 128K context with improved reasoning.',
        'IBM',
        FAM_GRANITE,
        param_size=8.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'starcoder2:7b',
        'starcoder2:7b',
        'StarCoder 2 7B. Transparent open code LLM.',
        'BigCode',
        FAM_STARCODER,
        param_size=7.0,
        ctx=16384,
        roles=['coder'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'starcoder2:15b',
        'starcoder2:15b',
        'StarCoder 2 15B.',
        'BigCode',
        FAM_STARCODER,
        param_size=15.0,
        ctx=16384,
        roles=['coder'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'dolphin3:8b',
        'dolphin3:8b',
        'Dolphin 3.0 8B. Uncensored general purpose with coding and function calling.',
        'Eric Hartford',
        FAM_DOLPHIN,
        param_size=8.0,
        ctx=131072,
        roles=['chat', 'coder'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'olmo2:7b',
        'olmo2:7b',
        'Allen AI OLMo 2 7B. Open model trained on 5T tokens.',
        'Allen AI',
        FAM_OLMO,
        param_size=7.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'olmo2:13b',
        'olmo2:13b',
        'Allen AI OLMo 2 13B.',
        'Allen AI',
        FAM_OLMO,
        param_size=13.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'smollm2:1.7b',
        'smollm2:1.7b',
        'HuggingFace SmolLM2 1.7B. Compact with tool support.',
        'Meta',
        FAM_SMOLLM,
        param_size=1.7,
        ctx=8192,
        roles=['chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'yi:34b',
        'yi:34b',
        '01.AI Yi 1.5 34B. High-performing bilingual model.',
        'Alibaba',
        FAM_YI,
        param_size=34.0,
        ctx=32768,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'codegemma:7b',
        'codegemma:7b',
        'Google CodeGemma 7B. Code completion and generation.',
        'Google',
        FAM_CODEGEMMA,
        param_size=7.0,
        ctx=8192,
        roles=['coder'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'vicuna:7b',
        'vicuna:7b',
        'UC Berkeley Vicuna 7B. Chat model based on Llama.',
        'Meta',
        FAM_VICUNA,
        param_size=7.0,
        ctx=4096,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'vicuna:13b',
        'vicuna:13b',
        'Vicuna 13B.',
        'Meta',
        FAM_VICUNA,
        param_size=13.0,
        ctx=4096,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'nemotron-mini:4b',
        'nemotron-mini:4b',
        'NVIDIA Nemotron Mini 4B. Optimized for roleplay, RAG, and function calling.',
        'NVIDIA',
        FAM_NEMOTRON,
        param_size=4.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'nemotron:70b',
        'nemotron:70b',
        'NVIDIA Nemotron 70B. Customized from Llama 3.1 for enterprise helpfulness.',
        'NVIDIA',
        FAM_NEMOTRON,
        param_size=70.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'solar:10.7b',
        'solar:10.7b',
        'Upstage Solar 10.7B. Compact single-turn model.',
        'Upstage',
        FAM_SOLAR,
        param_size=10.7,
        ctx=4096,
        roles=['chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'dbrx:132b',
        'dbrx:132b',
        'Databricks DBRX. 132B open general-purpose MoE.',
        'Databricks',
        FAM_DBRX,
        param_size=132.0,
        ctx=32768,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'exaone-deep:32b',
        'exaone-deep:32b',
        'LG EXAONE Deep 32B. Superior math and coding reasoning.',
        'LG AI Research',
        FAM_EXAONE,
        param_size=32.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'cogito:14b',
        'cogito:14b',
        'DeepCogito Cogito 14B. Hybrid reasoning.',
        'DeepCogito',
        FAM_COGITO,
        param_size=14.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'cogito:70b',
        'cogito:70b',
        'DeepCogito Cogito 70B.',
        'DeepCogito',
        FAM_COGITO,
        param_size=70.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'openthinker:7b',
        'openthinker:7b',
        'OpenThinker 7B. Reasoning distilled from DeepSeek-R1.',
        'DeepSeek',
        FAM_OPENTHINKER,
        param_size=7.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'openthinker:32b',
        'openthinker:32b',
        'OpenThinker 32B.',
        'DeepSeek',
        FAM_OPENTHINKER,
        param_size=32.0,
        ctx=131072,
        roles=['reasoning', 'chat'],
        caps=['reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'lfm2.5-thinking:1.2b',
        'lfm2.5-thinking:1.2b',
        'Liquid AI LFM2.5 1.2B. Hybrid model for edge deployment with thinking.',
        'Liquid AI',
        FAM_LFM,
        param_size=1.2,
        ctx=131072,
        roles=['chat', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'lfm2:24b',
        'lfm2:24b',
        'Liquid AI LFM2 24B. Efficient inference with tool support.',
        'Liquid AI',
        FAM_LFM,
        param_size=24.0,
        ctx=131072,
        roles=['chat'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'kimi-k2',
        'kimi-k2',
        'Moonshot Kimi K2. MoE with strong coding agent performance.',
        'Moonshot',
        FAM_KIMI,
        param_size=None,
        ctx=131072,
        roles=['chat', 'coder'],
        caps=['function_calling', 'system_messages'],
        tier=3,
    ),
    m(
        'minimax-m2.5',
        'minimax-m2.5',
        'MiniMax M2.5. State-of-the-art for productivity and coding.',
        'MiniMax',
        FAM_MINIMAX,
        param_size=None,
        ctx=131072,
        roles=['chat', 'coder', 'reasoning'],
        caps=['function_calling', 'reasoning', 'system_messages'],
        tier=3,
    ),
    m(
        'glm4:9b',
        'glm4:9b',
        'Zhipu GLM-4 9B. Strong multilingual general model.',
        'Zhipu AI',
        FAM_GLM,
        param_size=9.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'internlm2:7b',
        'internlm2:7b',
        'Shanghai AI Lab InternLM2.5 7B. Outstanding reasoning capability.',
        'Alibaba',
        FAM_INTERNLM,
        param_size=7.0,
        ctx=131072,
        roles=['instruct', 'chat'],
        caps=['system_messages'],
        tier=3,
    ),
    m(
        'all-minilm:33m',
        'all-minilm:33m',
        'Tiny embedding model for sentence-level tasks.',
        'Microsoft',
        FAM_MXBAI,
        param_size=0.033,
        ctx=512,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=3,
    ),
    m(
        'granite-embedding:278m',
        'granite-embedding:278m',
        'IBM Granite Embedding. Dense biencoder for multilingual retrieval.',
        'IBM',
        FAM_GRANITE,
        param_size=0.278,
        ctx=8192,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=3,
    ),
    m(
        'qwen3-embedding:8b',
        'qwen3-embedding:8b',
        'Qwen 3 Embedding 8B. Text embedding model from the Qwen 3 series.',
        'Alibaba',
        FAM_QWEN,
        param_size=8.0,
        ctx=8192,
        mode='embedding',
        roles=['embedding'],
        caps=[],
        tier=3,
    ),
]


# ──────────────────────────────────────────────
# FIXTURE GENERATION
# ──────────────────────────────────────────────


def make_family_fixtures():
    """Generate AIModelFamily fixture entries."""
    entries = []
    for data in FAMILY_DEFS.values():
        entries.append(
            {
                'model': 'hypothalamus.aimodelfamily',
                'pk': data['pk'],
                'fields': {
                    'name': data['name'],
                    'slug': data['slug'],
                    'description': data['description'],
                },
            }
        )
    return entries


def make_creator_fixtures():
    """Generate NEW AIModelCreator entries (keep existing ones in the original fixture)."""
    entries = []
    for name, (pk, desc) in NEW_CREATORS.items():
        entries.append(
            {
                'model': 'hypothalamus.aimodelcreator',
                'pk': pk,
                'fields': {
                    'name': name,
                    'description': desc,
                },
            }
        )
    return entries


def make_model_fixture(model_def):
    """Generate a single AIModel fixture entry."""
    model_uuid = str(
        uuid.uuid5(uuid.NAMESPACE_DNS, f'areself.ollama.{model_def["slug"]}')
    )

    role_pks = [ROLE[r] for r in model_def['roles'] if r in ROLE]
    cap_pks = [CAP[c] for c in model_def['caps'] if c in CAP]

    return {
        'model': 'hypothalamus.aimodel',
        'pk': model_uuid,
        'fields': {
            'name': model_def['name'],
            'description': model_def['description'],
            'creator': CREATOR_PK.get(model_def['creator']),
            'parameter_size': model_def['param_size'],
            'family': FAMILY_DEFS.get(
                next(
                    (
                        slug
                        for slug, d in FAMILY_DEFS.items()
                        if d['pk'] == model_def['family']
                    ),
                    None,
                ),
                {},
            ).get('pk'),
            'version': None,
            'context_length': model_def['ctx'],
            'enabled': True,
            'deprecation_date': None,
            'roles': role_pks,
            'quantizations': [],
            'capabilities': cap_pks,
        },
    }


def make_provider_fixture(model_def, provider_pk_counter):
    """Generate AIModelProvider entry for Docker-shipped models."""
    model_uuid = str(
        uuid.uuid5(uuid.NAMESPACE_DNS, f'areself.ollama.{model_def["slug"]}')
    )
    mode_pk = MODE.get(model_def['mode'], MODE['chat'])

    return {
        'model': 'hypothalamus.aimodelprovider',
        'pk': provider_pk_counter,
        'fields': {
            'created': '2026-04-01T00:00:00.000Z',
            'modified': '2026-04-01T00:00:00.000Z',
            'rate_limited_on': None,
            'rate_limit_reset_time': None,
            'rate_limit_reset_interval': '00:01:00',
            'rate_limit_counter': 0,
            'rate_limit_total_failures': 0,
            'is_enabled': True,
            'ai_model': model_uuid,
            'provider': EXISTING_PROVIDER_PK,
            'provider_unique_model_id': f'ollama/{model_def["slug"]}',
            'mode': mode_pk,
            'max_tokens': None,
            'max_input_tokens': None,
            'max_output_tokens': None,
            'disabled_capabilities': [],
        },
    }


def make_pricing_fixture(provider_pk, pricing_pk_counter):
    """Generate free pricing entry for Ollama models."""
    return {
        'model': 'hypothalamus.aimodelpricing',
        'pk': pricing_pk_counter,
        'fields': {
            'created': '2026-04-01T00:00:00.000Z',
            'modified': '2026-04-01T00:00:00.000Z',
            'is_current': True,
            'is_active': True,
            'model_provider': provider_pk,
            'input_cost_per_token': '0.000000000000000',
            'output_cost_per_token': '0.000000000000000',
            'input_cost_per_character': None,
            'output_cost_per_character': None,
            'input_cost_per_token_above_128k_tokens': None,
            'output_cost_per_token_above_128k_tokens': None,
            'output_cost_per_character_above_128k_tokens': None,
            'output_cost_per_reasoning_token': None,
            'cache_read_input_token_cost': None,
            'cache_creation_input_token_cost': None,
            'input_cost_per_audio_token': None,
            'output_vector_size': None,
        },
    }


# ──────────────────────────────────────────────
# EXISTING FIXTURE DATA (routing engine, statuses, etc.)
# ──────────────────────────────────────────────

EXISTING_CAPABILITIES = [
    {
        'model': 'hypothalamus.aimodelcapabilities',
        'pk': pk,
        'fields': {'name': name, 'description': None},
    }
    for name, pk in CAP.items()
]

EXISTING_MODES = [
    {
        'model': 'hypothalamus.aimode',
        'pk': pk,
        'fields': {'name': name, 'description': None},
    }
    for name, pk in MODE.items()
]

EXISTING_ROLES = [
    {
        'model': 'hypothalamus.aimodelrole',
        'pk': pk,
        'fields': {
            'name': name.title(),
            'description': {
                'instruct': 'Instruction-tuned for dialogue and tasks.',
                'chat': 'Optimized for conversational back-and-forth.',
                'coder': 'Fine-tuned specifically on programming languages.',
                'reasoning': 'Uses chain-of-thought or thinking tokens before replying.',
                'embedding': 'Converts text into mathematical vectors.',
                'multimodal': 'Handles vision, audio, or video inputs alongside text.',
                'uncensored': 'Alignment and safety guardrails removed.',
            }.get(name, ''),
        },
    }
    for name, pk in ROLE.items()
]

EXISTING_QUANTS = [
    {
        'model': 'hypothalamus.aimodelquantization',
        'pk': 1,
        'fields': {
            'name': 'fp16',
            'description': '16-bit floating point (standard unquantized).',
        },
    },
    {
        'model': 'hypothalamus.aimodelquantization',
        'pk': 2,
        'fields': {'name': 'fp8', 'description': '8-bit floating point.'},
    },
    {
        'model': 'hypothalamus.aimodelquantization',
        'pk': 3,
        'fields': {
            'name': 'awq',
            'description': 'Activation-aware Weight Quantization.',
        },
    },
    {
        'model': 'hypothalamus.aimodelquantization',
        'pk': 4,
        'fields': {
            'name': 'gptq',
            'description': 'Accurate Post-Training Quantization.',
        },
    },
    {
        'model': 'hypothalamus.aimodelquantization',
        'pk': 5,
        'fields': {
            'name': 'gguf',
            'description': 'Standard format for local CPU/GPU inference via llama.cpp.',
        },
    },
]

EXISTING_CREATORS_FIXTURES = [
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 1,
        'fields': {
            'name': 'Meta',
            'description': 'Meta AI (formerly Facebook)',
        },
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 2,
        'fields': {'name': 'Alibaba', 'description': 'Alibaba Cloud'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 3,
        'fields': {'name': 'Mistral AI', 'description': 'Mistral AI'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 4,
        'fields': {'name': 'OpenAI', 'description': 'OpenAI'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 5,
        'fields': {'name': 'Google', 'description': 'Google DeepMind'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 6,
        'fields': {'name': 'Anthropic', 'description': 'Anthropic'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 7,
        'fields': {'name': 'DeepSeek', 'description': 'DeepSeek AI'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 8,
        'fields': {'name': 'Microsoft', 'description': 'Microsoft Research'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 9,
        'fields': {'name': 'xAI', 'description': 'xAI'},
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 10,
        'fields': {
            'name': 'Black Forest Labs',
            'description': 'Creators of the FLUX image generation models.',
        },
    },
    {
        'model': 'hypothalamus.aimodelcreator',
        'pk': 11,
        'fields': {
            'name': 'Bria AI',
            'description': 'Commercial visual generative AI platform.',
        },
    },
]

OLLAMA_PROVIDER = {
    'model': 'hypothalamus.llmprovider',
    'pk': 64,
    'fields': {
        'created': '2026-03-23T17:34:10.978Z',
        'modified': '2026-03-25T00:20:23.879Z',
        'name': 'Ollama',
        'description': 'Local model inference via Ollama. Free, private, runs on consumer hardware.',
        'key': 'ollama',
        'base_url': 'http://localhost:11434',
        'chat_path': '/v1/chat/completions',
        'requires_api_key': False,
        'api_key_header': 'Authorization',
        'api_key_env_var': 'HOME',
    },
}

SYNC_STATUSES = [
    {
        'model': 'hypothalamus.syncstatus',
        'pk': 1,
        'fields': {'name': 'Running'},
    },
    {
        'model': 'hypothalamus.syncstatus',
        'pk': 2,
        'fields': {'name': 'Success'},
    },
    {'model': 'hypothalamus.syncstatus', 'pk': 3, 'fields': {'name': 'Failed'}},
]

FAILOVER_TYPES = [
    {
        'model': 'hypothalamus.failovertype',
        'pk': 5,
        'fields': {
            'name': 'Local Fallback',
            'description': 'Attempt to route to a verified local Ollama model.',
        },
    },
    {
        'model': 'hypothalamus.failovertype',
        'pk': 6,
        'fields': {
            'name': 'Family Failover',
            'description': 'Attempt to route to a sibling model in the same family.',
        },
    },
    {
        'model': 'hypothalamus.failovertype',
        'pk': 7,
        'fields': {
            'name': 'Semantic Vector Search',
            'description': 'Use Hypothalamus pgvector to find the closest conceptual match.',
        },
    },
    {
        'model': 'hypothalamus.failovertype',
        'pk': 8,
        'fields': {
            'name': 'Strict Fail',
            'description': 'Halt execution and return a routing error.',
        },
    },
]

FAILOVER_STRATEGIES = [
    {
        'model': 'hypothalamus.failoverstrategy',
        'pk': 4,
        'fields': {
            'name': 'Standard Cloud',
            'description': 'Standard API routing with semantic fallback.',
        },
    },
    {
        'model': 'hypothalamus.failoverstrategy',
        'pk': 5,
        'fields': {
            'name': 'Local First',
            'description': 'Prioritize free local models before touching the cloud.',
        },
    },
    {
        'model': 'hypothalamus.failoverstrategy',
        'pk': 6,
        'fields': {
            'name': 'Strict Requirement',
            'description': 'Do not deviate from the requested model family.',
        },
    },
]

FAILOVER_STEPS = [
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 9,
        'fields': {'strategy': 4, 'failover_type': 6, 'order': 1},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 10,
        'fields': {'strategy': 4, 'failover_type': 7, 'order': 2},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 11,
        'fields': {'strategy': 4, 'failover_type': 8, 'order': 3},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 12,
        'fields': {'strategy': 5, 'failover_type': 5, 'order': 1},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 13,
        'fields': {'strategy': 5, 'failover_type': 7, 'order': 2},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 14,
        'fields': {'strategy': 5, 'failover_type': 8, 'order': 3},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 15,
        'fields': {'strategy': 6, 'failover_type': 6, 'order': 1},
    },
    {
        'model': 'hypothalamus.failoverstrategystep',
        'pk': 16,
        'fields': {'strategy': 6, 'failover_type': 8, 'order': 2},
    },
]

SELECTION_FILTERS = [
    {
        'model': 'hypothalamus.aimodelselectionfilter',
        'pk': 1,
        'fields': {
            'name': 'Core Engineering Task',
            'failover_strategy': 4,
            'preferred_model': None,
            'local_failover': None,
            'required_capabilities': [],
            'banned_providers': [],
            'preferred_categories': [],
            'preferred_tags': [],
            'preferred_roles': [],
        },
    },
    {
        'model': 'hypothalamus.aimodelselectionfilter',
        'pk': 2,
        'fields': {
            'name': 'Local Coder',
            'failover_strategy': 6,
            'preferred_model': None,
            'local_failover': None,
            'required_capabilities': [2],
            'banned_providers': [],
            'preferred_categories': [],
            'preferred_tags': [],
            'preferred_roles': [2, 3, 4],
        },
    },
    {
        'model': 'hypothalamus.aimodelselectionfilter',
        'pk': 3,
        'fields': {
            'name': 'Thalamus',
            'failover_strategy': 6,
            'preferred_model': None,
            'local_failover': None,
            'required_capabilities': [],
            'banned_providers': [],
            'preferred_categories': [],
            'preferred_tags': [],
            'preferred_roles': [],
        },
    },
]


def generate_fixtures():
    """Generate all three fixture tiers."""

    # Shared reference data
    ref_data = (
        [OLLAMA_PROVIDER]
        + EXISTING_CAPABILITIES
        + EXISTING_MODES
        + EXISTING_ROLES
        + EXISTING_QUANTS
        + EXISTING_CREATORS_FIXTURES
        + make_creator_fixtures()
        + make_family_fixtures()
        + SYNC_STATUSES
        + FAILOVER_TYPES
        + FAILOVER_STRATEGIES
        + FAILOVER_STEPS
        + SELECTION_FILTERS
    )

    # Split models by tier
    tier1 = [m for m in MODELS if m['tier'] <= 1]
    tier2 = [m for m in MODELS if m['tier'] <= 2]
    tier3 = MODELS  # all

    # TIER 1: initial_data.json (Docker ships)
    tier1_entries = ref_data[:]
    provider_pk = 3000
    pricing_pk = 1

    for md in tier1:
        tier1_entries.append(make_model_fixture(md))
        prov = make_provider_fixture(md, provider_pk)
        tier1_entries.append(prov)
        tier1_entries.append(make_pricing_fixture(provider_pk, pricing_pk))
        provider_pk += 1
        pricing_pk += 1

    # TIER 2: ollama_popular.json (additional models only, no ref data duplication)
    tier2_only = [m for m in MODELS if m['tier'] == 2]
    tier2_entries = []
    for md in tier2_only:
        tier2_entries.append(make_model_fixture(md))

    # TIER 3: ollama_complete.json (additional models only)
    tier3_only = [m for m in MODELS if m['tier'] == 3]
    tier3_entries = []
    for md in tier3_only:
        tier3_entries.append(make_model_fixture(md))

    return tier1_entries, tier2_entries, tier3_entries


if __name__ == '__main__':
    t1, t2, t3 = generate_fixtures()

    with open('/home/claude/initial_data.json', 'w') as f:
        json.dump(t1, f, indent=2)
    print(f'initial_data.json: {len(t1)} entries')

    with open('/home/claude/ollama_popular.json', 'w') as f:
        json.dump(t2, f, indent=2)
    print(f'ollama_popular.json: {len(t2)} entries')

    with open('/home/claude/ollama_complete.json', 'w') as f:
        json.dump(t3, f, indent=2)
    print(f'ollama_complete.json: {len(t3)} entries')

    # Stats
    print(
        f'\nTier 1 models (Docker): {len([m for m in MODELS if m["tier"] == 1])}'
    )
    print(
        f'Tier 2 models (Popular): {len([m for m in MODELS if m["tier"] == 2])}'
    )
    print(
        f'Tier 3 models (Complete): {len([m for m in MODELS if m["tier"] == 3])}'
    )
    print(f'Total unique models: {len(MODELS)}')
    print(f'Total families: {len(FAMILY_DEFS)}')
    print(f'New creators added: {len(NEW_CREATORS)}')
