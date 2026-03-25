import re
from dataclasses import dataclass

from django.db.models.functions import Length

from hypothalamus.models import (
    AIModelCreator,
    AIModelFamily,
    AIModelQuantization,
    AIModelRole,
    AIModelTags,
    AIModelVersion,
    LLMProvider,
)


@dataclass
class AIModelSemanticParseResult:
    success: bool
    parameter_size: float | None
    family: AIModelFamily | None
    version: AIModelVersion | None
    creator: AIModelCreator | None
    roles: list[AIModelRole]
    quantizations: list[AIModelQuantization]
    tags: list[AIModelTags]


# TODO: there are some families that are not right, we need to touch those now.
# In general we need to clean the fixtures with scrutenizing eyes, but it's pretty pretty good start.


def parse_model_string(raw_string: str) -> AIModelSemanticParseResult:
    """The 100% Database-Driven 'Search & Destroy' Parser."""
    clean_name = raw_string.split('/')[-1].lower()

    # 1. Strip literal API endpoint noise first
    clean_name = re.sub(
        r':(free|latest|preview|extended|exacto)$',
        '',
        clean_name,
        flags=re.IGNORECASE,
    ).strip()

    # 2. Extract Math (Size)
    size_regex = re.compile(r'(?:(\d+)x)?(\d+(?:\.\d+)?)(b|m)\b')
    size_match = size_regex.search(clean_name)
    parameter_size = None

    if size_match:
        multiplier = float(size_match.group(1)) if size_match.group(1) else 1.0
        base_val = float(size_match.group(2))
        unit = size_match.group(3)
        parameter_size = (
            (multiplier * base_val)
            if unit == 'b'
            else (multiplier * base_val) / 1000.0
        )
        clean_name = clean_name.replace(size_match.group(0), ' ')

    # --- 3. THE "BOOM" DB SEARCH & DESTROY ---
    # We use pure string replacement. No \b regex traps.

    # A. Family First (Grabs 'claude' before anything else can mess it up)
    found_family = None
    for family in AIModelFamily.objects.annotate(
        slug_len=Length('slug')
    ).order_by('-slug_len'):
        if family.slug.lower() in clean_name:
            found_family = family
            clean_name = clean_name.replace(family.slug.lower(), ' ')
            break

    # B. Creator Second (Grabs 'anthropic')
    found_creator = None
    for creator in AIModelCreator.objects.annotate(
        name_len=Length('name')
    ).order_by('-name_len'):
        if creator.name.lower() in clean_name:
            found_creator = creator
            clean_name = clean_name.replace(creator.name.lower(), ' ')
            break

    # C. Roles & Quants
    found_roles = []
    for role in AIModelRole.objects.annotate(name_len=Length('name')).order_by(
        '-name_len'
    ):
        if role.name.lower() in clean_name:
            found_roles.append(role)
            clean_name = clean_name.replace(role.name.lower(), ' ')

    found_quants = []
    for quant in AIModelQuantization.objects.annotate(
        name_len=Length('name')
    ).order_by('-name_len'):
        if quant.name.lower() in clean_name:
            found_quants.append(quant)
            clean_name = clean_name.replace(quant.name.lower(), ' ')

    # D. Vaporize Providers (Cleanup only, so 'openrouter' or 'eu' doesn't become a tag)
    for provider in LLMProvider.objects.annotate(
        key_len=Length('key')
    ).order_by('-key_len'):
        if provider.key.lower() in clean_name:
            clean_name = clean_name.replace(provider.key.lower(), ' ')

    # --- 4. EXTRACT ISOLATED VERSIONS ---
    # Because we deleted everything above, a string like 'anthropic-claude-3.5-haiku' is now just ' - -3.5-haiku'
    version_obj = None

    # Grabs clean versions (3.5, 3-7, v1.0)
    v_regex = re.compile(
        r'\b([vVrR]?\d+(?:[-.pP]\d+)*(?:-[a-zA-Z0-9]+)?(?:[:]\d+)?)\b'
    )
    v_match = v_regex.search(clean_name)

    if v_match:
        raw_v = v_match.group(1)
        version_str = raw_v.lower().replace('-', '.').replace('p', '.')
        version_obj, _ = AIModelVersion.objects.get_or_create(name=version_str)
        clean_name = clean_name.replace(raw_v, ' ')

    # --- 5. THE SURVIVORS BECOME TAGS ---
    tokens = [t.strip() for t in re.split(r'[-:.@\s]', clean_name) if t.strip()]
    noise = {'hf', 'pt'}
    tokens = [t for t in tokens if t not in noise]

    tags = []
    for leftover in tokens:
        tag_obj, _ = AIModelTags.objects.get_or_create(name=leftover)
        tags.append(tag_obj)

    return AIModelSemanticParseResult(
        success=True,
        parameter_size=parameter_size,
        family=found_family,
        version=version_obj,
        creator=found_creator,
        roles=found_roles,
        quantizations=found_quants,
        tags=tags,
    )
