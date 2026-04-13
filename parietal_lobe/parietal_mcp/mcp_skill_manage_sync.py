"""Synchronous skill operations for mcp_skill_manage (testable, no async)."""
import logging
from typing import Any, Dict, Optional, Tuple

import yaml

from frontal_lobe.synapse import OllamaClient
from hippocampus.models import SkillEngram, SkillFileAttachment

logger = logging.getLogger(__name__)

MAX_SKILL_NAME_LEN = 64
EMBED_BODY_LIMIT = 2000
EMBED_MODEL = 'nomic-embed-text'
YAML_DELIMITER = '---'

FILE_TYPE_MAP = {
    'scripts': 'script',
    'templates': 'template',
    'references': 'reference',
    'assets': 'asset',
}
DEFAULT_FILE_TYPE = 'asset'


def _parse_yaml_frontmatter(content: str) -> Tuple[Dict, str]:
    """Split YAML frontmatter from markdown body.

    Returns:
        Tuple of (yaml_data dict, body string).
    """
    if not content.startswith(YAML_DELIMITER + '\n'):
        return {}, content

    parts = content.split(YAML_DELIMITER, 2)
    if len(parts) < 3:
        return {}, content

    try:
        yaml_data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        logger.warning('[SkillManage] Failed to parse YAML frontmatter.')
        return {}, content

    body = parts[2].strip()
    return yaml_data, body


def _embed_skill(skill: SkillEngram) -> None:
    """Generate and save 768-dim vector embedding for a skill."""
    index_text = '%s\n%s\n%s' % (
        skill.name,
        skill.description,
        skill.body[:EMBED_BODY_LIMIT],
    )
    try:
        client = OllamaClient(EMBED_MODEL)
        vector = client.embed(index_text)
        if vector:
            skill.vector = vector
            skill.save(update_fields=['vector'])
            logger.info(
                '[SkillManage] Embedded skill %s (%d dims).',
                skill.name,
                len(vector),
            )
    except Exception as exc:
        logger.warning(
            '[SkillManage] Embedding failed for skill %s: %s',
            skill.name,
            exc,
        )


def _get_active_skill(name: str) -> Optional[SkillEngram]:
    """Return active skill by name or None."""
    try:
        return SkillEngram.objects.get(name=name, is_active=True)
    except SkillEngram.DoesNotExist:
        return None


def _infer_file_type(file_path: str) -> str:
    """Infer file_type from path prefix (e.g. scripts/ -> script)."""
    for prefix, ftype in FILE_TYPE_MAP.items():
        if file_path.startswith(prefix + '/'):
            return ftype
    return DEFAULT_FILE_TYPE


def _create_skill(
    name: str, content: str, category: str
) -> Dict[str, Any]:
    """Create a new SkillEngram from content with optional YAML frontmatter."""
    if not name or not name.strip():
        return {'error': 'Name is required.'}
    name = name.strip()
    if len(name) > MAX_SKILL_NAME_LEN:
        return {
            'error': 'Name must be %d characters or fewer.' % MAX_SKILL_NAME_LEN
        }

    if SkillEngram.objects.filter(name=name, is_active=True).exists():
        return {'error': "Skill '%s' already exists." % name}

    yaml_data, body = _parse_yaml_frontmatter(content)

    description = (
        yaml_data.get('description', '')[:200]
        or body[:200].split('\n')[0]
    )
    resolved_category = category or yaml_data.get('category', '')

    skill = SkillEngram.objects.create(
        name=name,
        description=description,
        category=resolved_category,
        body=body,
        yaml_frontmatter=yaml_data,
    )

    _embed_skill(skill)

    logger.info('[SkillManage] Created skill %s.', name)
    return {
        'status': 'created',
        'name': name,
        'description': skill.description,
    }


