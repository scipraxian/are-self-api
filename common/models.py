"""A set of common mixins for models."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.measure import Distance
from django.db import models
from django.urls import reverse
from django.utils.timezone import now

from common.constants import STANDARD_CHARFIELD_LENGTH


class CreatedMixin(models.Model):
    """Adds an auto populated created field to a model."""
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class CreatedByMixin(models.Model):
    """Adds created_by."""
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.CASCADE,
                                   related_name="%(class)s_created_by",
                                   blank=True,
                                   null=True)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class ModifiedByMixin(models.Model):
    """Adds created_by."""
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.CASCADE,
                                    related_name="%(class)s_modified_by",
                                    blank=True,
                                    null=True)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class DescriptionMixin(models.Model):
    """Adds a standard sized description field to a model."""
    description = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH,
                                   blank=True,
                                   null=True)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class ModifiedMixin(models.Model):
    """Adds an auto populated modified field to a model."""
    modified = models.DateTimeField(auto_now=True, db_index=True)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class CreatedAndModifiedBy(CreatedMixin, CreatedByMixin, ModifiedMixin,
                           ModifiedByMixin):
    """Mixin for Create and Modified and By."""

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class NameMixin(models.Model):
    """Adds standard length name to a model, and makes name typical output."""
    name = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH,
                            db_index=True,
                            unique=True)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True

    def __str__(self):
        """Simple default helper for objects with the NameMixin."""
        return self.name

    def natural_key(self):
        """Shows 'name' instead of PK when serializing with natural_keys."""
        return self.name


class DefaultFieldsMixin(CreatedMixin, ModifiedMixin, NameMixin):
    """A model which contains the typical startup fields for a model."""

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class DjangoAdminReverseRequirementsMixin(object):
    """Reverse a URL from a template and 'view on site' for the admin.
        {% url object_instance|admin_urlname:'add' }%"""

    @property
    def app_label(self):
        """Access the _meta option directly, useful for templates and names."""
        return self._meta.app_label

    @property
    def model_name(self):
        """Access the _meta option directly, useful for templates and names."""
        return self._meta.model_name

    def get_absolute_url(self):
        """Allows this model to have the expected reverse URL."""
        reverse_string = '{app_label}:{model_name}'.format(
            app_label=self.app_label, model_name=self.model_name)
        return reverse(reverse_string, kwargs={'pk': self.pk})

    def get_admin_url(self):
        """Generate the Admin URL for django 2."""
        content_type = ContentType.objects.get_for_model(self.__class__)
        return reverse("admin:%s_%s_change" %
                       (content_type.app_label, content_type.model),
                       args=(self.id,))


class UUIDIdMixin(models.Model):
    """UUID ID Keys."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta(object):
        """Standard Django Meta object, for model configuration."""
        abstract = True


class BigIdMixin(models.Model):
    """Large ID keys."""
    id = models.BigAutoField(primary_key=True)

    class Meta(object):  # pylint:disable=too-few-public-methods
        """Django meta module."""
        abstract = True
