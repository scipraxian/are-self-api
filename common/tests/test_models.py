"""Assert commonX models perform as expected."""
from datetime import datetime, timedelta
from django.db import models
from django.test import TestCase

from common import constants
from common.models import (CreatedMixin, DefaultFieldsMixin, DescriptionMixin,
                           ModifiedMixin, NameMixin, CreatedByMixin,
                           ModifiedByMixin, UUIDIdMixin, BigIdMixin,
                           CreatedAndModifiedBy,
                           DjangoAdminReverseRequirementsMixin)

# pylint: disable=invalid-name


class SimpleModelClass(models.Model):
    """Basic model class, used for testing mixins."""
    test_field = models.BooleanField()

    class Meta(object):  # pylint:disable=too-few-public-methods
        """Django meta accessor."""
        abstract = True


class CommonMixinTests(TestCase):  # pylint: disable=too-many-public-methods
    """Assert all mixins are functioning within expected parameters."""

    def test_created_mixin_adds_created(self):
        """Assert created mixin adds created field."""

        class MixedCreated(SimpleModelClass, CreatedMixin):
            """Mixed Model."""
            pass

        class_instance = MixedCreated()
        self.assertTrue(hasattr(class_instance, constants.CREATED))
        self.assertIsNone(class_instance.created)
        self.assertTrue(hasattr(class_instance, 'test_field'))
        self.assertFalse(hasattr(class_instance, 'foo'))

    def test_modified_mixin_adds_modified(self):
        """Assert modified mixin adds modified field."""

        class MixedModified(SimpleModelClass, ModifiedMixin):
            """Mixed Model."""
            pass

        class_instance = MixedModified()
        self.assertTrue(hasattr(class_instance, constants.MODIFIED))
        self.assertIsNone(class_instance.modified)
        self.assertTrue(hasattr(class_instance, 'test_field'))
        self.assertFalse(hasattr(class_instance, 'foo'))

    def test_description_mixin_adds_description(self):
        """Assert description mixin adds description field."""

        class MixedDescription(SimpleModelClass, DescriptionMixin):
            """Mixed Model."""
            pass

        class_instance = MixedDescription()
        self.assertTrue(hasattr(class_instance, constants.DESCRIPTION))
        self.assertIsNone(class_instance.description)
        self.assertTrue(hasattr(class_instance, 'test_field'))
        self.assertFalse(hasattr(class_instance, 'foo'))

    def test_name_mixin_adds_name_and_methods(self):
        """Assert name mixin adds name field and unicode and natural methods."""

        class MixedName(SimpleModelClass, NameMixin):
            """Mixed Model."""
            pass

        class_instance = MixedName()
        self.assertTrue(hasattr(class_instance, constants.NAME))
        self.assertEqual(class_instance.name, '')
        self.assertTrue(hasattr(class_instance, 'test_field'))
        self.assertFalse(hasattr(class_instance, 'foo'))

        TEST_NAME = 'test'
        class_instance.name = TEST_NAME
        self.assertEqual(str(class_instance), TEST_NAME)
        self.assertEqual(class_instance.natural_key(), TEST_NAME)

    def test_default_fields_mixin(self):
        """Assert default fields mixin adds all expected methods."""

        # pylint:disable=too-many-ancestors
        class TestMixedDefaultFields(SimpleModelClass, DefaultFieldsMixin):
            """Mixed Model."""
            pass

        class_instance = TestMixedDefaultFields()
        self.assertTrue(hasattr(class_instance, constants.NAME))
        self.assertEqual(class_instance.name, '')
        self.assertTrue(hasattr(class_instance, 'test_field'))
        self.assertFalse(hasattr(class_instance, 'foo'))

        TEST_NAME = 'test'
        class_instance.name = TEST_NAME
        self.assertEqual(str(class_instance), TEST_NAME)
        self.assertEqual(class_instance.natural_key(), TEST_NAME)
        self.assertIsNone(class_instance.created)
        self.assertIsNone(class_instance.modified)
        self.assertTrue(hasattr(class_instance, constants.NAME))

    def test_created_by_mixin_adds_created_by(self):
        """Assert created mixin adds created field."""

        class MixedCreatedBy(SimpleModelClass, CreatedByMixin):
            """Mixed Model."""
            pass

        class_instance = MixedCreatedBy()
        self.assertTrue(hasattr(class_instance, 'created_by_id'))
        self.assertTrue(hasattr(class_instance, 'test_field'))
        self.assertFalse(hasattr(class_instance, 'foo'))

    def test_modified_by_mixin_adds_modified_by(self):
        """Assert modified by mixin adds modified_by field."""

        class MixedModifiedBy(SimpleModelClass, ModifiedByMixin):
            """Mixed Model."""
            pass

        class_instance = MixedModifiedBy()
        self.assertTrue(hasattr(class_instance, 'modified_by_id'))
        self.assertTrue(hasattr(class_instance, 'test_field'))

    def test_uuid_id_mixin_adds_uuid_id(self):
        """Assert UUIDIdMixin adds UUID id field."""
        import uuid

        class MixedUUID(UUIDIdMixin):
            """Mixed Model."""
            pass

        class_instance = MixedUUID()
        self.assertTrue(hasattr(class_instance, 'id'))
        self.assertIsNotNone(class_instance.id)
        self.assertIsInstance(class_instance.id, uuid.UUID)

    def test_big_id_mixin_adds_big_id(self):
        """Assert BigIdMixin adds BigAutoField id field."""

        class MixedBigId(BigIdMixin):
            """Mixed Model."""
            pass

        class_instance = MixedBigId()
        self.assertTrue(hasattr(class_instance, 'id'))

    def test_created_and_modified_by_mixin(self):
        """Assert CreatedAndModifiedBy adds all fields."""

        # pylint:disable=too-many-ancestors
        class MixedAll(CreatedAndModifiedBy):
            """Mixed Model."""
            pass

        class_instance = MixedAll()
        self.assertTrue(hasattr(class_instance, 'created'))
        self.assertTrue(hasattr(class_instance, 'modified'))
        self.assertTrue(hasattr(class_instance, 'created_by_id'))
        self.assertTrue(hasattr(class_instance, 'modified_by_id'))

    def test_django_admin_reverse_requirements_mixin(self):
        """Assert DjangoAdminReverseRequirementsMixin adds expected properties."""

        class MixedAdmin(models.Model, DjangoAdminReverseRequirementsMixin):
            """Mixed Model."""

            class Meta(object):
                """Meta."""
                app_label = 'common'

        class_instance = MixedAdmin()
        self.assertEqual(class_instance.app_label, 'common')
        self.assertEqual(class_instance.model_name, 'mixedadmin')
        self.assertTrue(hasattr(class_instance, 'get_absolute_url'))
        self.assertTrue(hasattr(class_instance, 'get_admin_url'))
