import re
from dataclasses import dataclass, field


@dataclass
class AIModelSemanticParseResult:
    """Result of parsing a model identifier string."""

    raw_string: str
    success: bool
    provider: str | None = None
    provider_region: str | None = None
    creator: str | None = None
    family: str | None = None
    version: str | None = None
    parameter_size: str | None = None
    roles: list[str] = field(default_factory=list)
    quantizations: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    unmanageable: bool = False
    unmanageable_reason: str | None = None


# ──────────────────────────────────────────────
# KNOWN PROVIDERS — order matters (longest first for prefix matching)
# ──────────────────────────────────────────────
PROVIDERS = [
    'fireworks_ai/accounts/fireworks/models',
    'text-completion-codestral',
    'vercel_ai_gateway',
    'bedrock_mantle',
    'github_copilot',
    'nvidia_nim',
    'amazon-nova',
    'black_forest_labs',
    'fireworks_ai',
    'together_ai',
    'codestral',
    'deepinfra',
    'gradient_ai',
    'azure_ai',
    'cerebras',
    'chatgpt',
    'cloudflare',
    'dashscope',
    'deepgram',
    'deepseek',
    'elevenlabs',
    'fal_ai',
    'featherless_ai',
    'friendliai',
    'gigachat',
    'groq',
    'heroku',
    'hyperbolic',
    'lambda_ai',
    'lemonade',
    'linkup',
    'llamagate',
    'meta_llama',
    'minimax',
    'mistral',
    'moonshot',
    'morph',
    'nebius',
    'novita',
    'nscale',
    'nvidia_nim',
    'oci',
    'openrouter',
    'ovhcloud',
    'palm',
    'parallel_ai',
    'perplexity',
    'publicai',
    'recraft',
    'replicate',
    'runwayml',
    'sagemaker',
    'sambanova',
    'serper',
    'snowflake',
    'stability',
    'tavily',
    'vertex_ai',
    'volcengine',
    'voyage',
    'wandb',
    'watsonx',
    'xai',
    'azure',
    'aiml',
    'assemblyai',
    'aws_polly',
    'bedrock',
    'cohere',
    'dataforseo',
    'duckduckgo',
    'exa_ai',
    'firecrawl',
    'gmi',
    'google_pse',
    'ollama',
    'openai',
    'searxng',
    'sarvam',
    'v0',
    'zai',
]

# Bedrock region patterns
BEDROCK_REGION_RE = re.compile(
    r'^bedrock/([a-z]{2}-[a-z]+-\d|invoke|\*)'
)
AZURE_REGION_RE = re.compile(
    r'^azure/(eu|us|apac|global|global-standard|speech)/'
)

