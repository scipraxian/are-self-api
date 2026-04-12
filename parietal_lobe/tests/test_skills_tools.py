"""Tests for skill MCP tool sync backends."""
from unittest.mock import patch

from common.tests.common_test_case import CommonFixturesAPITestCase
from hippocampus.models import SkillEngram, SkillFileAttachment


SKILL_BODY = '# Git Workflow\n\nAlways rebase before push.'
YAML_CONTENT = (
    '---\n'
    'name: git_workflow\n'
    'description: Git branching standards\n'
    'category: dev\n'
    '---\n'
    '# Git Workflow\n\n'
    'Always rebase before push.'
)


class TestSkillManageCreate(CommonFixturesAPITestCase):
    """Assert mcp_skill_manage create action works correctly."""

    def test_create_basic(self):
        """Assert create returns status=created and persists SkillEngram."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='create',
            name='basic_skill',
            content='# Basic\n\nA simple skill.',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='general',
        )
        self.assertEqual(result['status'], 'created')
        self.assertEqual(result['name'], 'basic_skill')
        self.assertTrue(
            SkillEngram.objects.filter(name='basic_skill').exists()
        )

    def test_create_with_yaml_frontmatter(self):
        """Assert create parses YAML frontmatter from content."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='create',
            name='yaml_skill',
            content=YAML_CONTENT,
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertEqual(result['status'], 'created')
        skill = SkillEngram.objects.get(name='yaml_skill')
        self.assertEqual(skill.yaml_frontmatter.get('category'), 'dev')
        self.assertIn('Always rebase', skill.body)
        self.assertNotIn('---', skill.body)

    def test_create_duplicate_returns_error(self):
        """Assert error dict when skill name already exists."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        SkillEngram.objects.create(
            name='dupe_skill', description='Exists.', body='Body.'
        )
        result = run_skill_manage(
            action='create',
            name='dupe_skill',
            content='New body.',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertIn('error', result)

    def test_create_name_too_long_returns_error(self):
        """Assert error when name exceeds 64 characters."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='create',
            name='x' * 65,
            content='Body.',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertIn('error', result)


class TestSkillManagePatchEditDelete(CommonFixturesAPITestCase):
    """Assert mcp_skill_manage patch, edit, and delete actions."""

    def setUp(self):
        super().setUp()
        self.skill = SkillEngram.objects.create(
            name='editable_skill',
            description='A skill to edit.',
            body='Line one.\nLine two.\nLine three.',
        )
        self.attachment = SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='script',
            file_path='scripts/run.sh',
            file_content='#!/bin/bash\necho hello',
        )

    def test_patch_body_text(self):
        """Assert old_text is replaced with new_text in body."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='patch',
            name='editable_skill',
            content='',
            old_text='Line two.',
            new_text='Line TWO updated.',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertEqual(result['status'], 'patched')
        self.skill.refresh_from_db()
        self.assertIn('Line TWO updated.', self.skill.body)
        self.assertNotIn('Line two.', self.skill.body)

    def test_patch_file_attachment(self):
        """Assert patching with file_path targets the attachment content."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='patch',
            name='editable_skill',
            content='',
            old_text='echo hello',
            new_text='echo world',
            replace_all=False,
            file_path='scripts/run.sh',
            file_content='',
            category='',
        )
        self.assertEqual(result['status'], 'patched')
        self.attachment.refresh_from_db()
        self.assertIn('echo world', self.attachment.file_content)

    def test_edit_full_rewrite(self):
        """Assert edit replaces body entirely."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='edit',
            name='editable_skill',
            content='# Completely New Body\n\nRewritten.',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertEqual(result['status'], 'edited')
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.body, '# Completely New Body\n\nRewritten.')

    def test_delete_soft_deletes(self):
        """Assert delete sets is_active=False."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='delete',
            name='editable_skill',
            content='',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertEqual(result['status'], 'deleted')
        self.skill.refresh_from_db()
        self.assertFalse(self.skill.is_active)


