"""Synchronous skill view operations for mcp_skill_view (testable, no async)."""
import logging
from typing import Any, Dict

from hippocampus.models import SkillEngram, SkillFileAttachment

logger = logging.getLogger(__name__)


def run_skill_view(name: str, file_path: str) -> Dict[str, Any]:
    """Load a skill's body, metadata, and attached file list."""
    try:
        skill = SkillEngram.objects.get(name=name, is_active=True)
    except SkillEngram.DoesNotExist:
        return {'error': "Skill '%s' not found." % name}

    result: Dict[str, Any] = {
        'name': skill.name,
        'description': skill.description,
        'category': skill.category,
        'body': skill.body,
        'attached_files': [
            {
                'file_type': f.file_type,
                'file_path': f.file_path,
            }
            for f in skill.attached_files.all()
        ],
    }

    if file_path:
        try:
            attachment = skill.attached_files.get(file_path=file_path)
            result['file_content'] = attachment.file_content
        except SkillFileAttachment.DoesNotExist:
            result['file_error'] = (
                "File '%s' not found." % file_path
            )

    logger.info('[SkillView] Viewed skill %s.', name)
    return result