# ──────────────────────────────────────────────
# FAMILY DEFINITIONS — (canonical_name, list_of_slug_patterns)
# Ordered so longer/more-specific slugs match first within each family
# ──────────────────────────────────────────────
FAMILY_PATTERNS = [
    # Anthropic
    ('Claude', [
        'claude-opus', 'claude-sonnet', 'claude-haiku',
        'claude-instant', 'claude',
    ]),
    # OpenAI
    ('GPT-OSS', ['gpt-oss']),
    ('GPT-Image', ['gpt-image']),
    ('GPT-Realtime', ['gpt-realtime']),
    ('GPT-Audio', ['gpt-audio']),
    ('GPT', [
        'gpt-5', 'gpt-4o', 'gpt-4.1', 'gpt-4', 'gpt-3.5',
        'gpt-35',  # azure naming
    ]),
    ('o-series', ['o4-mini', 'o3-pro', 'o3-mini', 'o3', 'o1-pro', 'o1-mini', 'o1']),
    ('DALL-E', ['dall-e']),
    ('Sora', ['sora']),
    ('Codex', ['codex']),
    ('Whisper', ['whisper']),
    ('TTS', ['tts-1']),
    # Google
    ('Gemini', ['gemini']),
    ('Gemma', ['gemma']),
    ('Imagen', ['imagen']),
    ('Veo', ['veo']),
    ('PaLM', ['chat-bison', 'text-bison']),
    ('LearnLM', ['learnlm']),
    # Meta
    ('Llama', [
        'llama-guard', 'llama-4', 'llama-3.3', 'llama-3.2',
        'llama-3.1', 'llama-3', 'llama-2', 'llama',
        'llama4', 'llama3.3', 'llama3.2', 'llama3.1',
        'llama3', 'llama2',
    ]),
    # Mistral
    ('Codestral', ['codestral']),
    ('Devstral', ['devstral']),
    ('Magistral', ['magistral']),
    ('Ministral', ['ministral']),
    ('Pixtral', ['pixtral']),
    ('Mixtral', ['mixtral']),
    ('Mistral', ['mistral']),
    ('Voxtral', ['voxtral']),
    # DeepSeek (before Qwen to prevent qwen stealing deepseek-r1-distill-qwen)
    ('DeepSeek', [
        'deepseek-r1', 'deepseek-v3', 'deepseek-v2',
        'deepseek-coder', 'deepseek-prover',
        'deepseek-chat', 'deepseek-reasoner', 'deepseek-ocr',
        'deepseek-llama', 'deepseek',
    ]),
    # Alibaba / Qwen
    ('Qwen', [
        'qwen3.5', 'qwen3-coder', 'qwen3-vl', 'qwen3-next',
        'qwen3-omni', 'qwen3', 'qwen2.5-coder', 'qwen2.5-vl',
        'qwen2.5', 'qwen2-vl', 'qwen2', 'qwen1.5',
        'qwen-vl', 'qwen-mt', 'qwen-plus', 'qwen-max',
        'qwen-turbo', 'qwen-flash', 'qwen-coder', 'qwen',
        'qwen25',  # fireworks p-notation: qwen25 = qwen2.5
        'qwq',
    ]),
    # Cohere
    ('Command', ['command-r', 'command-a', 'command-light', 'command-nightly', 'command']),
    ('Cohere-Embed', ['cohere-embed', 'embed-english', 'embed-multilingual', 'cohere.embed', 'embed-v']),
    ('Cohere-Rerank', ['cohere-rerank', 'rerank']),
    # AI21
    ('Jamba', ['jamba']),
    ('Jurassic', ['j2-mid', 'j2-light', 'j2-ultra', 'ai21.j2']),
    # Microsoft
    ('Phi', ['phi-4', 'phi-3.5', 'phi-3', 'phi-2', 'phi']),
    # Amazon
    ('Nova', ['nova-2', 'nova-premier', 'nova-pro', 'nova-lite', 'nova-micro', 'nova-canvas', 'nova']),
    ('Titan', ['titan']),
    # Stability
    ('Stable Diffusion', ['stable-diffusion', 'sd3.5', 'sd3', 'ssd-1b']),
    ('Stable Image', [
        'stable-image', 'stable-creative', 'stable-conservative',
        'stable-fast', 'stable-style', 'stable-outpaint',
    ]),
    # FLUX
    ('FLUX', ['flux-kontext', 'flux-pro', 'flux-dev', 'flux-realism', 'flux']),
    # Moonshot / Kimi
    ('Kimi', ['kimi-k2', 'kimi-latest', 'kimi-thinking', 'kimi']),
    ('Moonshot', ['moonshot']),
    # MiniMax
    ('MiniMax', ['minimax-m2', 'minimax-m1', 'minimax-01', 'minimax']),
    # GLM (Zhipu AI)
    ('GLM', [
        'glm-5', 'glm-4.7', 'glm-4.6', 'glm-4.5', 'glm-4',
        'glm-4p7', 'glm-4p6', 'glm-4p5', 'glm',
    ]),
    # Various
    ('Nemotron', ['nemotron']),
    ('Hermes', ['hermes']),
    ('Dolphin', ['dolphin']),
    ('CodeLlama', ['codellama', 'code-llama', 'code-qwen']),
    ('Granite', ['granite']),
    ('ERNIE', ['ernie']),
    ('Doubao', ['doubao']),
    ('Luminous', ['luminous']),
    ('Voyage', ['voyage']),
    ('MPT', ['mpt']),
    ('Yi', ['yi-large', 'yi-34b', 'yi-6b', 'yi']),
    ('DBRX', ['dbrx']),
    ('Cogito', ['cogito']),
    ('InternVL', ['internvl']),
    ('StarCoder', ['starcoder']),
    ('Nomic-Embed', ['nomic-embed']),
    ('LLaVA', ['llava']),
    ('Reka', ['reka']),
    ('Arctic', ['snowflake-arctic', 'arctic']),
    ('Falcon', ['falcon']),
    ('OLMo', ['olmo']),
    ('Mercury', ['mercury']),
    ('BGE', ['bge']),
    ('GTE', ['gte']),
    ('E5', ['e5-mistral']),
    ('Pegasus', ['pegasus']),
    ('MedLM', ['medlm']),
    ('Palmyra', ['palmyra']),
    ('JAIS', ['jais']),
    ('Allam', ['allam']),
    ('Salamandra', ['salamandra']),
    ('ALIA', ['alia']),
    ('Apertus', ['apertus']),
    ('SEA-LION', ['sea-lion']),
    ('LFM', ['lfm']),
    ('Seed', ['seed-2', 'seed-1']),
    ('Hunyuan', ['hunyuan']),
    ('MIMO', ['mimo']),
    ('Text-Embedding', ['text-embedding', 'text-multilingual-embedding']),
    ('Text-Moderation', ['text-moderation', 'omni-moderation']),
    ('Text-Unicorn', ['text-unicorn']),
    ('Marengo', ['marengo']),
    ('Multimodal-Embedding', ['multimodalembedding']),
    ('Chirp', ['chirp']),
    ('V0', ['v0-1']),
    ('Computer-Use', ['computer-use']),
    ('Deep-Research', ['deep-research']),
    ('Sonar', ['sonar']),
    ('PPLX', ['pplx']),
    ('Grok', ['grok']),
    ('Morph', ['morph']),
    ('Runway', ['gen4', 'gen3a']),
    ('Eleven', ['eleven_multilingual', 'eleven_v3']),
    ('Scribe', ['scribe']),
    ('Internlm', ['internlm']),
    ('Vicuna', ['vicuna']),
    ('Orca', ['orca-mini']),
    ('Zephyr', ['zephyr']),
    ('FireFunction', ['firefunction']),
    ('Pythia', ['pythia']),
    ('Playground', ['playground']),
    ('Dobby', ['dobby']),
    ('Trinity', ['trinity']),
    ('Cydonia', ['cydonia']),
    ('Skyfall', ['skyfall']),
    ('Rocinante', ['rocinante']),
    ('Euryale', ['euryale']),
    ('Lunaris', ['lunaris']),
    ('Goliath', ['goliath']),
    ('MythoMax', ['mythomax']),
    ('Capybara', ['capybara']),
    ('Chronos', ['chronos']),
    ('Toppy', ['toppy']),
    ('Remm', ['remm']),
    ('Weaver', ['weaver']),
    ('OpenHermes', ['openhermes']),
    ('Phind', ['phind']),
    ('OpenOrca', ['openorca']),
    ('StableCode', ['stablecode']),
    ('GigaChat', ['gigachat']),
    ('Embeddings', ['embeddings']),
    ('Catcoder', ['kat-coder', 'kat-dev']),
    ('Aion', ['aion']),
    ('Spotlight', ['spotlight']),
    ('Maestro', ['maestro']),
    ('Virtuoso', ['virtuoso']),
    ('Coder', ['coder-large']),
    ('Longcat', ['longcat']),
    ('GPT-OSS-Safeguard', ['gpt-oss-safeguard']),
    ('Fare', ['fare']),
    ('ROLM-OCR', ['rolm-ocr']),
    ('Firesearch', ['firesearch']),
    ('Solar', ['solar']),
    ('Intellect', ['intellect']),
    ('Step', ['step-3']),
    # Speech / Audio
    ('PlayAI-TTS', ['playai-tts']),
    ('MiniMax-Speech', ['speech-02', 'speech-2.6']),
    ('Azure-TTS', ['azure-tts']),
    # Misc
    ('Babbage', ['babbage']),
    ('Davinci', ['davinci']),
    ('Ada', ['ada']),
    ('CodeGeex', ['codegeex']),
    ('Ideogram', ['ideogram']),
    ('Recraft', ['recraftv3', 'recraftv2', 'recraft']),
    ('AssemblyAI', ['assemblyai']),
    ('Relace', ['relace']),
    ('RNJ', ['rnj']),
    ('Flan-T5', ['flan-t5']),
    ('MT0', ['mt0']),
    ('Inflection', ['inflection']),
    ('Magnum', ['magnum']),
    ('Baichuan', ['baichuan']),
    ('OpenThinker', ['openthinker']),
    ('Stheno', ['stheno']),
    ('Nano-Banana', ['nano-banana']),
    ('Tongyi', ['tongyi']),
    ('Chimera', ['chimera']),
    ('WizardLM', ['wizardlm']),
    ('UI-TARS', ['ui-tars']),
    ('PaddleOCR', ['paddleocr']),
    ('SeedReam', ['seedream']),
    ('Dreamina', ['dreamina']),
    ('OpenChat', ['openchat']),
    ('Llemma', ['llemma']),
    ('UnslopNemo', ['unslopnemo']),
    ('Hanami', ['hanami']),
    ('Qwerky', ['qwerky']),
    ('SSD', ['ssd']),
    ('UAE', ['uae']),
    ('ImageGen', ['imagegeneration', 'imagen4', 'imagen']),
    ('Sarvam', ['sarvam']),
    ('Perplexity-Preset', ['pro-search', 'fast-search', 'deep-research', 'advanced-deep-research']),
    ('Fireworks-ASR', ['fireworks-asr']),
    ('MAI', ['mai-ds']),
    ('Skywork', ['r1v4']),
    ('Bria', ['bria']),
]