def _patch_skill(
    name: str,
    old_text: str,
    new_text: str,
    replace_all: bool,
    file_path: str,
) -> Dict[str, Any]:
    """Replace old_text with new_text in skill body or file attachment."""
    skill = _get_active_skill(name)
    if not skill:
        return {'error': "Skill '%s' not found." % name}

    if not old_text:
        return {'error': 'old_text is required for patch.'}

    if file_path:
        try:
            attachment = skill.attached_files.get(file_path=file_path)
        except SkillFileAttachment.DoesNotExist:
            return {'error': "File '%s' not found on skill '%s'." % (file_path, name)}

        if old_text not in attachment.file_content:
            return {'error': 'old_text not found in file content.'}

        if replace_all:
            attachment.file_content = attachment.file_content.replace(
                old_text, new_text
            )
        else:
            attachment.file_content = attachment.file_content.replace(
                old_text, new_text, 1
            )
        attachment.save(update_fields=['file_content'])
        logger.info(
            '[SkillManage] Patched file %s on skill %s.', file_path, name
        )
    else:
        if old_text not in skill.body:
            return {'error': 'old_text not found in skill body.'}

        if replace_all:
            skill.body = skill.body.replace(old_text, new_text)
        else:
            skill.body = skill.body.replace(old_text, new_text, 1)
        skill.save(update_fields=['body'])
        _embed_skill(skill)
        logger.info('[SkillManage] Patched skill %s body.', name)

    return {'status': 'patched', 'name': name}


def _edit_skill(name: str, content: str) -> Dict[str, Any]:
    """Full body rewrite of a skill."""
    skill = _get_active_skill(name)
    if not skill:
        return {'error': "Skill '%s' not found." % name}

    yaml_data, body = _parse_yaml_frontmatter(content)

    skill.body = body
    update_fields = ['body']

    if yaml_data:
        skill.yaml_frontmatter = yaml_data
        update_fields.append('yaml_frontmatter')
        if 'description' in yaml_data:
            skill.description = yaml_data['description'][:200]
            update_fields.append('description')
        if 'category' in yaml_data:
            skill.category = yaml_data['category']
            update_fields.append('category')

    skill.save(update_fields=update_fields)
    _embed_skill(skill)

    logger.info('[SkillManage] Edited skill %s (full rewrite).', name)
    return {'status': 'edited', 'name': name}


def _delete_skill(name: str) -> Dict[str, Any]:
    """Soft-delete a skill by setting is_active=False."""
    skill = _get_active_skill(name)
    if not skill:
        return {'error': "Skill '%s' not found." % name}

    skill.is_active = False
    skill.save(update_fields=['is_active'])
    logger.info('[SkillManage] Soft-deleted skill %s.', name)
    return {'status': 'deleted', 'name': name}


def _write_file(
    name: str, file_path: str, file_content: str
) -> Dict[str, Any]:
    """Create or update an attached file on a skill."""
    skill = _get_active_skill(name)
    if not skill:
        return {'error': "Skill '%s' not found." % name}

    if not file_path or not file_path.strip():
        return {'error': 'file_path is required for write_file.'}

    file_type = _infer_file_type(file_path)

    attachment, created = SkillFileAttachment.objects.update_or_create(
        skill=skill,
        file_path=file_path,
        defaults={
            'file_type': file_type,
            'file_content': file_content,
        },
    )

    action_word = 'created' if created else 'updated'
    logger.info(
        '[SkillManage] File %s %s on skill %s.',
        file_path,
        action_word,
        name,
    )
    return {'status': 'file_written', 'name': name, 'file_path': file_path}


def _remove_file(name: str, file_path: str) -> Dict[str, Any]:
    """Delete an attached file from a skill."""
    skill = _get_active_skill(name)
    if not skill:
        return {'error': "Skill '%s' not found." % name}

    if not file_path or not file_path.strip():
        return {'error': 'file_path is required for remove_file.'}

    try:
        attachment = skill.attached_files.get(file_path=file_path)
    except SkillFileAttachment.DoesNotExist:
        return {'error': "File '%s' not found on skill '%s'." % (file_path, name)}

    attachment.delete()
    logger.info(
        '[SkillManage] Removed file %s from skill %s.', file_path, name
    )
    return {'status': 'file_removed', 'name': name, 'file_path': file_path}


def run_skill_manage(
    action: str,
    name: str,
    content: str,
    old_text: str,
    new_text: str,
    replace_all: bool,
    file_path: str,
    file_content: str,
    category: str,
) -> Dict[str, Any]:
    """Dispatch skill management action."""
    act = action.strip().lower()

    dispatch = {
        'create': lambda: _create_skill(name, content, category),
        'patch': lambda: _patch_skill(
            name, old_text, new_text, replace_all, file_path
        ),
        'edit': lambda: _edit_skill(name, content),
        'delete': lambda: _delete_skill(name),
        'write_file': lambda: _write_file(name, file_path, file_content),
        'remove_file': lambda: _remove_file(name, file_path),
    }

    handler = dispatch.get(act)
    if not handler:
        return {
            'error': "Unknown action '%s'. Valid: %s."
            % (act, ', '.join(sorted(dispatch.keys())))
        }

    return handler()