class TestSkillManageFiles(CommonFixturesAPITestCase):
    """Assert mcp_skill_manage write_file and remove_file actions."""

    def setUp(self):
        super().setUp()
        self.skill = SkillEngram.objects.create(
            name='file_skill',
            description='Skill for file tests.',
            body='# Body',
        )

    def test_write_file_creates_attachment(self):
        """Assert write_file creates a new SkillFileAttachment."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='write_file',
            name='file_skill',
            content='',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='templates/base.html',
            file_content='<html></html>',
            category='',
        )
        self.assertEqual(result['status'], 'file_written')
        self.assertTrue(
            SkillFileAttachment.objects.filter(
                skill=self.skill, file_path='templates/base.html'
            ).exists()
        )

    def test_write_file_updates_existing(self):
        """Assert write_file updates existing attachment content."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='template',
            file_path='templates/base.html',
            file_content='<html>old</html>',
        )
        result = run_skill_manage(
            action='write_file',
            name='file_skill',
            content='',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='templates/base.html',
            file_content='<html>new</html>',
            category='',
        )
        self.assertEqual(result['status'], 'file_written')
        attachment = SkillFileAttachment.objects.get(
            skill=self.skill, file_path='templates/base.html'
        )
        self.assertEqual(attachment.file_content, '<html>new</html>')

    def test_remove_file_deletes_attachment(self):
        """Assert remove_file deletes the attachment."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='script',
            file_path='scripts/cleanup.sh',
            file_content='rm -rf /tmp/cache',
        )
        result = run_skill_manage(
            action='remove_file',
            name='file_skill',
            content='',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='scripts/cleanup.sh',
            file_content='',
            category='',
        )
        self.assertEqual(result['status'], 'file_removed')
        self.assertFalse(
            SkillFileAttachment.objects.filter(
                skill=self.skill, file_path='scripts/cleanup.sh'
            ).exists()
        )

    def test_invalid_action_returns_error(self):
        """Assert unknown action returns error dict."""
        from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import (
            run_skill_manage,
        )

        result = run_skill_manage(
            action='explode',
            name='file_skill',
            content='',
            old_text='',
            new_text='',
            replace_all=False,
            file_path='',
            file_content='',
            category='',
        )
        self.assertIn('error', result)


class TestSkillView(CommonFixturesAPITestCase):
    """Assert mcp_skill_view sync backend returns correct data."""

    def setUp(self):
        super().setUp()
        self.skill = SkillEngram.objects.create(
            name='viewable_skill',
            description='A viewable skill.',
            category='demo',
            body='# View Me\n\nBody content here.',
        )
        SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='script',
            file_path='scripts/run.py',
            file_content='print("running")',
        )

    def test_view_returns_body_and_files(self):
        """Assert view returns name, description, body, and attached_files."""
        from parietal_lobe.parietal_mcp.mcp_skill_view_sync import (
            run_skill_view,
        )

        result = run_skill_view(name='viewable_skill', file_path='')
        self.assertEqual(result['name'], 'viewable_skill')
        self.assertEqual(result['description'], 'A viewable skill.')
        self.assertIn('Body content here.', result['body'])
        self.assertEqual(len(result['attached_files']), 1)
        self.assertEqual(
            result['attached_files'][0]['file_path'], 'scripts/run.py'
        )

    def test_view_with_file_path(self):
        """Assert view with file_path includes file_content."""
        from parietal_lobe.parietal_mcp.mcp_skill_view_sync import (
            run_skill_view,
        )

        result = run_skill_view(
            name='viewable_skill', file_path='scripts/run.py'
        )
        self.assertEqual(result['file_content'], 'print("running")')

    def test_view_missing_returns_error(self):
        """Assert view of nonexistent skill returns error dict."""
        from parietal_lobe.parietal_mcp.mcp_skill_view_sync import (
            run_skill_view,
        )

        result = run_skill_view(name='nonexistent_skill', file_path='')
        self.assertIn('error', result)


class TestSkillsList(CommonFixturesAPITestCase):
    """Assert mcp_skills_list sync backend returns correct data."""

    def setUp(self):
        super().setUp()
        SkillEngram.objects.create(
            name='alpha_skill',
            description='Alpha.',
            category='cat_a',
            body='Body A.',
        )
        SkillEngram.objects.create(
            name='beta_skill',
            description='Beta.',
            category='cat_b',
            body='Body B.',
        )
        SkillEngram.objects.create(
            name='inactive_skill',
            description='Gone.',
            category='cat_a',
            body='Body.',
            is_active=False,
        )

    def test_list_all_active(self):
        """Assert list returns all active skills."""
        from parietal_lobe.parietal_mcp.mcp_skills_list_sync import (
            run_skills_list,
        )

        result = run_skills_list(category='')
        self.assertEqual(result['count'], 2)
        names = [s['name'] for s in result['skills']]
        self.assertIn('alpha_skill', names)
        self.assertIn('beta_skill', names)

    def test_list_filters_category(self):
        """Assert list filters by category."""
        from parietal_lobe.parietal_mcp.mcp_skills_list_sync import (
            run_skills_list,
        )

        result = run_skills_list(category='cat_a')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['skills'][0]['name'], 'alpha_skill')

    def test_list_excludes_inactive(self):
        """Assert inactive skills are excluded from list."""
        from parietal_lobe.parietal_mcp.mcp_skills_list_sync import (
            run_skills_list,
        )

        result = run_skills_list(category='')
        names = [s['name'] for s in result['skills']]
        self.assertNotIn('inactive_skill', names)
