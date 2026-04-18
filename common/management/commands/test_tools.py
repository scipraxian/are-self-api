import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from parietal_lobe.models import (
    ParameterEnum,
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
)

logger = logging.getLogger(__name__)

# ── Map your ToolParameterType PKs → OpenAI JSON Schema types ────────
TYPE_MAP = {
    1: 'string',
    2: 'number',
    3: 'integer',
    4: 'boolean',
    5: 'array',
    6: 'object',
    7: 'null',
}


class Command(BaseCommand):
    help = 'Test each ToolDefinition against the LLM endpoint to isolate 400 errors.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--model',
            type=str,
            default=None,
            help='Model to test against (defaults to OPENROUTER_MODEL setting or openrouter/hunter-alpha)',
        )
        parser.add_argument(
            '--url',
            type=str,
            default=None,
            help='Chat completions URL (defaults to OPENROUTER_BASE_URL setting)',
        )
        parser.add_argument(
            '--api-key',
            type=str,
            default=None,
            help='API key (defaults to OPENROUTER_API_KEY setting/env)',
        )
        parser.add_argument(
            '--tool-ids',
            type=str,
            default=None,
            help='Comma-separated ToolDefinition IDs to test (default: all)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print the full tool schema for each test',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Request timeout in seconds',
        )

    def handle(self, *args, **options):
        self.verbose = options['verbose']
        self.timeout = options['timeout']

        # ── Resolve config ───────────────────────────────────────────
        self.chat_url = (
            options['url']
            or getattr(
                settings, 'OPENROUTER_BASE_URL', 'https://openrouter.ai/api'
            ).rstrip('/')
            + '/v1/chat/completions'
        )
        self.model = (
            options['model']
            or getattr(settings, 'OPENROUTER_MODEL', None)
            or 'openrouter/hunter-alpha'
        )
        self.api_key = (
            options['api_key']
            or getattr(settings, 'OPENROUTER_API_KEY', None)
            or os.environ.get('OPENROUTER_API_KEY', '')
        ).strip()

        if not self.api_key:
            self.stderr.write(
                self.style.ERROR(
                    'No API key found. Set OPENROUTER_API_KEY in settings, env, or pass --api-key.'
                )
            )
            sys.exit(1)

        # ── Load tools ───────────────────────────────────────────────
        queryset = ToolDefinition.objects.prefetch_related(
            'assignments__parameter__type',
            'assignments__parameter__enum_values',
        ).all()

        if options['tool_ids']:
            ids = [x.strip() for x in options['tool_ids'].split(',')]
            queryset = queryset.filter(id__in=ids)

        tools = list(queryset)
        if not tools:
            self.stdout.write(self.style.WARNING('No ToolDefinitions found.'))
            return

        self.stdout.write(
            self.style.HTTP_INFO(
                f'\n{"=" * 70}\n'
                f'TOOL DIAGNOSTIC\n'
                f'  Model:  {self.model}\n'
                f'  URL:    {self.chat_url}\n'
                f'  Tools:  {len(tools)}\n'
                f'{"=" * 70}\n'
            )
        )

        # ── Phase 1: Static schema checks ───────────────────────────
        self.stdout.write(
            self.style.HTTP_INFO('📋 Phase 1: Static Schema Checks\n')
        )
        all_schemas: List[Dict[str, Any]] = []
        schema_issues: Dict[int, List[str]] = {}

        for tool in tools:
            schema = self._build_tool_schema(tool)
            all_schemas.append(schema)
            issues = self._validate_schema(schema)
            if issues:
                schema_issues[tool.id] = issues
                self.stdout.write(f'  [{tool.id}] {tool.name}')
                for issue in issues:
                    self.stdout.write(self.style.WARNING(f'      ⚠ {issue}'))
            else:
                self.stdout.write(
                    f'  [{tool.id}] {tool.name} — schema looks clean'
                )

            if self.verbose:
                self.stdout.write(f'      {json.dumps(schema, indent=6)}\n')

        # ── Phase 2: Live isolation tests ────────────────────────────
        self.stdout.write(
            self.style.HTTP_INFO(
                f'\n\n🔬 Phase 2: Live Isolation Tests\n'
                f'  Sending one request per tool...\n'
            )
        )

        results: List[Dict[str, Any]] = []
        for tool, schema in zip(tools, all_schemas):
            self.stdout.write(
                f'  Testing [{tool.id}] {tool.name}...', ending=' '
            )
            self.stdout.flush()

            result = self._test_single_tool(schema, tool.id, tool.name)
            results.append(result)

            if result['status'] == 'OK':
                self.stdout.write(self.style.SUCCESS('✓ OK'))
            else:
                self.stdout.write(
                    self.style.ERROR(f'✗ FAIL ({result["code"]})')
                )
                error = result.get('error', '')
                if isinstance(error, dict):
                    for line in json.dumps(error, indent=4).split('\n'):
                        self.stdout.write(self.style.ERROR(f'       {line}'))
                else:
                    self.stdout.write(
                        self.style.ERROR(f'       {str(error)[:400]}')
                    )

        # ── Phase 3: Combined test if all pass individually ─────────
        failed = [r for r in results if r['status'] != 'OK']

        if not failed:
            self.stdout.write(
                self.style.HTTP_INFO(
                    '\n\n🤔 All tools pass individually.\n'
                    '   Testing all tools together...\n'
                )
            )
            self.stdout.write(
                f'  Sending {len(all_schemas)} tools in one request...',
                ending=' ',
            )
            self.stdout.flush()

            combined = self._test_combined(all_schemas)
            if combined['status'] == 'OK':
                self.stdout.write(self.style.SUCCESS('✓ OK'))
                self.stdout.write(
                    self.style.WARNING(
                        '\n  Intermittent issue? The 400 may be model-specific or load-dependent.\n'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'✗ FAIL ({combined["code"]})')
                )
                error = combined.get('error', '')
                if isinstance(error, dict):
                    for line in json.dumps(error, indent=4).split('\n'):
                        self.stdout.write(self.style.ERROR(f'    {line}'))
                else:
                    self.stdout.write(
                        self.style.ERROR(f'    {str(error)[:400]}')
                    )

                # Binary search
                self._binary_search(all_schemas, tools)

        # ── Summary ──────────────────────────────────────────────────
        self.stdout.write(f'\n{"=" * 70}')
        self.stdout.write(self.style.HTTP_INFO('SUMMARY'))
        self.stdout.write(f'{"=" * 70}')

        ok = [r for r in results if r['status'] == 'OK']
        fail = [r for r in results if r['status'] != 'OK']

        self.stdout.write(f'  Passed:       {len(ok)}/{len(results)}')
        self.stdout.write(f'  Schema issues: {len(schema_issues)}')

        if fail:
            self.stdout.write(self.style.ERROR(f'\n  🔴 Suspect tools:'))
            for r in fail:
                self.stdout.write(
                    self.style.ERROR(f'    - [{r["tool_id"]}] {r["name"]}')
                )

        if schema_issues:
            self.stdout.write(
                self.style.WARNING(f'\n  ⚠  Tools with schema warnings:')
            )
            for tid, issues in schema_issues.items():
                name = next((t.name for t in tools if t.id == tid), f'id={tid}')
                self.stdout.write(self.style.WARNING(f'    - [{tid}] {name}'))
                for issue in issues:
                    self.stdout.write(self.style.WARNING(f'        {issue}'))

        self.stdout.write('')

    # ──────────────────────────────────────────────────────────────────
    # Schema builder — mirrors what your system does at runtime
    # ──────────────────────────────────────────────────────────────────

    def _build_tool_schema(self, tool: ToolDefinition) -> Dict[str, Any]:
        """Build an OpenAI-compatible tool dict from a ToolDefinition."""
        properties: Dict[str, Any] = {}
        required: List[str] = []

        assignments = (
            tool.assignments.all()
            .select_related('parameter__type')
            .prefetch_related('parameter__enum_values')
        )

        for assignment in assignments:
            param = assignment.parameter
            param_type_name = TYPE_MAP.get(param.type_id, 'string')
            prop: Dict[str, Any] = {'type': param_type_name}

            if param.description:
                prop['description'] = param.description

            # Enums
            enum_vals = list(param.enum_values.values_list('value', flat=True))
            if enum_vals:
                prop['enum'] = enum_vals

            properties[param.name] = prop

            if assignment.required:
                required.append(param.name)

        schema: Dict[str, Any] = {
            'type': 'function',
            'function': {
                'name': tool.name,
                'description': tool.description or '',
                'parameters': {
                    'type': 'object',
                    'properties': properties,
                },
            },
        }

        if required:
            schema['function']['parameters']['required'] = required

        return schema

    # ──────────────────────────────────────────────────────────────────
    # Static validators
    # ──────────────────────────────────────────────────────────────────

    def _validate_schema(self, tool: Dict[str, Any]) -> List[str]:
        """Check a single tool definition for common issues."""
        warnings: List[str] = []
        fn = tool.get('function', {})
        name = fn.get('name', '')

        if not name:
            warnings.append('Missing function.name')
        if len(name) > 64:
            warnings.append(
                f'Function name too long ({len(name)} chars, max ~64)'
            )
        if name and not all(c.isalnum() or c in ('_', '-') for c in name):
            warnings.append(f"Function name '{name}' has unusual characters")

        params = fn.get('parameters', {})
        if not isinstance(params, dict):
            warnings.append(f'parameters is not a dict: {type(params)}')
            return warnings

        # Depth check
        def _depth(obj, d=0):
            if isinstance(obj, dict):
                return max((_depth(v, d + 1) for v in obj.values()), default=d)
            if isinstance(obj, list):
                return max((_depth(v, d + 1) for v in obj), default=d)
            return d

        depth = _depth(params)
        if depth > 10:
            warnings.append(f'Schema nesting too deep (depth={depth})')

        # $ref check
        def _has_ref(obj):
            if isinstance(obj, dict):
                if '$ref' in obj:
                    return True
                return any(_has_ref(v) for v in obj.values())
            if isinstance(obj, list):
                return any(_has_ref(v) for v in obj)
            return False

        if _has_ref(params):
            warnings.append('Schema contains $ref (many providers reject this)')

        # Enum size
        def _check_enum_sizes(obj, path=''):
            if isinstance(obj, dict):
                if 'enum' in obj and isinstance(obj['enum'], list):
                    if len(obj['enum']) > 100:
                        warnings.append(
                            f"enum at '{path}' has {len(obj['enum'])} values (too many)"
                        )
                for k, v in obj.items():
                    _check_enum_sizes(v, f'{path}.{k}' if path else k)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _check_enum_sizes(v, f'{path}[{i}]')

        _check_enum_sizes(params)

        # Total size
        size = len(json.dumps(params))
        if size > 10_000:
            warnings.append(f'Schema very large ({size:,} chars)')

        return warnings

    # ──────────────────────────────────────────────────────────────────
    # HTTP testers
    # ──────────────────────────────────────────────────────────────────

    def _test_single_tool(
        self, tool_schema: Dict[str, Any], tool_id: int, tool_name: str
    ) -> Dict[str, Any]:
        """Send a request with only this one tool."""
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': 'Say hello.'}],
            'tools': [tool_schema],
            'tool_choice': 'auto',
            'max_tokens': 100,
        }
        return self._send(payload, tool_id, tool_name)

    def _test_combined(
        self, tool_schemas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send all tools together."""
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': 'Say hello.'}],
            'tools': tool_schemas,
            'tool_choice': 'auto',
            'max_tokens': 100,
        }
        return self._send(payload, tool_id=0, tool_name='(combined)')

    def _send(
        self,
        payload: Dict[str, Any],
        tool_id: int,
        tool_name: str,
    ) -> Dict[str, Any]:
        """Low-level HTTP call. Returns result dict."""

        payload['provider'] = {
            'order': ['Stealth'],
            'allow_fallbacks': False,
        }

        try:
            resp = requests.post(
                self.chat_url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}',
                },
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                return {
                    'status': 'OK',
                    'code': 200,
                    'tool_id': tool_id,
                    'name': tool_name,
                }

            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text[:500]

            return {
                'status': 'FAIL',
                'code': resp.status_code,
                'tool_id': tool_id,
                'name': tool_name,
                'error': error_body,
            }

        except Exception as e:
            return {
                'status': 'EXCEPTION',
                'code': 0,
                'tool_id': tool_id,
                'name': tool_name,
                'error': str(e),
            }

    # ──────────────────────────────────────────────────────────────────
    # Binary search when combined fails but individual passes
    # ──────────────────────────────────────────────────────────────────

    def _binary_search(
        self,
        schemas: List[Dict[str, Any]],
        tools: List[ToolDefinition],
        depth: int = 0,
    ):
        """Recursively narrow down which group of tools causes the failure."""
        indent = '  ' + ('    ' * depth)

        if len(schemas) <= 1:
            self.stdout.write(
                self.style.ERROR(
                    f'{indent}  → Tool [{tools[0].id}] {tools[0].name} fails only in combination'
                )
            )
            return

        mid = len(schemas) // 2
        left_schemas, right_schemas = schemas[:mid], schemas[mid:]
        left_tools, right_tools = tools[:mid], tools[mid:]

        self.stdout.write(
            f'{indent}  Split [{len(left_schemas)} + {len(right_schemas)}]...'
        )

        left_result = self._test_combined(left_schemas)
        right_result = self._test_combined(right_schemas)

        left_status = (
            self.style.SUCCESS('✓')
            if left_result['status'] == 'OK'
            else self.style.ERROR('✗')
        )
        right_status = (
            self.style.SUCCESS('✓')
            if right_result['status'] == 'OK'
            else self.style.ERROR('✗')
        )

        self.stdout.write(f'{indent}    First half:  {left_status}')
        self.stdout.write(f'{indent}    Second half: {right_status}')

        if left_result['status'] != 'OK':
            self._binary_search(left_schemas, left_tools, depth + 1)
        if right_result['status'] != 'OK':
            self._binary_search(right_schemas, right_tools, depth + 1)


"""
```

**Usage:**

```bash
# Test all tools
python manage.py test_tools

# Test specific tools by ID
python manage.py test_tools --tool-ids 5,12,27

# Use a different model or endpoint
python manage.py test_tools --model openai/gpt-4o --verbose

# Pass key directly
python manage.py test_tools --api-key sk-or-xxxxx
```

**What it does:**

1. **Phase 1** — Pulls every `ToolDefinition` from the DB, builds the schema the same way your runtime does, and runs static checks (name validity, nesting depth, `$ref` detection, enum sizes, schema bloat)

2. **Phase 2** — Sends one HTTP request per tool in isolation. If a single tool fails on its own, you've found your culprit immediately

3. **Phase 3** — If everything passes individually but you still get 400s in production, it runs a combined test followed by binary search to find which *group* of tools breaks it — usually hitting a total schema size or tool count limit on the model

The `TYPE_MAP` dict at the top maps your `ToolParameterType` PKs to JSON Schema strings. Adjust if your PKs don't match (1=String, 2=Number, etc.).
"""
