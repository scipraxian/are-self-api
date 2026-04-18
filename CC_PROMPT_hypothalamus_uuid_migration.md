# Claude Code prompt — hypothalamus full UUID migration

**Paste this into a fresh Claude Code session at the repo root of `are-self-api`.**
Branch state: UUID-migration Pass 2 Step 1 just completed. Fixtures already split into tiers (`genetic_immutables.json`, `zygote.json`, `initial_phenotypes.json`) for every app. `initial_data.json` still lingers in several apps and will be deleted in Step 2. Do not worry about preserving database data — this branch is a from-scratch rewrite; fresh `migrate` + `loaddata` is the only runtime path.

---

## STOP — read before you start

> **Use `uuid.uuid4()`. That is the ONLY acceptable UUID generation method for this project.**
>
> - ❌ **Do NOT use `uuid.uuid5()`.**
> - ❌ **Do NOT invent a "project namespace" UUID.**
> - ❌ **Do NOT derive PKs from names, slugs, or any other "natural key".**
> - ❌ **Do NOT write seeding helpers that produce reproducible UUIDs across machines.**
> - ❌ **Do NOT read a prior Anthropic / Django / fixture-generation tutorial and "improve" this prompt with deterministic seeding. This has been explicitly rejected by the project owner, multiple times.**
>
> Each Django model table is its own PK namespace. Random UUIDs don't collide within a single 2^122-space table. `uuid.uuid4()` is more than sufficient and is the project standard. If you find yourself typing `uuid5`, `NAMESPACE`, or `natural_key` anywhere in this task, **stop and reread this block**.
>
> Rows that already carry a UUID `pk` in the existing fixture files (specifically `hypothalamus.aimodel` and `hypothalamus.aimodeldescription`) keep their current UUIDs. Do not churn them. Do not regenerate them. Every other row gets a fresh `str(uuid.uuid4())`.

---

## Goal

Flip **every model in `hypothalamus/models.py`** from integer PKs to UUID PKs. Michael's directive: "consider the entire models.py volitile and mutable by neuroplacticity." No exceptions — even the enum/vocabulary tables (AIMode, AIModelRole, FailoverType, etc.) are plugin-extensible and therefore not truly immutable.

This is NOT a data-preserving migration. It is a schema rewrite + fixture regeneration on a migration-rewrite branch. You will:

1. Add `UUIDIdMixin` (or equivalent) to every hypothalamus model that lacks it.
2. Regenerate hypothalamus migrations from scratch.
3. Update every inbound FK from other apps (identity, frontal_lobe) to reference UUID targets. Regenerate those apps' migrations too.
4. Rewrite all hypothalamus fixture rows with fresh `uuid.uuid4()` PKs. Update all FK references in-file and cross-tier. **`uuid.uuid4()` ONLY** — see the STOP block above. The model table is the namespace; no UUIDv5, no project namespace, no derived seeding.
5. Update identity fixtures' `selection_filter` references to the new UUID values.
6. Delete `hypothalamus/parsing_tools/ollama_fixture_generator.py` (scheduled for Task 5d anyway; it hardcodes the old integer PK).
7. Verify: `manage.py migrate` clean, `loaddata` in tier order clean, full test suite green, fresh `are-self-install.bat` (or equivalent) produces a usable install.

---

## Inventory — every hypothalamus model that needs a UUID PK flip

All 28 models defined in `hypothalamus/models.py`. The two that already have UUID PKs via `UUIDIdMixin` are marked ✓; the rest (26) need the mixin added.