# ──────────────────────────────────────────────
# CREATOR INFERENCE — map family to creator
# ──────────────────────────────────────────────
FAMILY_TO_CREATOR = {
    'Claude': 'Anthropic',
    'GPT': 'OpenAI', 'GPT-OSS': 'OpenAI', 'GPT-Image': 'OpenAI',
    'GPT-Realtime': 'OpenAI', 'GPT-Audio': 'OpenAI',
    'o-series': 'OpenAI', 'DALL-E': 'OpenAI', 'Sora': 'OpenAI',
    'Codex': 'OpenAI', 'Whisper': 'OpenAI', 'TTS': 'OpenAI',
    'Text-Embedding': 'OpenAI', 'Text-Moderation': 'OpenAI',
    'GPT-OSS-Safeguard': 'OpenAI',
    'Gemini': 'Google', 'Gemma': 'Google', 'Imagen': 'Google',
    'Veo': 'Google', 'PaLM': 'Google', 'LearnLM': 'Google',
    'Chirp': 'Google', 'Multimodal-Embedding': 'Google',
    'Llama': 'Meta', 'CodeLlama': 'Meta',
    'Codestral': 'Mistral', 'Devstral': 'Mistral',
    'Magistral': 'Mistral', 'Ministral': 'Mistral',
    'Pixtral': 'Mistral', 'Mixtral': 'Mistral',
    'Mistral': 'Mistral', 'Voxtral': 'Mistral',
    'Qwen': 'Alibaba',
    'DeepSeek': 'DeepSeek',
    'Command': 'Cohere', 'Cohere-Embed': 'Cohere',
    'Cohere-Rerank': 'Cohere',
    'Jamba': 'AI21', 'Jurassic': 'AI21',
    'Phi': 'Microsoft',
    'Nova': 'Amazon', 'Titan': 'Amazon',
    'Stable Diffusion': 'Stability AI', 'Stable Image': 'Stability AI',
    'FLUX': 'Black Forest Labs',
    'Kimi': 'Moonshot', 'Moonshot': 'Moonshot',
    'MiniMax': 'MiniMax',
    'GLM': 'Zhipu AI',
    'Nemotron': 'NVIDIA',
    'Grok': 'xAI',
    'ERNIE': 'Baidu',
    'Doubao': 'ByteDance',
    'Luminous': 'Aleph Alpha',
    'Voyage': 'Voyage AI',
    'Granite': 'IBM',
    'JAIS': 'G42',
    'Palmyra': 'Writer',
    'Reka': 'Reka',
    'MedLM': 'Google',
    'Text-Unicorn': 'Google',
    'Hermes': 'NousResearch',
    'Eleven': 'ElevenLabs', 'Scribe': 'ElevenLabs',
    'GigaChat': 'Sber', 'Embeddings': 'Sber',
    'Sonar': 'Perplexity', 'PPLX': 'Perplexity',
    'Morph': 'Morph',
    'Runway': 'Runway',
    'Seed': 'ByteDance',
    'Hunyuan': 'Tencent',
    'MIMO': 'Xiaomi',
    'DBRX': 'Databricks',
    'StarCoder': 'BigCode',
    'V0': 'Vercel',
    'Deep-Research': 'OpenAI',
    'Computer-Use': 'Anthropic',
    'Mercury': 'Inception',
    'OLMo': 'Allen AI',
    'LFM': 'Liquid AI',
    'Deepgram-Nova': 'Deepgram',
    'Deepgram-Base': 'Deepgram',
    'Deepgram-Enhanced': 'Deepgram',
    'Deepgram-Whisper': 'Deepgram',
    'PlayAI-TTS': 'PlayAI',
    'MiniMax-Speech': 'MiniMax',
    'AWS-Polly': 'Amazon',
    'Azure-TTS': 'Microsoft',
    'Babbage': 'OpenAI',
    'Davinci': 'OpenAI',
    'Ada': 'OpenAI',
    'CodeGeex': 'Zhipu AI',
    'Ideogram': 'Ideogram',
    'Recraft': 'Recraft',
    'Flan-T5': 'Google',
    'MT0': 'BigScience',
    'Inflection': 'Inflection',
    'Baichuan': 'Baichuan',
    'WizardLM': 'Microsoft',
    'PaddleOCR': 'Baidu',
    'SeedReam': 'ByteDance',
    'Dreamina': 'ByteDance',
    'Perplexity-Preset': 'Perplexity',
    'Fireworks-ASR': 'Fireworks AI',
    'Sarvam': 'Sarvam AI',
    'Skywork': 'Skywork',
}

