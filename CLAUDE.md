# Are-Self Style Guide

This document defines the engineering standards for Are-Self. Every contributor — human or AI agent — must follow these
rules. No exceptions. No "I'll clean it up later." If it's in the codebase, it meets this standard.

## Baseline

Google Python Style Guide. Everything below either reinforces or overrides it for this project.

## Naming

Are-Self, not Talos. New code never introduces the word "Talos", "spell", or "cast" in class names, variable names,
function names, or comments. The canonical class prefix where a prefix is needed is `AreSelf`, but prefer no prefix when
the Django app label already provides namespace (e.g., `Engram` inside the `hippocampus` app, not `AreSelfEngram`).

Use `snake_case` for functions, methods, variables, and module names. Use `PascalCase` for classes. Use
`UPPER_SNAKE_CASE` for module-level constants. No exceptions.

## No Nested Functions

Never define a function inside another function. If you need a helper, make it a module-level function. Closures are
banned. Lambda is acceptable only in trivial one-liners passed to `sync_to_async`, `sorted()`, or ORM calls where
extracting it would reduce clarity.

## Functions vs. Methods

If it doesn't use `self`, it is a module-level function, not a method. If it doesn't use `cls`, it is a module-level
function, not a `@classmethod`. Classes are for state. Stateless logic lives at module scope.

## No Repeated String Literals

If a string appears more than once, it becomes a constant at module scope or a class-level attribute. Use the
`common/constants.py` pattern for cross-cutting values. Use class-level constants (e.g., `RELATED_NAME = 'engrams'`) for
model-specific repeated strings.

## Constants on Model Classes

Integer FK reference constants live on the model class they point to:

```python
class SpikeStatus(NameMixin):
    PENDING = 1
    ACTIVE = 2
    SUCCESS = 3
    FAILED = 4
```

This makes callsites self-documenting: `SpikeStatus.PENDING` not `1`.

## Small Testable Units

Every function should do one thing. If you can't describe what a function does in a single sentence without the word "
and", split it. The goal: any function can be tested by calling it directly with known inputs and asserting on the
return value or a single side effect.

## Error Handling

Try/except blocks must be short and targeted. Wrap the specific line that can raise, not 40 lines of logic. Catch the
specific exception, not `Exception`, unless you are at a true boundary (top-level task runner, HTTP view). Always log
the error with enough context to diagnose:

```python
# GOOD
try:
    engram = TalosEngram.objects.get(id=engram_id)
except TalosEngram.DoesNotExist:
    logger.error('[Hippocampus] Engram %s not found.', engram_id)
    return None

# BAD
try:
    engram = TalosEngram.objects.get(id=engram_id)
    engram.sessions.add(session)
    engram.spikes.add(spike)
    tags = process_tags(engram)
    engram.save()
except Exception as e:
    logger.error(f'Something went wrong: {e}')
```

The only acceptable broad `except Exception` is at the outermost boundary of a Celery task or the Frontal Lobe `run()`
method, where crashing the process is worse than logging and continuing.

Never silently swallow exceptions. Every `except` block either logs, re-raises, or returns a meaningful error to the
caller.

## Logging

Verbose logging is a feature. Every significant state change, tool execution, model selection, and session transition
should log at `INFO` or `DEBUG`. Use bracketed component tags:

```python
logger.info('[FrontalLobe] Session %s started. Turns: %d', session.id, max_turns)
logger.warning('[Synapse] Circuit breaker tripped for %s.', model_id)
logger.debug('[ParietalMCP] Executing %s with args: %s', tool_name, safe_args)
```

Use `%s` formatting in logger calls, not f-strings. The logger defers string interpolation until the message is actually
emitted, which matters at `DEBUG` level in production.

## Async Policy

Async is intentional, not infectious. Use async for:

- WebSocket streaming (Glutamate neurotransmitters, log mirroring).
- The Nerve Terminal (remote process execution with async generators).
- Any code path that genuinely benefits from concurrent I/O.

Do not use async merely because a caller is async. The Frontal Lobe reasoning loop runs inside a Celery worker. The
Celery worker calls `async_to_sync` at the boundary. Inside that boundary, `sync_to_async` wrapping is acceptable for
ORM calls but should not proliferate into every helper function. If a function is purely synchronous DB work called from
an async context, write it synchronously and wrap it once at the call site.

## Django Models

Use the established mixin hierarchy from `common/models.py`: `CreatedMixin`, `ModifiedMixin`,
`CreatedAndModifiedWithDelta`, `NameMixin`, `DefaultFieldsMixin`, `UUIDIdMixin`, `DescriptionMixin`. Do not reinvent
timestamps or naming patterns.

`RELATED_NAME` should be a class-level constant when used across multiple ForeignKeys on the same model.

Abstract mixins (`class Meta: abstract = True`) for cross-cutting concerns like `ReasoningStatusMixin`.

## Testing

All tests inherit from `CommonTestCase` or `CommonFixturesAPITestCase`. Tests use the real database with fixtures, not
mocks. Django + PostgreSQL is the product; abstracting it away in tests is lying to yourself.

Test names and docstrings may exceed the line length limit. Docstrings begin with the word "Assert":

```python
def test_yield_turn_pauses_session(self):
    """Assert mcp_respond_to_user with yield_turn=True sets session status to ATTENTION_REQUIRED."""
```

Do not mock Django models. Use fixture data. If setup requires more than what fixtures provide, build the objects in
`setUp()` using the ORM directly.

## Type Hints

Type hints on all function signatures, including return types. Use `Optional[X]` not `X | None` for Django model fields
that can be null (consistency with the existing codebase). Use built-in generics (`list`, `dict`, `tuple`) not
`typing.List`, `typing.Dict`, `typing.Tuple` (Python 3.10+).

## Imports

Standard library, then blank line, then third-party, then blank line, then Django, then blank line, then project
imports. Within each group, alphabetical. `isort` compatible.

## Docstrings

Google style. Classes always get a docstring. Public methods get a docstring if the behavior isn't obvious from the name
and type hints. Private helpers and short pure functions can skip docstrings if the name is self-documenting. Args
sections only when parameter names aren't self-explanatory.

## Fixtures

Tool definitions, parameters, and assignments live in `initial_data.json` fixtures. PKs are stable integers used as
class-level constants. Never change an existing PK. Add new records with the next available PK. Old records are
deprecated in place, never deleted, because existing sessions reference them.

## Line Length

88 characters for code (Black default). Test names, test docstrings, and URLs are exempt.

## Formatting

Single quotes for strings unless the string contains a single quote. No trailing commas in function signatures (but yes
in collections and Django model field definitions for clean diffs). Black-compatible formatting throughout.