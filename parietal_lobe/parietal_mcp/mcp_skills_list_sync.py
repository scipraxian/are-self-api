"""Synchronous skill listing for mcp_skills_list (testable, no async)."""
import logging
from typing import Any, Dict

from hippocampus.models import SkillEngram

logger = logging.getLogger(__name__)


def run_skills_list(category: str) -> Dict[str, Any]:
    """List active skills, optionally filtered by category."""
    qs = SkillEngram.objects.filter(is_active=True)
    if category:
        qs = qs.filter(category=category)

    skills = [
        {
            'name': s.name,
            'description': s.description,
            'category': s.category,
        }
        for s in qs.order_by('category', 'name')
    ]

    logger.info('[SkillsList] Listed %d skills.', len(skills))
    return {'skills': skills, 'count': len(skills)}