# ──────────────────────────────────────────────
# CREATOR SLUG OVERRIDES — for explicit creator in path
# ──────────────────────────────────────────────
CREATOR_SLUGS = {
    'anthropic': 'Anthropic',
    'openai': 'OpenAI',
    'meta': 'Meta',
    'meta-llama': 'Meta',
    'google': 'Google',
    'mistralai': 'Mistral',
    'qwen': 'Alibaba',
    'alibaba': 'Alibaba',
    'deepseek': 'DeepSeek',
    'deepseek-ai': 'DeepSeek',
    'cohere': 'Cohere',
    'ai21': 'AI21',
    'microsoft': 'Microsoft',
    'amazon': 'Amazon',
    'stability': 'Stability AI',
    'stabilityai': 'Stability AI',
    'black-forest-labs': 'Black Forest Labs',
    'nvidia': 'NVIDIA',
    'x-ai': 'xAI',
    'xai': 'xAI',
    'z-ai': 'Zhipu AI',
    'zai': 'Zhipu AI',
    'zai-org': 'Zhipu AI',
    'baidu': 'Baidu',
    'bytedance': 'ByteDance',
    'bytedance-seed': 'ByteDance',
    'ibm': 'IBM',
    'ibm-granite': 'IBM',
    'moonshotai': 'Moonshot',
    'minimax': 'MiniMax',
    'minimaxai': 'MiniMax',
    'nousresearch': 'NousResearch',
    'allenai': 'Allen AI',
    'writer': 'Writer',
    'tencent': 'Tencent',
    'xiaomi': 'Xiaomi',
    'xiaomimimo': 'Xiaomi',
    'sao10k': 'Sao10K',
    'inflection': 'Inflection',
    'baai': 'BAAI',
    'bigscience': 'BigScience',
    'sdaia': 'SDAIA',
    'inception': 'Inception',
    'liquid': 'Liquid AI',
    'arcee-ai': 'Arcee AI',
    'upstage': 'Upstage',
    'kwaipilot': 'Kuaishou',
    'paddlepaddle': 'Baidu',
    'stepfun': 'StepFun',
    'meituan': 'Meituan',
    'prime-intellect': 'Prime Intellect',
    'bsc-lt': 'BSC',
    'swiss-ai': 'Swiss AI',
    'aisingapore': 'AI Singapore',
    'skywork': 'Skywork',
    'relace': 'Relace',
    'essentialai': 'Essential AI',
    'whoisai': 'WhereIsAI',
    'featherless-ai': 'Featherless AI',
    'thedrummer': 'TheDrummer',
    'eleutherai': 'EleutherAI',
    'anthracite-org': 'Anthracite',
    'gryphe': 'Gryphe',
    'undi95': 'Undi95',
    'alpindale': 'Alpindale',
    'alfredpros': 'AlfredPros',
    'deepcogito': 'DeepCogito',
    'tngtech': 'TNGTech',
    'cognitivecomputations': 'Cognitive Computations',
    'aion-labs': 'Aion Labs',
}

