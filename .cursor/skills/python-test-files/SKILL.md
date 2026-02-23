---
name: python-test-files
description: Create, batch-create, or check Python test files per project styling and Talos engineering standards. Use when adding tests for a module, generating tests for multiple modules, or auditing test files for compliance and robustness.
---

# Python Test Files

## When to Use

- **Create**: User asks for tests for a specific module, class, or function.
- **Batch create**: User asks for tests for a package or a list of modules.
- **Check**: User asks to verify or fix test files against the rules.

## Rules Summary

- **Imports**: Three groups (stdlib → third-party → local), sorted; no local imports inside functions.
- **Framework**: Prefer pytest. For **DB-touching tests** use `django.test.TestCase` and `@pytest.mark.django_db` (or a class inheriting TestCase with django_db). Never write to the live database; use fixtures or in-test creation.
- **Setup**: Use pytest fixtures or TestCase `setUp`; separate setup from assertions.
- **Scenarios**: Use `@pytest.mark.parametrize` for multiple inputs/expected outcomes when it simplifies tests.
- **Naming**: Test names may be long; must be descriptive (e.g. `test_run_hydra_pipeline_leash_broken`).
- **Docstrings**: Every test (or test class) has a docstring. Prefer one sentence; start with "Assert...", "Verify...", or "Ensure..." where natural. For critical behavior, add a short note (e.g. "CRITICAL: ...").
- **Determinism**: No dependence on wall-clock, network, or shared DB; use mocks, fixtures, or `tmp_path`.
- **Scope**: Do not test Django, hardware, database, network, OS, or external services; test project logic thoroughly.
- **Style**: Google-style docstrings, type hints on public helpers, one blank line at end of file. Explicit `object` for classes if the project uses it.

## Create Workflow

1. **Identify SUT**: Determine the module/class/function under test and whether it touches the DB or is async.
2. **Choose pattern**:
   - Pure pytest (no DB): plain pytest, `tmp_path` for files.
   - DB: pytest + `TestCase` + `@pytest.mark.django_db`, `fixtures = [...]`, `setUp()` for shared state.
   - Async: `@pytest.mark.asyncio`; on Windows set `asyncio.WindowsProactorEventLoopPolicy()` at module level.
3. **Placement**: `tests/test_<module>.py` or `tests/test_<module>_<aspect>.py` next to the package.
4. **Reuse patterns**: Async fixture for server/agent; `setUp` + `fixtures` for Django; async helpers for streams; pytest fixtures for mocks (see [reference.md](reference.md)).
5. **Write tests**: One logical behavior per test; use parametrize for multiple cases; document critical behavior in docstrings.

## Batch Create Workflow

1. **Discover targets**: List modules/classes that need tests (user-provided or by scanning a package).
2. **Per target**: Apply the Create workflow; one test file per module or per logical group to keep files focused.
3. **Optional**: Produce a short checklist (e.g. `test_foo.py`, `test_bar.py`, ...) for the user.

## Check Workflow

For each given (or discovered) test file, verify:

- **Imports**: Three groups, no wildcards, no local imports in test body.
- **DB**: Uses TestCase + fixtures or in-test creation; no `manage.py migrate` or live DB.
- **Fixtures/setUp**: Used; assertions separated from setup.
- **Docstrings**: Test and class docstrings present; naming descriptive.
- **Determinism**: Mocks, tmp_path, or fixtures; no network or live DB.
- **Parametrize**: Used where multiple similar cases exist.

Report violations and suggest minimal fixes; do not reformat unrelated code.

## References

- Project styling and test style: [.cursor/rules/python-lang-styling.mdc](.cursor/rules/python-lang-styling.mdc) (D.8, D.1.4, D.3, D.7).
- Inviolate project rules: [.cursor/rules/talos-engineering-standards.mdc](.cursor/rules/talos-engineering-standards.mdc) (testing).
- Condensed rules and codebase examples: [reference.md](reference.md).