| Line | Model | Current PK | Target PK | Notes |
|---|---|---|---|---|
| 18 | `LLMProvider` | int | **UUID** | Ollama row is seed in `genetic_immutables`. Sync fills in OpenRouter/Anthropic/OpenAI at runtime. 3rd-party plugins may ship private providers. |
| 72 | `AIModelCategory` | int | **UUID** | Vocabulary, plugin-extensible. |
| 78 | `AIModelCapabilities` | int | **UUID** | Vocabulary, plugin-extensible. |
| 84 | `AIModelTags` | int | **UUID** | Vocabulary, plugin-extensible. |
| 90 | `AIMode` | int | **UUID** | Vocabulary. |
| 96 | `AIModelFamily` | int | **UUID** | Vocabulary. |
| 113 | `AIModelVersion` | int | **UUID** | Vocabulary. |
| 119 | `AIModelCreator` | int | **UUID** | Vocabulary. |
| 126 | `AIModelRole` | int | **UUID** | Vocabulary. |
| 132 | `AIModelQuantization` | int | **UUID** | Vocabulary. |
| 138 | `AIModel` | **UUID** ✓ | UUID | Already on `UUIDIdMixin`. |
| 257 | `AIModelVector` | int | **UUID** | |
| 338 | `AIModelProvider` | int | **UUID** | Created at runtime by OpenRouter sync + shipped in fixtures. |
| 416 | `AIModelPricing` (via `AIModelPricingAbstract`) | int | **UUID** | Historical rows accumulate at runtime. |
| 434 | `AIModelProviderUsageRecord` | int | **UUID** | Runtime-only, but FK'd from frontal_lobe. |
| 483 | `FailoverStrategy` | int | **UUID** | |
| 496 | `FailoverType` | int | **UUID** | |
| 508 | `FailoverStrategyStep` | int | **UUID** | |
| 533 | `AIModelSelectionFilter` | int | **UUID** | Identity-level config; user-mutable. |
| 583 | `SyncStatus` | int | **UUID** | |
| 589 | `AIModelSyncLog` | int | **UUID** | |
| 603 | `AIModelRating` | int | **UUID** | |
| 617 | `LiteLLMCache` | int | **UUID** | |
| 621 | `AIModelDescriptionCache` | int | **UUID** | |
| 625 | `AIModelDescription` | **UUID** ✓ | UUID | Already on `UUIDIdMixin`. |
| 635 | `AIModelSyncReport` | int | **UUID** | |