# ──────────────────────────────────────────────
# ROLES
# ──────────────────────────────────────────────
ROLE_PATTERNS = [
    'instruct', 'chat', 'embed', 'embedding', 'rerank', 'reranker',
    'vision', 'thinking', 'reasoning', 'search', 'ocr',
    'code', 'coder', 'creative', 'turbo',
    'guard', 'safeguard', 'moderation',
    'tts', 'asr', 'speech', 'transcribe', 'diarize',
    'preview', 'experimental', 'exp',
    'pro', 'mini', 'nano', 'lite', 'large', 'medium', 'small',
    'fast', 'ultra', 'plus', 'max',
    'long', 'extended', 'lightning',
    'distill',
    'fill', 'inpaint', 'outpaint', 'erase', 'sketch', 'structure',
    'style', 'upscale', 'generate', 'image',
]

# ──────────────────────────────────────────────
# QUANTIZATION PATTERNS
# ──────────────────────────────────────────────
QUANT_RE = re.compile(
    r'\b(fp8|fp16|fp32|bf16|int8|int4|'
    r'q[0-9]+_k_[a-z]+|q[0-9]+_[0-9]+|q[0-9]+|'
    r'gguf|gptq|awq|mxfp4?|mxfp-gguf|tput)\b',
    re.IGNORECASE,
)

# ──────────────────────────────────────────────
# SIZE EXTRACTION
# ──────────────────────────────────────────────
SIZE_RE = re.compile(
    r'(?:(\d+)\s*x\s*)?(\d+(?:\.\d+)?)\s*([bBmM])\b'
)

# ──────────────────────────────────────────────
# VERSION EXTRACTION — dates, semver-ish, etc.
# ──────────────────────────────────────────────
DATE_VERSION_RE = re.compile(
    r'\b(\d{4}[-]\d{2}[-]\d{2})\b'
)
SEMVER_RE = re.compile(
    r'\b[vV]?(\d+(?:\.\d+)+(?:[-][a-zA-Z0-9]+)*)\b'
)

# ──────────────────────────────────────────────
# NOISE — tokens to strip that carry no semantic value
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# PROVIDER-SPECIFIC FAMILIES — families that are too generic to match globally
# ──────────────────────────────────────────────
PROVIDER_FAMILIES = {
    'deepgram': {
        'nova-3': 'Deepgram-Nova',
        'nova-2': 'Deepgram-Nova',
        'nova': 'Deepgram-Nova',
        'base': 'Deepgram-Base',
        'enhanced': 'Deepgram-Enhanced',
        'whisper': 'Deepgram-Whisper',
    },
    'stability': {
        'erase': 'Stability-Erase',
        'style-transfer': 'Stability-Style',
        'style': 'Stability-Style',
        'inpaint': 'Stability-Inpaint',
        'outpaint': 'Stability-Outpaint',
        'sketch': 'Stability-Sketch',
        'structure': 'Stability-Structure',
        'creative': 'Stability-Creative',
        'conservative': 'Stability-Conservative',
        'fast': 'Stability-Fast',
        'remove-background': 'Stability-Remove-BG',
        'replace-background-and-relight': 'Stability-Replace-BG',
        'search-and-recolor': 'Stability-Recolor',
        'search-and-replace': 'Stability-Replace',
    },
    'assemblyai': {
        'best': 'AssemblyAI-Best',
        'nano': 'AssemblyAI-Nano',
    },
    'aws_polly': {
        'standard': 'AWS-Polly',
        'neural': 'AWS-Polly',
        'long-form': 'AWS-Polly',
        'generative': 'AWS-Polly',
    },
    'minimax': {
        'speech-02-turbo': 'MiniMax-Speech',
        'speech-02-hd': 'MiniMax-Speech',
        'speech-2.6-turbo': 'MiniMax-Speech',
        'speech-2.6-hd': 'MiniMax-Speech',
    },
    'recraft': {
        'recraftv2': 'Recraft',
        'recraftv3': 'Recraft',
    },
}

# Provider-specific family to creator
PROVIDER_FAMILY_TO_CREATOR = {
    'Deepgram-Nova': 'Deepgram',
    'Deepgram-Base': 'Deepgram',
    'Deepgram-Enhanced': 'Deepgram',
    'Deepgram-Whisper': 'Deepgram',
    'Stability-Erase': 'Stability AI',
    'Stability-Style': 'Stability AI',
    'Stability-Inpaint': 'Stability AI',
    'Stability-Outpaint': 'Stability AI',
    'Stability-Sketch': 'Stability AI',
    'Stability-Structure': 'Stability AI',
    'Stability-Creative': 'Stability AI',
    'Stability-Conservative': 'Stability AI',
    'Stability-Fast': 'Stability AI',
    'Stability-Remove-BG': 'Stability AI',
    'Stability-Replace-BG': 'Stability AI',
    'Stability-Recolor': 'Stability AI',
    'Stability-Replace': 'Stability AI',
    'AssemblyAI-Best': 'AssemblyAI',
    'AssemblyAI-Nano': 'AssemblyAI',
    'AWS-Polly': 'Amazon',
    'MiniMax-Speech': 'MiniMax',
    'Recraft': 'Recraft',
}

NOISE_TOKENS = {
    'free', 'latest', 'hf', 'pt', 'default', 'auto',
    'accounts', 'fireworks', 'models', 'fal-ai',
    'cf', 'hd', 'standard', 'low', 'medium', 'high',
    'steps', 'max', '50', '1024', '1536', '1792', '512', '256',
    'v1', 'v2', 'v0', 'v1:0', 'v2:0',
    'month', 'commitment', '1', '6',
    'maas', 'cloud',
}

