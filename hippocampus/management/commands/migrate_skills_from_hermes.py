"""Management command: import skills from a Hermes-style skills directory.

Each skill lives in its own directory containing a SKILL.md and optional
auxiliary files. Example layout:

    skills_root/
        git_workflow/
            SKILL.md          # YAML frontmatter + markdown body
            scripts/run.sh    # attached file (auto-detected type)
            templates/pr.md   # attached file
        code_review/
            SKILL.md
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from django.core.management.base import BaseCommand

from hippocampus.models import SkillEngram, SkillFileAttachment
from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
    _parse_yaml_frontmatter,
)

logger = logging.getLogger(__name__)

SKILL_MD = 'SKILL.md'

FILE_TYPE_MAP = {
    'scripts': 'script',
    'templates': 'template',
    'references': 'reference',
    'assets': 'asset',
}
DEFAULT_FILE_TYPE = 'asset'


def _infer_file_type(relative_path: str) -> str:
    """Infer file_type from the first path segment."""
    for prefix, ftype in FILE_TYPE_MAP.items():
        if relative_path.startswith(prefix + '/'):
            return ftype
    return DEFAULT_FILE_TYPE


def _migrate_single_skill(
    skill_dir: Path, stats: Dict[str, int], disc: 'Optional[IdentityDisc]' = None
) -> None:
    """Import one skill directory into the database."""
    skill_md_path = skill_dir / SKILL_MD
    if not skill_md_path.is_file():
        logger.warning(
            '[migrate_skills] Skipping %s: no %s found.', skill_dir.name, SKILL_MD
        )
        stats['skipped'] += 1
        return

    content = skill_md_path.read_text(encoding='utf-8')
    yaml_data, body = _parse_yaml_frontmatter(content)

    name = yaml_data.get('name', skill_dir.name)
    description = (
        yaml_data.get('description', '')[:200]
        or body[:200].split('\n')[0]
    )
    category = yaml_data.get('category', '')

    if SkillEngram.objects.filter(name=name).exists():
        logger.info(
            '[migrate_skills] Skill %s already exists, skipping.', name
        )
        stats['skipped'] += 1
        return

    skill = SkillEngram.objects.create(
        name=name,
        description=description,
        category=category,
        body=body,
        yaml_frontmatter=yaml_data,
        identity_disc=disc,
    )
    stats['created'] += 1
    logger.info('[migrate_skills] Created skill %s.', name)

    for child in skill_dir.iterdir():
        if child.name == SKILL_MD or child.is_dir():
            continue
        if not child.is_file():
            continue

        relative = child.name
        file_type = _infer_file_type(relative)

        try:
            file_content = child.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning(
                '[migrate_skills] Cannot read %s: %s', child, exc
            )
            continue

        SkillFileAttachment.objects.create(
            skill=skill,
            file_type=file_type,
            file_path=relative,
            file_content=file_content,
        )
        stats['files'] += 1
        logger.info(
            '[migrate_skills] Attached %s to skill %s.',
            relative,
            name,
        )

    for subdir in skill_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith('.'):
            continue
        for child in subdir.iterdir():
            if not child.is_file():
                continue

            relative = f'{subdir.name}/{child.name}'
            file_type = _infer_file_type(relative)

            try:
                file_content = child.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning(
                    '[migrate_skills] Cannot read %s: %s', child, exc
                )
                continue

            SkillFileAttachment.objects.create(
                skill=skill,
                file_type=file_type,
                file_path=relative,
                file_content=file_content,
            )
            stats['files'] += 1


class Command(BaseCommand):
    help = 'Import skills from a Hermes-style skills directory into SkillEngram.'

    def add_arguments(self, parser):
        parser.add_argument(
            'skills_root',
            type=str,
            help='Path to the skills directory (e.g. ~/.hermes/skills/).',
        )
        parser.add_argument(
            '--identity-disc',
            type=str,
            default='',
            help='IdentityDisc name to link imported skills to.',
        )

    def handle(self, *args, **options):
        skills_root = Path(options['skills_root']).expanduser().resolve()
        if not skills_root.is_dir():
            self.stderr.write(
                self.style.ERROR(
                    'Skills root does not exist: %s' % skills_root
                )
            )
            return

        disc = None
        disc_name = options.get('identity_disc', '')
        if disc_name:
            from identity.models import IdentityDisc

            try:
                disc = IdentityDisc.objects.get(name=disc_name)
            except IdentityDisc.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        'IdentityDisc not found: %s' % disc_name
                    )
                )
                return

        stats: Dict[str, int] = {'created': 0, 'skipped': 0, 'files': 0}

        for child in sorted(skills_root.iterdir()):
            if not child.is_dir() or child.name.startswith('.'):
                continue
            _migrate_single_skill(child, stats, disc=disc)

        self.stdout.write(
            self.style.SUCCESS(
                'Migration complete: %d created, %d skipped, %d files attached.'
                % (stats['created'], stats['skipped'], stats['files'])
            )
        )