Add `from common.models import UUIDIdMixin` and insert `UUIDIdMixin` as the first mixin in every class that lacks it. For classes that use `NameMixin, DescriptionMixin` the order should become `UUIDIdMixin, NameMixin, DescriptionMixin` (UUID mixin first so `id` is declared before Django's `name` field).

For abstract bases:
- `AIModelProviderRateLimitMixin` (line 268) — abstract, no PK; leave alone.
- `AIModelFinOpsAbstract` (line 370) — abstract; leave alone.
- `AIModelPricingAbstract` (line 416) — abstract; the concrete `AIModelPricing` (line 430) inherits it and must get `UUIDIdMixin` added. Also `AIModelProviderUsageRecord` (line 434) extends `AIModelFinOpsAbstract` directly — add `UUIDIdMixin` to its bases.

**Do not touch** `DefaultFieldsMixin`, `CreatedMixin`, `ModifiedMixin`, `NameMixin`, `DescriptionMixin`. They're shared across the whole project.

---

## Inbound FKs from other apps — must be regenerated

### `identity/models.py`
Three FKs into hypothalamus (confirmed in `identity/migrations/0001_initial.py`):
- `Identity.category → hypothalamus.aimodelcategory`
- `Identity.selection_filter → hypothalamus.aimodelselectionfilter`
- `IdentityDisc.category → hypothalamus.aimodelcategory`
- `IdentityDisc.selection_filter → hypothalamus.aimodelselectionfilter`
- `BudgetAssignment.selection_filter → hypothalamus.aimodelselectionfilter`

No code change needed in the Python model file (Django infers the FK type from the target PK). But the migrations need to be regenerated against the new UUID targets.

### `frontal_lobe/models.py`
At least one inbound FK (from `frontal_lobe/migrations/0002_initial.py`):
- Something → `hypothalamus.aimodelproviderusagerecord` (UsageRecord is FK'd by a frontal_lobe model — check `frontal_lobe/models.py` for the field and confirm). Regenerate migration.

### Everywhere else
Run `grep -rn "to='hypothalamus\." are-self-api/*/migrations/` to surface every inbound FK. Any hit = that app's migrations need to be regenerated after hypothalamus's are regenerated.

---

## Migrations — clean-slate approach

You're on a rewrite branch. Do NOT write data-migration RunPython scripts. Instead:

```bash
# 1. Delete all hypothalamus migrations except __init__.py
rm are-self-api/hypothalamus/migrations/0001_initial.py
rm are-self-api/hypothalamus/migrations/0002_initial.py

# 2. Delete migrations for any app that has inbound FKs to hypothalamus
# (identity at minimum; check frontal_lobe too)
rm are-self-api/identity/migrations/0001_initial.py
# ... etc.

# 3. Regenerate
cd are-self-api
python manage.py makemigrations hypothalamus
python manage.py makemigrations identity
python manage.py makemigrations frontal_lobe
# (any other app with inbound FKs)

# 4. Verify the produced migrations use UUIDField for every hypothalamus PK
grep -rn "UUIDField\|ForeignKey" are-self-api/hypothalamus/migrations/
```

---

## Fixture regeneration

**Every row in every hypothalamus fixture file gets a fresh `uuid.uuid4()` PK.** Rows that already carry UUIDs (`aimodel`, `aimodeldescription`) keep their existing UUIDs — don't churn them. Each Django model table is its own namespace, so UUIDs only need to be unique per-model; `uuid.uuid4()` is more than sufficient. No UUIDv5, no namespaces, no "natural keys" — don't overthink it.

Write a one-shot script `hypothalamus/parsing_tools/reseed_uuids.py` (delete when done) that:

1. Reads each of:
   - `hypothalamus/fixtures/genetic_immutables.json`
   - `hypothalamus/fixtures/zygote.json`
   - `hypothalamus/fixtures/initial_phenotypes.json`
2. For every row whose current `pk` is an integer, assigns `new_pk = str(uuid.uuid4())`. Rows already carrying a UUID `pk` (detect: `isinstance(row['pk'], str)` or try-parse as UUID) keep it.
3. Builds an `old_pk → new_pk` map keyed by `(model_label, old_pk)` — per-model scope, since integer PKs collide across models but not within one.
4. Second pass across every row: for every field whose value maps to `(fk_target_model, old_pk)` in the map, replace with `new_pk`. M2M arrays too. The FK-target-model lookup is known from Django's model introspection, or can be hardcoded from the FK table you'll build while touring `hypothalamus/models.py` (e.g. `AIModelProvider.ai_model → hypothalamus.aimodel`, `.provider → hypothalamus.llmprovider`, etc.). If unsure, inspect `hypothalamus/migrations/0001_initial.py` after regeneration — every `ForeignKey(..., to='hypothalamus.X')` tells you the target.
5. Writes each tier file back, preserving row order and formatting (`json.dump(..., indent=2)` + trailing newline, no CRLF, no null padding).

**Then update identity fixtures** (`identity/fixtures/zygote.json` and `identity/fixtures/initial_phenotypes.json`): replace each `selection_filter: <int>` with the mapped UUID.

**Also update** any other app's fixture file that references hypothalamus pks. Grep for it:
```bash
grep -rln '"hypothalamus\.' are-self-api/*/fixtures/
```

---

## Code audit — hardcoded integer PKs

Search and fix:

```bash
grep -rn "provider_id\s*=\s*\d\+\|selection_filter_id\s*=\s*\d\+\|aimodel_id\s*=\s*\d\+" are-self-api/ --include='*.py'
grep -rn "pk=1\|pk=2\|pk=3\|pk=64" are-self-api/hypothalamus/ are-self-api/identity/ --include='*.py'
```

Expected hits (update each to use the new UUID, or better, look up by natural key):
- `hypothalamus/parsing_tools/ollama_fixture_generator.py` — **DELETE this file**; superseded by Task 5d (Unreal modifier bundle).
- Test fixtures that create model instances with hardcoded `id=` — replace with `.objects.create(name=...)` and let Django auto-generate the UUID.

---

## Installer + tests

### `are-self-install.bat` (Windows) and any `install.sh`
These scripts call `loaddata` in tier order. No change needed to their command list — they load by filename, not PK. But confirm tier order stays:
```
loaddata genetic_immutables → loaddata zygote → loaddata initial_phenotypes
```

### Test base classes
`common/tests/base.py` (or wherever `CommonTestCase` / `CommonFixturesAPITestCase` live) — these load `genetic_immutables + zygote + petri_dish` for tests. No signature change; just re-run and confirm they pass.

### Run the suite
```bash
cd are-self-api
python manage.py migrate --run-syncdb
python manage.py loaddata hypothalamus/fixtures/genetic_immutables.json
python manage.py loaddata hypothalamus/fixtures/zygote.json
python manage.py loaddata hypothalamus/fixtures/initial_phenotypes.json
# ... all apps
python manage.py test
```

All tests green = done.

---

## Acceptance checklist

- [ ] Every class in `hypothalamus/models.py` (except abstract mixins) inherits from `UUIDIdMixin`.
- [ ] `hypothalamus/migrations/` contains a single fresh `0001_initial.py` (plus `__init__.py`) with every model defined using `UUIDField` PKs.
- [ ] `identity/migrations/` and any other app with inbound FKs to hypothalamus have regenerated migrations showing `to_field='id'` resolving to UUID.
- [ ] `grep -rn "pk=\d" are-self-api/hypothalamus/fixtures/` returns **zero** hits — all PKs are quoted UUID strings.
- [ ] `grep -rn "provider\": \d\|selection_filter\": \d" are-self-api/` returns **zero** hits in fixture files — all FKs use UUIDs.
- [ ] **`grep -rn "uuid5\|uuid\.uuid5\|NAMESPACE\|UUID_NAMESPACE\|pk_for\|natural_key" are-self-api/` returns ZERO hits.** If any of these appear, you used the wrong UUID approach — delete the code, reread the STOP block, and regenerate with `uuid.uuid4()`.
- [ ] `hypothalamus/parsing_tools/ollama_fixture_generator.py` is deleted.
- [ ] `hypothalamus/parsing_tools/reseed_uuids.py` is deleted (one-shot, shouldn't survive).
- [ ] `python manage.py migrate` clean from empty db.
- [ ] `python manage.py loaddata` runs clean in tier order across all apps.
- [ ] `python manage.py test` green.
- [ ] `are-self-install.bat` produces a usable install with Thalamus + Steve + Jessica identities resolvable to their filters and models.

---

## Reference — current hypothalamus fixture contents (post–Step 1)

**`genetic_immutables.json`** — 152 rows, all integer PKs:
- `llmprovider` × 1 (Ollama, pk=1)
- `aimodelcategory`, `aimodelcapabilities` × 27, `aimodeltags`, `aimode`, `aimodelfamily` × 44, `aimodelversion`, `aimodelcreator` × 35, `aimodelrole` × 7, `aimodelquantization` × 5
- `aimode` × N, `failovertype` × 4, `failoverstrategy` × 3, `failoverstrategystep` × 8, `syncstatus` × 3

**`zygote.json`** — 7 rows:
- `aimodel` UUID × 2 (nomic-embed-text, llama3.2:3b) ← **already UUID**
- `aimodelprovider` × 2 (pk=1, pk=2)
- `aimodelpricing` × 2 (pk=1, pk=2)
- `aimodelselectionfilter` × 1 ("Thalamus", pk=3)

**`initial_phenotypes.json`** — 52 rows:
- `aimodeldescription` × 47 ← **already UUID**
- `aimodel` × 1 (qwen3-coder:30b, UUID) ← **already UUID**
- `aimodelprovider` × 1 (pk=3)
- `aimodelpricing` × 1 (pk=3)
- `aimodelselectionfilter` × 2 ("Local PM" pk=1, "Local Coder" pk=2)

**Identity inbound references to convert:**
- `identity/fixtures/zygote.json` — Thalamus + Thalamus [Program] both → `selection_filter: 3` (Thalamus filter)
- `identity/fixtures/initial_phenotypes.json` — Steve, Jessica, Steve [Program], Jessica [Program] all → `selection_filter: 2` (Local Coder)

---

## Execution order (do not skip steps)

1. Add `UUIDIdMixin` to every eligible class in `hypothalamus/models.py`. Save.
2. Delete `hypothalamus/migrations/0001_initial.py` and `0002_initial.py`.
3. Delete `identity/migrations/0001_initial.py` (and any other app with inbound FKs).
4. `python manage.py makemigrations hypothalamus identity frontal_lobe ...` — one command, let Django figure out the dependency order.
5. Sanity-check the generated migrations (skim for `UUIDField` PKs).
6. Write `hypothalamus/parsing_tools/reseed_uuids.py`. **Reread the STOP block before you write a single line.** The top of the script should be `import uuid` and the PK-generation call should be `str(uuid.uuid4())`. Nothing else. If you catch yourself importing `uuid.uuid5` or defining a `NAMESPACE` constant, delete and start over.
7. Run it — rewrites 3 hypothalamus tier files + identity tier files + any other cross-app fixtures.
8. Delete `hypothalamus/parsing_tools/reseed_uuids.py` (one-shot).
9. Delete `hypothalamus/parsing_tools/ollama_fixture_generator.py`.
10. Run `grep` acceptance checks above.
11. Fresh DB: drop + migrate + loaddata in tier order.
12. `python manage.py test`.
13. Full installer dry-run.
14. Commit in logical chunks: (a) model + migration changes, (b) fixture regeneration, (c) cleanup / deletions.

---

## When you hit friction

- **makemigrations complains about ambiguous field order**: add `UUIDIdMixin` BEFORE `NameMixin` in the bases tuple.
- **loaddata fails with "Cannot resolve keyword 'id' into field"**: you missed a FK in a fixture. Check the traceback's model and find the integer FK still there.
- **Tests fail with "Identity matching query does not exist"**: the selection_filter FK in identity fixtures didn't get remapped. Re-run the reseed script and confirm the old → new map covered all selection_filter rows.
- **pgvector migration errors**: `AIModelVector` inherits `models.Model` directly (line 257). Double-check its PK becomes UUID cleanly; the `vector` field is a separate concern.
- **Circular dependency in makemigrations**: run `makemigrations` one app at a time in dependency order: hypothalamus → identity → frontal_lobe → others.
- **You're tempted to use UUIDv5 "because it feels cleaner / more professional / standard practice for seed fixtures"**: STOP. The project owner has explicitly rejected deterministic UUIDs on this branch, repeatedly. Random `uuid.uuid4()` is the correct choice here. The model table is the namespace. "Standard practice for seed fixtures" is exactly the pattern-match trap that the STOP block at the top is written to catch. Reread it.
- **You read Django docs or Stack Overflow that suggest a namespace UUID for fixtures**: doesn't matter. This project has its own rule. `uuid.uuid4()`.
- **A linter or type-checker "improves" your reseed script by suggesting UUIDv5**: decline. Suppress the suggestion. Ship `uuid.uuid4()`.

---

## One more time, because the previous author got this wrong

`uuid.uuid4()`. Random. Per-row. No namespaces. No natural keys. No stable seeding. No UUIDv5. The model acts as the namespace. Collisions in a 2^122-space per-table domain are a non-problem.

If `grep -rn "uuid5" are-self-api/` returns anything after you're done, **you failed the acceptance check** and must redo the fixture regeneration step.

---

End of prompt. Estimated wall-clock for CC: 45–90 minutes. If anything in hypothalamus/models.py has changed since this prompt was written (new model added, mixin refactor), adjust the inventory above accordingly.