# ──────────────────────────────────────────────
# UNMANAGEABLE PATTERNS — things that aren't real models
# ──────────────────────────────────────────────
UNMANAGEABLE_PREFIXES = [
    'bedrock/*/1-month',
    'bedrock/*/6-month',
]

UNMANAGEABLE_SUBSTRINGS = [
    'searxng/search', 'serper/search', 'tavily/search',
    'linkup/search', 'dataforseo/search', 'duckduckgo/search',
    'exa_ai/search', 'firecrawl/search', 'google_pse/search',
    'vertex_ai/search_api', 'perplexity/search',
    'parallel_ai/search',
    'doc-intelligence/',  # Azure AI document intelligence
    'model_router',
    'openrouter/openrouter/',  # meta routes
    'switchpoint/router',
    'openai/container',  # container deployment, not a model
    'azure/container',  # container deployment, not a model
]

# Pricing tiers (not real models)
PRICING_TIER_RE = re.compile(
    r'^(together-ai-|fireworks-ai-)'
    r'(default|up-to-|above-|\d+\.?\d*b-to-|\d+\.?\d*b-\d|moe-|embedding-)',
    re.IGNORECASE,
)


def _strip_provider(raw: str) -> tuple[str | None, str | None, str]:
    """Strip the provider prefix and optional region from the raw string.

    Returns (provider, region, remainder).
    """
    lower = raw.lower()

    # Handle bedrock regions: bedrock/us-east-1/...
    bedrock_match = BEDROCK_REGION_RE.match(lower)
    if bedrock_match:
        region = bedrock_match.group(1)
        remainder = raw[bedrock_match.end():].lstrip('/')
        return 'bedrock', region, remainder

    # Handle azure regions: azure/eu/..., azure/us/..., azure/global/...
    azure_match = AZURE_REGION_RE.match(lower)
    if azure_match:
        region = azure_match.group(1)
        remainder = raw[azure_match.end():].lstrip('/')
        return 'azure', region, remainder

    # Handle image size prefixes like 1024-x-1024/
    size_prefix_re = re.match(
        r'^(?:low|medium|high|standard|hd)?/?'
        r'(?:\d+[-]x[-]\d+/)?'
        r'(?:\d+[-]steps/)?',
        lower,
    )
    if size_prefix_re and size_prefix_re.group():
        raw = raw[size_prefix_re.end():]
        lower = raw.lower()

    for provider in PROVIDERS:
        if lower.startswith(provider + '/'):
            remainder = raw[len(provider) + 1:]
            return provider, None, remainder

    return None, None, raw


def _is_unmanageable(raw: str) -> str | None:
    """Check if this model string is one we can't meaningfully parse."""
    lower = raw.lower()
    for prefix in UNMANAGEABLE_PREFIXES:
        if lower.startswith(prefix):
            return f'Matches unmanageable prefix: {prefix}'
    for sub in UNMANAGEABLE_SUBSTRINGS:
        if sub in lower:
            return f'Contains unmanageable substring: {sub}'
    if PRICING_TIER_RE.match(lower):
        return 'Pricing tier, not a model'
    # Empty remainder after provider strip
    stripped = lower.rstrip('/')
    if stripped.endswith('/models') or stripped.endswith('/models/'):
        return 'Empty model path'
    return None


def _find_family(name: str) -> tuple[str | None, str]:
    """Find the model family from the cleaned name.

    Returns (family_name, name_with_family_removed).
    """
    lower = name.lower()
    for family_name, slugs in FAMILY_PATTERNS:
        for slug in slugs:
            idx = lower.find(slug)
            if idx != -1:
                # Remove the matched slug from the name
                before = name[:idx]
                after = name[idx + len(slug):]
                cleaned = before + ' ' + after
                return family_name, cleaned.strip()
    return None, name


def _find_creator_from_path(path_segments: list[str]) -> str | None:
    """Try to find a creator from intermediate path segments."""
    for seg in path_segments:
        seg_lower = seg.lower()
        if seg_lower in CREATOR_SLUGS:
            return CREATOR_SLUGS[seg_lower]
    return None


def _extract_sizes(name: str) -> tuple[str | None, str]:
    """Extract parameter size from the name.

    Returns (size_string, cleaned_name).
    """
    match = SIZE_RE.search(name)
    if match:
        multiplier = int(match.group(1)) if match.group(1) else 1
        base_val = match.group(2)
        unit = match.group(3).upper()
        if unit == 'M':
            # Convert millions to billions
            size_str = f'{float(base_val) * multiplier / 1000.0}B'
        else:
            if multiplier > 1:
                size_str = f'{multiplier}x{base_val}B'
            else:
                size_str = f'{base_val}B'
        cleaned = name[:match.start()] + ' ' + name[match.end():]
        return size_str, cleaned.strip()
    return None, name


def _extract_quantizations(name: str) -> tuple[list[str], str]:
    """Extract quantization tokens from the name."""
    quants = []
    cleaned = name
    for match in QUANT_RE.finditer(name):
        quants.append(match.group(0).upper())
    if quants:
        cleaned = QUANT_RE.sub(' ', name)
    return quants, cleaned.strip()


def _extract_date_version(name: str) -> tuple[str | None, str]:
    """Extract a date-based version like 2024-12-17."""
    match = DATE_VERSION_RE.search(name)
    if match:
        date_str = match.group(1)
        cleaned = name[:match.start()] + ' ' + name[match.end():]
        return date_str, cleaned.strip()
    return None, name


