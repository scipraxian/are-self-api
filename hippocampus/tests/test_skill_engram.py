"""Tests for SkillEngram and SkillFileAttachment models."""
from django.db import IntegrityError

from common.tests.common_test_case import CommonFixturesAPITestCase
from hippocampus.models import SkillEngram, SkillFileAttachment
from identity.models import IdentityDisc


class TestSkillEngramModel(CommonFixturesAPITestCase):
    """Assert SkillEngram model stores and constrains fields correctly."""

    def setUp(self):
        super().setUp()
        self.disc = IdentityDisc.objects.first()
        self.skill = SkillEngram.objects.create(
            name='test_skill',
            description='A test skill for unit tests.',
            category='testing',
            body='# Test Skill\n\nThis is the body.',
            yaml_frontmatter={'author': 'test', 'version': '1.0'},
            identity_disc=self.disc,
        )

    def test_create_stores_all_fields(self):
        """Assert SkillEngram.objects.create populates all fields correctly."""
        self.assertEqual(self.skill.name, 'test_skill')
        self.assertEqual(self.skill.description, 'A test skill for unit tests.')
        self.assertEqual(self.skill.category, 'testing')
        self.assertEqual(self.skill.body, '# Test Skill\n\nThis is the body.')
        self.assertEqual(
            self.skill.yaml_frontmatter,
            {'author': 'test', 'version': '1.0'},
        )
        self.assertTrue(self.skill.is_active)
        self.assertIsNone(self.skill.vector)
        self.assertIsNotNone(self.skill.pk)
        self.assertIsNotNone(self.skill.created)
        self.assertIsNotNone(self.skill.modified)

    def test_name_unique_constraint(self):
        """Assert IntegrityError on duplicate skill name."""
        with self.assertRaises(IntegrityError):
            SkillEngram.objects.create(
                name='test_skill',
                description='Duplicate name.',
                body='Body.',
            )

    def test_identity_disc_fk_set_null(self):
        """Assert FK to IdentityDisc uses SET_NULL on delete."""
        skill_pk = self.skill.pk
        self.disc.delete()
        self.skill.refresh_from_db()
        self.assertIsNone(self.skill.identity_disc)
        self.assertEqual(self.skill.pk, skill_pk)

    def test_ordering_by_name(self):
        """Assert default ordering is by name ascending."""
        SkillEngram.objects.create(
            name='alpha_skill', description='First', body='Body A'
        )
        SkillEngram.objects.create(
            name='zulu_skill', description='Last', body='Body Z'
        )
        names = list(
            SkillEngram.objects.values_list('name', flat=True)
        )
        self.assertEqual(names, sorted(names))

    def test_str_returns_name(self):
        """Assert __str__ returns the skill name."""
        self.assertEqual(str(self.skill), 'test_skill')

    def test_repr_includes_name(self):
        """Assert __repr__ includes the skill name."""
        self.assertIn('test_skill', repr(self.skill))

    def test_category_defaults_to_empty(self):
        """Assert category defaults to empty string when not provided."""
        skill = SkillEngram.objects.create(
            name='no_category_skill',
            description='No category.',
            body='Body.',
        )
        self.assertEqual(skill.category, '')

    def test_yaml_frontmatter_defaults_to_empty_dict(self):
        """Assert yaml_frontmatter defaults to empty dict."""
        skill = SkillEngram.objects.create(
            name='no_yaml_skill',
            description='No YAML.',
            body='Body.',
        )
        self.assertEqual(skill.yaml_frontmatter, {})


class TestSkillFileAttachmentModel(CommonFixturesAPITestCase):
    """Assert SkillFileAttachment model stores and constrains fields correctly."""

    def setUp(self):
        super().setUp()
        self.skill = SkillEngram.objects.create(
            name='attach_test_skill',
            description='Skill for attachment tests.',
            body='# Body',
        )
        self.attachment = SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='script',
            file_path='scripts/setup.py',
            file_content='print("hello")',
        )

    def test_file_attachment_create(self):
        """Assert SkillFileAttachment stores all fields."""
        self.assertEqual(self.attachment.skill, self.skill)
        self.assertEqual(self.attachment.file_type, 'script')
        self.assertEqual(self.attachment.file_path, 'scripts/setup.py')
        self.assertEqual(self.attachment.file_content, 'print("hello")')
        self.assertIsNotNone(self.attachment.pk)
        self.assertIsNotNone(self.attachment.created)

    def test_file_attachment_unique_together(self):
        """Assert (skill, file_path) unique constraint."""
        with self.assertRaises(IntegrityError):
            SkillFileAttachment.objects.create(
                skill=self.skill,
                file_type='template',
                file_path='scripts/setup.py',
                file_content='duplicate path',
            )

    def test_file_attachment_cascade_delete(self):
        """Assert deleting SkillEngram cascades to attachments."""
        attachment_pk = self.attachment.pk
        self.skill.delete()
        self.assertFalse(
            SkillFileAttachment.objects.filter(pk=attachment_pk).exists()
        )

    def test_file_attachment_ordering(self):
        """Assert ordering is by file_type then file_path."""
        SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='template',
            file_path='templates/base.html',
            file_content='<html>',
        )
        SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='asset',
            file_path='assets/logo.png',
            file_content='',
        )
        attachments = list(
            self.skill.attached_files.values_list('file_type', 'file_path')
        )
        expected = sorted(attachments, key=lambda x: (x[0], x[1]))
        self.assertEqual(attachments, expected)

    def test_file_attachment_str(self):
        """Assert __str__ returns file_type: file_path."""
        self.assertEqual(str(self.attachment), 'script: scripts/setup.py')

    def test_file_content_defaults_to_empty(self):
        """Assert file_content defaults to empty string."""
        attachment = SkillFileAttachment.objects.create(
            skill=self.skill,
            file_type='reference',
            file_path='references/notes.txt',
        )
        self.assertEqual(attachment.file_content, '')
