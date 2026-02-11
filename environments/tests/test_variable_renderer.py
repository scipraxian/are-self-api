import socket
from unittest.mock import MagicMock

from django.test import TestCase

from environments.models import (
    ContextVariable,
    ProjectEnvironment,
    ProjectEnvironmentContextKey,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)
from environments.variable_renderer import VariableRenderer
from hydra.constants import KEY_SERVER


class VariableRendererTest(TestCase):

    def setUp(self):
        self.env_type = ProjectEnvironmentType.objects.create(
            name="TestEnvType")
        self.env_status = ProjectEnvironmentStatus.objects.create(
            name="TestStatus")
        self.env = ProjectEnvironment.objects.create(
            name="TestEnv",
            type=self.env_type,
            status=self.env_status,
        )
        self.key1 = ProjectEnvironmentContextKey.objects.create(name="var1")
        self.key2 = ProjectEnvironmentContextKey.objects.create(name="var2")
        ContextVariable.objects.create(environment=self.env,
                                       key=self.key1,
                                       value="val1")
        ContextVariable.objects.create(environment=self.env,
                                       key=self.key2,
                                       value="val2")

    def test_extract_variables(self):
        context = VariableRenderer.extract_variables(self.env)
        self.assertEqual(context["var1"], "val1")
        self.assertEqual(context["var2"], "val2")
        self.assertEqual(context[KEY_SERVER], socket.gethostname())

    def test_extract_variables_none(self):
        context = VariableRenderer.extract_variables(None)
        self.assertEqual(context[KEY_SERVER], socket.gethostname())
        self.assertNotIn("var1", context)

    def test_render_string_basic(self):
        template = "Hello {{ var1 }}"
        context = {"var1": "World"}
        rendered = VariableRenderer.render_string(template, context)
        self.assertEqual(rendered, "Hello World")

    def test_render_string_missing_var(self):
        template = "Hello {{ var1 }}"
        context = {}
        # Django template renders missing variables as empty string by default
        rendered = VariableRenderer.render_string(template, context)
        self.assertEqual(rendered, "Hello ")

    def test_render_string_no_template(self):
        template = "Hello World"
        context = {"var1": "val1"}
        rendered = VariableRenderer.render_string(template, context)
        self.assertEqual(rendered, "Hello World")

    def test_render_string_error_handling(self):
        # Even if context is invalid, it shouldn't crash
        template = "Hello {{ var1 }}"
        context = 123

        # Django apparently handles even integer contexts without crashing,
        # treating them as empty. Use that behavior.
        rendered = VariableRenderer.render_string(template, context)
        self.assertEqual(rendered, "Hello ")
