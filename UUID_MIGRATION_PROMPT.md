# Prompt 1: UUID Migration for Plugin-Extensible Models

## Context

Are-Self is a neurologically-inspired AI reasoning engine built on Django 6.x / DRF / Celery / PostgreSQL+pgvector. Every Django app models a brain region. The codebase is about to undergo a plugin-architecture refactor where certain models become install/uninstall-able as plugin bundles (Unreal Engine flow will be the first extracted plugin).

For plugins to work without PK collisions across independent installations, **plugin-extensible model PKs must be UUIDs instead of BigAutoField integers.** Plugin A on one machine can't safely ship `Effector(id=147)` if plugin B on another machine already has `Effector(id=147)`.

This prompt is **Pass 1 of 2**. Its only job is the UUID migration — mechanical PK type conversion on a specific list of models. No other behavior changes. Fixture separation, plugin extraction, and code reorganization happen in a later pass. Keep this pass small, reviewable, and reversible.

## Hard Scope Rules

- **YES:** Swap PK type from integer to UUID on the models listed below. Update migrations. Update any code that treats those PKs as integers. Regenerate fixtures with new UUIDs. Keep tests passing.
- **NO:** Do not split fixtures. Do not move files between apps. Do not extract a plugin. Do not touch `ue_tools/`. Do not remove `ollama_fixture_generator.py`. Do not change business logic. Do not "improve" things you notice along the way — file a TODO instead.
- **If uncertain about scope, stop and ask.** Bias toward smaller diffs.

## Architectural Line: Integer vs UUID

**Stay integer (protocol enums / canonical vocabularies — never extended by plugins):**
- `spike.SpikeStatus`
- `axon.AxonType`
- `central_nervous_system.CNSDistributionMode`
- `identity.IdentityAddonPhase`
- `budget.BudgetPeriod`
- `ai_model.AIModelCapabilities`, `AIModes`, `AIModelRole`, `AIModelQuantization`
- `iteration.ShiftType`
- Any other small lookup/enum model whose rows are defined by core and never added to by plugins.

**Migrate to UUID (plugin-extensible — plugins will ship their own rows):**
- `effector.Effector`
- `effector.EffectorArgumentAssignment`
- `effector.EffectorContext`
- `executable.Executable`
- `executable.ExecutableSwitch`
- `executable.ExecutableArgument`
- `executable.ExecutableArgumentAssignment`
- `parietal_mcp.ToolDefinition` (or wherever it lives — confirm location)
- `parietal_mcp.ToolParameter`
- `parietal_mcp.ParameterEnum`
- `parietal_mcp.ToolParameterAssignment`
- `axon.NeuralPathway`
- `neuron.Neuron`
- `neuron.NeuronContext`
- `axon.Axon`
- `ai_model.AIModelDescription`
- `iteration.IterationDefinition`
- `iteration.IterationShiftDefinition`
- `context.ContextVariable` (or wherever it lives)

**Already UUID (no change needed — but verify):**
- `identity.Identity` (has `Identity.THALAMUS` UUID constant)
- `identity.IdentityDisc` (has `IdentityDisc.THALAMUS` UUID constant)
- `environments.ProjectEnvironment` (has `ProjectEnvironment.DEFAULT_ENVIRONMENT` UUID constant)

**Before starting, validate the list above against the actual codebase.** If a model is missing, mis-named, or shouldn't be in a list, surface it and ask before proceeding. The list reflects my current understanding; you have ground truth.

## Mixins

`common/models.py` defines `UUIDIdMixin` and `BigIdMixin`:

```python
class UUIDIdMixin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Meta: abstract = True

class BigIdMixin(models.Model):
    id = models.BigAutoField(primary_key=True)
    class Meta: abstract = True
```

The migration is primarily: replace `BigIdMixin` with `UUIDIdMixin` in the model class definition. Django's `makemigrations` will generate the PK type change + cascade updates to every FK pointing at that model.

## UUID Strategy

Use `uuid4` (random). **Do not** use `uuid5` with namespaces. The UUIDs get written into fixture JSON as literals once and then never regenerated. No deterministic-generation requirement. Keep it simple.

## Execution Plan

1. **Branch.** Create a branch named `uuid-migration` off current HEAD. All work on this branch.

2. **Validate the model list.** For each model above, confirm:
   - It currently uses `BigIdMixin` (or equivalent integer PK).
   - It's genuinely plugin-extensible (shipped rows will be supplemented by plugin rows).
   - No hidden reason it needs to stay integer (performance-critical FK on a massive table, raw SQL that assumes int, etc.).
   Report any findings before changing code.