def _normalize_name(remainder: str) -> str:
    """Normalize the remainder for family/version extraction.

    Strips known provider noise from sub-paths, bedrock model prefixes, etc.
    """
    parts = remainder.split('/')
    # Take the last meaningful segment, but join with spaces if there
    # are interesting segments beyond just org names
    model_part = parts[-1] if parts else remainder

    # For paths like aiml/flux/dev or aiml/flux/schnell or
    # fal_ai/fal-ai/ideogram/v3
    # We want to keep the product and variant
    if len(parts) >= 2:
        # Check if second-to-last part looks like a product name
        # (not an org slug)
        for i in range(len(parts) - 1):
            seg_lower = parts[i].lower()
            if seg_lower in CREATOR_SLUGS:
                continue
            if seg_lower in (
                'fal-ai', '@cf', '@hf', 'thebloke',
                'accounts', 'fireworks', 'models',
                'ranking',
            ):
                continue
            # It might be a product segment, include it
            # But only if it's a known family slug
            for _, slugs in FAMILY_PATTERNS:
                if seg_lower in [s.lower() for s in slugs]:
                    model_part = '/'.join(parts[i:])
                    return model_part.replace('/', '-')
        model_part = parts[-1]

    return model_part


def parse_model_string(raw_string: str) -> AIModelSemanticParseResult:
    """Parse a model identifier string into its semantic components."""
    raw_string = raw_string.strip()

    if not raw_string:
        return AIModelSemanticParseResult(
            raw_string=raw_string,
            success=False,
            unmanageable=True,
            unmanageable_reason='Empty string',
        )

    # Check unmanageable
    reason = _is_unmanageable(raw_string)
    if reason:
        return AIModelSemanticParseResult(
            raw_string=raw_string,
            success=False,
            unmanageable=True,
            unmanageable_reason=reason,
        )

    # Step 0.5: Handle ft: prefix (fine-tuned models)
    ft_prefix = False
    working = raw_string
    if working.startswith('ft:'):
        ft_prefix = True
        working = working[3:]

    # Step 1: Strip provider
    provider, region, remainder = _strip_provider(working)

    # Step 2: Handle sub-path creators
    # e.g., deepinfra/meta-llama/Llama-3.3-70B-Instruct
    path_parts = remainder.split('/')
    creator_from_path = _find_creator_from_path(path_parts[:-1]) if len(path_parts) > 1 else None

    # Get the model name (last path segment typically, but handle special cases)
    model_name = _normalize_name(remainder)

    # Handle bedrock-style dotted prefixes: anthropic.claude-3-5-sonnet-20240620-v1:0
    # or meta.llama3-1-8b-instruct-v1:0
    dot_parts = model_name.split('.', 1)
    if len(dot_parts) == 2:
        prefix_lower = dot_parts[0].lower()
        # Known creator/vendor prefixes in dot notation
        dot_vendor_slugs = {
            'stability', 'twelvelabs', 'openai', 'writer',
            'cohere', 'google', 'nvidia', 'minimax',
            'moonshotai', 'qwen',
        }
        if prefix_lower in CREATOR_SLUGS:
            if not creator_from_path:
                creator_from_path = CREATOR_SLUGS[prefix_lower]
            model_name = dot_parts[1]
        elif prefix_lower in dot_vendor_slugs:
            if prefix_lower in CREATOR_SLUGS and not creator_from_path:
                creator_from_path = CREATOR_SLUGS[prefix_lower]
            model_name = dot_parts[1]

    # Also handle region-prefixed bedrock names like
    # eu.anthropic.claude-3-opus-20240229-v1:0
    # or us.meta.llama3-1-8b-instruct-v1:0
    region_prefixes = {
        'eu', 'us', 'apac', 'au', 'jp', 'global',
    }
    if dot_parts[0].lower() in region_prefixes:
        # Strip region prefix and re-parse
        after_region = dot_parts[1] if len(dot_parts) == 2 else model_name
        # Check for another dot (eu.anthropic.claude...)
        inner_dots = after_region.split('.', 1)
        if len(inner_dots) == 2 and inner_dots[0].lower() in CREATOR_SLUGS:
            if not creator_from_path:
                creator_from_path = CREATOR_SLUGS[inner_dots[0].lower()]
            model_name = inner_dots[1]
        elif len(inner_dots) == 2:
            # e.g., eu.amazon.nova-lite-v1:0
            model_name = inner_dots[1]
            if inner_dots[0].lower() in CREATOR_SLUGS and not creator_from_path:
                creator_from_path = CREATOR_SLUGS[inner_dots[0].lower()]
        else:
            model_name = after_region
        if not region and dot_parts[0].lower() in region_prefixes:
            region = dot_parts[0].lower()

    # Strip trailing :free, :latest, :exacto, :thinking, etc. but preserve the tag
    colon_match = re.search(r':([a-zA-Z_]+)$', model_name)
    colon_tag = None
    if colon_match:
        colon_tag = colon_match.group(1).lower()
        if colon_tag in ('free', 'latest', 'exacto'):
            model_name = model_name[:colon_match.start()]
        else:
            # Keep it as a tag
            model_name = model_name[:colon_match.start()]

    # Strip trailing version-like :0, :1, :2 from bedrock names
    colon_ver_match = re.search(r':(\d+)$', model_name)
    if colon_ver_match:
        model_name = model_name[:colon_ver_match.start()]

    # Strip @version suffixes like @001, @2405, @20240229, @latest, @default
    at_match = re.search(r'@([a-zA-Z0-9]+)$', model_name)
    if at_match:
        model_name = model_name[:at_match.start()]

    # Step 3: Extract date version
    date_version, model_name = _extract_date_version(model_name)

    # Step 4: Extract parameter size
    param_size, model_name = _extract_sizes(model_name)

    # Step 5: Extract quantizations
    quants, model_name = _extract_quantizations(model_name)

    # Step 6: Find family — try provider-specific first, then global
    family = None
    if provider and provider in PROVIDER_FAMILIES:
        model_lower = model_name.lower()
        for slug, fam_name in sorted(
            PROVIDER_FAMILIES[provider].items(),
            key=lambda x: len(x[0]),
            reverse=True,
        ):
            if slug in model_lower:
                family = fam_name
                model_name = model_name[:model_lower.find(slug)] + ' ' + model_name[model_lower.find(slug) + len(slug):]
                break

    if not family:
        family, model_name = _find_family(model_name)

    # Step 6b: If we have a creator from path but no family, try inferring
    # For cases like deepseek.v3.2 -> creator=DeepSeek, name="v3.2"
    if not family and creator_from_path:
        creator_to_default_family = {
            'DeepSeek': 'DeepSeek',
            'Inflection': 'Inflection',
        }
        if creator_from_path in creator_to_default_family:
            family = creator_to_default_family[creator_from_path]

    # Step 7: Infer creator
    creator = creator_from_path
    if not creator and family:
        if family in FAMILY_TO_CREATOR:
            creator = FAMILY_TO_CREATOR[family]
        elif family in PROVIDER_FAMILY_TO_CREATOR:
            creator = PROVIDER_FAMILY_TO_CREATOR[family]

    # Step 8: Extract version from what remains
    # Look for version-like patterns in the cleaned name
    version = date_version
    if not version:
        # Try semver-ish: 3.5, 4.1, v0.1, r1, etc.
        # But be careful not to grab noise
        ver_match = re.search(
            r'\b[vVrR]?(\d+(?:[.\-]\d+)*(?:[.\-][a-zA-Z]+\d*)*)\b',
            model_name,
        )
        if ver_match:
            candidate = ver_match.group(0)
            # Don't grab pure noise numbers or sizes we already caught
            if not re.match(r'^\d{1,2}$', candidate):
                version = candidate

    # Step 9: Collect roles from the model name
    # Use word boundary matching to avoid false positives
    roles = []
    full_lower = remainder.lower()
    # Tokenize by common separators
    tokens = set(re.split(r'[-_./\s]+', full_lower))
    for role in ROLE_PATTERNS:
        if role in tokens:
            roles.append(role)

    # Step 10: Build tags from remaining tokens
    tags = []
    if ft_prefix:
        tags.append('fine-tuned')
    if colon_tag and colon_tag not in ('free', 'latest', 'exacto'):
        tags.append(colon_tag)

    # Determine success
    success = family is not None or param_size is not None or creator is not None

    return AIModelSemanticParseResult(
        raw_string=raw_string,
        success=success,
        provider=provider,
        provider_region=region,
        creator=creator,
        family=family,
        version=version,
        parameter_size=param_size,
        roles=roles,
        quantizations=quants,
        tags=tags,
    )


