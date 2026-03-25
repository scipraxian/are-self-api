import re
from dataclasses import dataclass

from hypothalamus.models import (
    AIModelCreator,
    AIModelFamily,
    AIModelQuantization,
    AIModelRole,
    AIModelTags,
    AIModelVersion,
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


def parse_model_string(raw_string: str) -> AIModelSemanticParseResult:
    """
    Enhancer function for the sync pipeline.
    Parses a raw LLM string, queries the DB for taxonomy, creates missing
    taxonomy records (Families, Roles, Versions, Tags), and returns a dictionary.

    DOES NOT CREATE AIModel records.
    """
    # 1. Bypass provider paths completely and strip pure API noise
    clean_name = raw_string.split('/')[-1].lower()
    clean_name = re.sub(
        r':(free|latest|preview|extended|exacto)$',
        '',
        clean_name,
        flags=re.IGNORECASE,
    ).strip()

    # 2. Math Extraction (Size)
    # Extracts 70b, 8x22b, 500m, etc.
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

    # 3. Tokenize for DB Queries
    # Notice we don't split on underscores so quantizations like 'q4_k_m' stay intact
    tokens = [t.strip() for t in re.split(r'[-:.@]', clean_name) if t.strip()]
    noise = {'hf', 'pt', 'v1', 'v2', 'v3'}
    tokens = [t for t in tokens if t not in noise]

    if not tokens:
        return AIModelSemanticParseResult(
            success=False,
            parameter_size=parameter_size,
            family=None,
            version=None,
            roles=[],
            quantizations=[],
            tags=[],
        )

    # 4. Database Queries (Fast Mapping)
    search_slugs = set(tokens)
    for t in tokens:
        alpha_only = re.sub(r'\d+$', '', t)
        if alpha_only:
            search_slugs.add(alpha_only)

    families = list(AIModelFamily.objects.filter(slug__in=search_slugs))
    found_family = None
    if families:
        found_family = min(families, key=lambda f: clean_name.find(f.slug))
    else:
        family_slug = re.sub(r'\d+$', '', tokens[0])
        if family_slug:
            found_family, _ = AIModelFamily.objects.get_or_create(
                name=family_slug.title(), defaults={'slug': family_slug}
            )

    capitalized_tokens = [t.title() for t in tokens]
    found_roles = list(AIModelRole.objects.filter(name__in=capitalized_tokens))
    found_quants = list(AIModelQuantization.objects.filter(name__in=tokens))
    found_creator = AIModelCreator.objects.filter(
        name__in=capitalized_tokens
    ).first()

    # 5. Deduce Version
    version_obj = None
    if found_family:
        # We strip the size before searching for version so '7b' doesn't become a version
        clean_name_for_v = (
            clean_name.replace(size_match.group(0), ' ', 1)
            if size_match
            else clean_name
        )

        # Matches: r1, 3.5, 4o, v3p1. Explicitly ignores 4-digit date tags like -0528.
        v_regex = re.compile(
            rf'{found_family.slug}[-_.]?([vVrR]?\d+(?:[-.pP]\d{{1,2}})?(?:[a-zA-Z](?![a-zA-Z]))?)\b',
            re.IGNORECASE,
        )
        v_match = v_regex.search(clean_name_for_v)
        if v_match:
            # Normalize hyphens and 'p' into standard decimal dots (e.g. '3-1' or '3p1' -> '3.1')
            version_str = (
                v_match.group(1).lower().replace('-', '.').replace('p', '.')
            )
            version_obj, _ = AIModelVersion.objects.get_or_create(
                name=version_str
            )

            # Clean the token array so the version doesn't also become a tag
            if version_str in tokens:
                tokens.remove(version_str)

            # Catch raw tokenized variations that haven't been normalized (e.g. 'r1', '35')
            raw_v_token = v_match.group(1).lower()
            if raw_v_token in tokens:
                tokens.remove(raw_v_token)
            clean_v_token = raw_v_token.replace('.', '')
            if clean_v_token in tokens:
                tokens.remove(clean_v_token)

    # 6. Leftover Cleanup via Word Boundary Replacement
    # This prevents ghost tags by strictly wiping the known data out of the string
    tag_str = clean_name
    if size_match:
        tag_str = tag_str.replace(size_match.group(0), ' ', 1)

    if found_family:
        if version_obj:
            v_safe = re.escape(version_obj.name)
            tag_str = re.sub(
                rf'\b{found_family.slug}[-_.]?{v_safe}\b',
                ' ',
                tag_str,
                flags=re.IGNORECASE,
            )
        # Wipe standalone family mentions or trailing numbers (e.g. 'llama' or 'llama3')
        tag_str = re.sub(
            rf'\b{found_family.slug}\d*\b', ' ', tag_str, flags=re.IGNORECASE
        )

    for r in found_roles:
        tag_str = re.sub(rf'\b{r.name}\b', ' ', tag_str, flags=re.IGNORECASE)
    for q in found_quants:
        tag_str = re.sub(
            rf'\b{re.escape(q.name)}\b', ' ', tag_str, flags=re.IGNORECASE
        )

    # 7. Create Tags from the pristine leftovers
    final_tokens = [
        t.strip() for t in re.split(r'[-:.@]', tag_str) if t.strip()
    ]
    final_tokens = [t for t in final_tokens if t not in noise]

    tags = []
    for leftover in final_tokens:
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