3. **Hazard scan — run these greps and resolve each hit:**
   - `Identity.THALAMUS`, `IdentityDisc.THALAMUS`, `ProjectEnvironment.DEFAULT_ENVIRONMENT` — these are UUID class constants already in production use (see `thalamus/api.py:106`, `central_nervous_system/utils.py:86`). They should not break, but verify.
   - For each migrating model `Foo`, grep for `Foo\.[A-Z_]+\s*=\s*\d+` — class-level integer PK constants (like `Effector.FRONTAL_LOBE = 8`). Every one of these must change to a `UUID('...')` literal **and every call site must continue working** because the constant's name doesn't change, only its type.
   - Grep for `_id=\s*\d+`, `id=\d+`, `.filter(id=\d`, `.get(id=\d` on migrating models.
   - Grep for raw SQL referencing PKs of migrating models.
   - Grep for int-cast patterns: `int(obj.id)`, `int(.*_id)`.
   - Grep for URL patterns using `<int:pk>` or `<int:id>` on views for migrating models.
   - Grep for serializer fields that declare `IntegerField` for a PK or FK on a migrating model.

4. **Mixin swap.** For each model in the migrate list, change `BigIdMixin` → `UUIDIdMixin`. Do this one app at a time, running `makemigrations {app}` after each, so migrations stay readable per-app.

5. **Update class-level PK constants.** For every `Effector.FRONTAL_LOBE = 8` style constant on a migrating model, pick a `uuid4` once and write it in as `Effector.FRONTAL_LOBE = uuid.UUID('...')`. Same constant name, new type. Record the mapping (old int → new UUID) in a temporary file `uuid_migration_mapping.json` at repo root — you'll need it in step 6.

6. **Regenerate fixtures.** The existing `initial_data.json` files have integer PKs and integer FK references for migrating models. Two options:
   - **Option A (preferred if clean):** Use the `uuid_migration_mapping.json` to transform existing fixture JSON in place. For every row whose model is migrating, replace `pk: 8` with `pk: "uuid-string"`. For every FK field on any model (migrating or not) that points at a migrating model, replace the integer FK value with the matching UUID. Write a one-off script `scripts/migrate_fixture_uuids.py` that does this from the mapping file. Commit the script alongside the migration — it's reference documentation for the pass.
   - **Option B (fallback):** If the fixture graph is too tangled, `dumpdata` from a freshly-migrated dev DB that was loaded from old fixtures, captured post-migration. Less traceable, only use if A gets stuck.

7. **Code updates.** Fix every hit from the hazard scan in step 3. For each fix, prefer the smallest change that preserves behavior:
   - `<int:pk>` URL patterns → `<uuid:pk>` on migrating models.
   - Integer PK constants → UUID constants (already done in step 5, but double-check callers).
   - Raw SQL → parameterized with UUID values.
   - Serializer `IntegerField` → `UUIDField` for affected PK/FK fields.

8. **Run migrations locally.** `./manage.py migrate` against a fresh dev DB (drop and recreate if needed — this is a migration pass, destructive-to-local-data is fine). Load fixtures. Verify the app boots.

9. **Run the full test suite.** Fix failures that are type-mismatch (int vs UUID) only. If a test fails for a non-type-related reason, STOP and surface it — that means the migration changed behavior somewhere it shouldn't have.

10. **Diff review.** Generate `git diff main...uuid-migration` and walk it. Every change should fall into one of these buckets:
    - Mixin swap (`BigIdMixin` → `UUIDIdMixin`)
    - Auto-generated migration files
    - Class-level PK constant retype
    - Fixture PK/FK value retype
    - URL pattern retype (`<int:pk>` → `<uuid:pk>`)
    - Serializer field retype
    - The one-off fixture transformation script
    - Test adjustments for type (rare — most tests should pass unchanged)
    
    Anything outside those buckets is out of scope for this pass — revert it.

## Acceptance Criteria

- `git diff main...uuid-migration` contains only the change categories listed in step 10.
- `./manage.py check` passes.
- `./manage.py migrate` applies cleanly on a fresh DB.
- Full test suite passes.
- All existing class-level PK constants (`Effector.FRONTAL_LOBE`, etc.) still resolve and still point at the correct logical row (just by UUID now).
- No changes to `ue_tools/`, no fixture splitting, no plugin extraction, no removal of `ollama_fixture_generator.py`. Those are deferred to Pass 2.
- `uuid_migration_mapping.json` committed at repo root for audit.

## If You Get Stuck

- **Fixture graph is tangled beyond reasonable scripting:** fall back to Option B in step 6, document why.
- **A model's PK type seems like it should migrate but doing so cascades into unexpected territory:** stop, document, ask.
- **A test fails for a non-type reason after migration:** stop, document, ask. Do not "fix" by changing logic.
- **You discover the integer-vs-UUID categorization in this prompt is wrong for a specific model:** stop, ask. The list is my best guess; you have ground truth.

## Out of Scope (Pass 2, Do Not Touch)

- Splitting `initial_data.json` into per-app / per-tier fixture files.
- Extracting the Unreal flow as a plugin bundle.
- Moving `merge_logs.py` / `merge_logs_nway.py` to `occipital_lobe/`.
- Splitting `log_parser.py` (generic vs UE-specific).
- Removing `ollama_fixture_generator.py`.
- Creating the `plugins` Django app (Michael is doing that himself after Pass 1 lands).
- Any refactor not directly required to make integer PKs into UUID PKs.

Focus. Small diff. Reviewable. Reversible. Then merge, then we plan Pass 2.