def run_gauntlet(file_path: str, verbose: bool = False) -> None:
    """Run the parser against every line in the model list and print a report."""
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_models = [line.strip() for line in f if line.strip()]

    total = len(raw_models)
    successes = 0
    failures = []
    unmanageables = []
    no_family = []

    for raw in raw_models:
        result = parse_model_string(raw)
        if result.unmanageable:
            unmanageables.append(raw)
        elif result.success:
            successes += 1
            if not result.family:
                no_family.append(raw)
        else:
            failures.append(raw)

    print(f'\n=== GAUNTLET REPORT ===')
    print(f'Total:         {total}')
    print(f'Success:       {successes} ({100 * successes / total:.1f}%)')
    print(f'Unmanageable:  {len(unmanageables)}')
    print(f'Failures:      {len(failures)} ({100 * len(failures) / total:.1f}%)')
    print(f'No family:     {len(no_family)}')

    if failures:
        print(f'\n--- FAILURES (first 50) ---')
        for f_item in failures[:50]:
            print(f'  {f_item}')

    if no_family:
        print(f'\n--- NO FAMILY (first 30) ---')
        for nf in no_family[:30]:
            result = parse_model_string(nf)
            print(f'  {nf} -> creator={result.creator}, ver={result.version}, size={result.parameter_size}')

    if unmanageables:
        print(f'\n--- UNMANAGEABLE ({len(unmanageables)}) ---')
        for u in unmanageables:
            print(f'  {u}')

    print('========================\n')

    if verbose:
        print('\n=== DETAILED RESULTS (sample) ===')
        import random
        sample = random.sample(
            [r for r in raw_models if not _is_unmanageable(r)],
            min(50, len(raw_models)),
        )
        for raw in sorted(sample):
            r = parse_model_string(raw)
            print(
                f'  {raw}\n'
                f'    provider={r.provider} region={r.provider_region} '
                f'creator={r.creator} family={r.family}\n'
                f'    version={r.version} size={r.parameter_size} '
                f'roles={r.roles} quants={r.quantizations} tags={r.tags}'
            )
        print('=================================\n')


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'example_model_list.txt'
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    run_gauntlet(path, verbose=verbose)
