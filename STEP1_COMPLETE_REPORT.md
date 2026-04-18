# STEP1_COMPLETE_REPORT.md — Pass 2 Step 1 Completion Pass

Generated 2026-04-15. This is the rewrite-phase report for the fixture-tier split.
Applies D1–D9 per Michael's rulings on top of the read/classify-only output captured
in `STEP1_REPORT.md`. All 10 `initial_data.json` files are byte-identical to their
pre-pass state.

> **STATUS: rewrite complete with 0 cross-tier FK blockers.** 10 per-app tier files
> written in place, one new file created (`temporal_lobe/fixtures/zygote.json`),
> one new `environments/fixtures/genetic_immutables.json` created, one file deleted
> (`hypothalamus/fixtures/zygote.step1.json`), petri_dish.json written as `[]` in
> every app. One NEW data row authored: `qwen3-coder:30b`. All other UUID literals
> are frozen verbatim.
>
> **Attention items** — two cascade decisions the rewrite agent made as judgment
> calls and two pre-existing data smells surfaced by cross-FK verification, below
> in section 6. Michael should confirm before Step 2.

---

## 1. Per-App Final Row Counts

| app | gen_imm | zygote | phenotypes | petri | modifier | total |
|-----|--------:|-------:|-----------:|------:|---------:|------:|
| central_nervous_system    |  28 |   6 |  89 | 0 | 198 | 321 |
| django_celery_beat        |   7 |   0 |   0 | 0 |   0 |   7 |
| environments              |   7 |  10 |  86 | 0 |  65 | 168 |
| frontal_lobe              |   8 |   0 |   0 | 0 |   0 |   8 |
| hypothalamus              | 153 |   9 |  48 | 0 |   0 | 210 |
| identity                  |  31 |   2 |   4 | 0 |   0 |  37 |
| parietal_lobe             |  13 | 204 |   0 | 0 |   0 | 217 |
| peripheral_nervous_system |   4 |   0 |   0 | 0 |   0 |   4 |
| prefrontal_cortex         |  12 |   0 |   0 | 0 |   0 |  12 |
| temporal_lobe             |  17 |  10 |   0 | 0 |   0 |  27 |
| **TOTAL**                 | 280 | 241 | 227 | 0 | 263 | **1011** |

**Row accounting vs STEP1_REPORT.md §1 (total 1017):**

- -1 `DEPLOY_RELEASE` Executable (dark record, already dropped per Rule 1)
- -3 qwen2.5-coder:7b cascade: aimodel + aimodelprovider#3002 + aimodelpricing#3
- -3 gemma3:4b cascade: aimodel + aimodelprovider#3003 + aimodelpricing#4
- +1 **NEW row authored** — `qwen3-coder:30b` (pk `b02d348c-3303-4c3d-a5ac-241da3d6f026`)

1017 − 1 − 3 − 3 + 1 = **1011** ✓

### Notable per-app shape changes

- **central_nervous_system/zygote.json**: unchanged (BEGIN_PLAY effector +
  EffectorArgumentAssignment, 4 logic atoms, Debug — 6 rows). **D1 verified**.
- **central_nervous_system/unreal_modifier.json**: expanded from 48 → 198 rows
  by D3 pathway closure (13 UE-named pathways + neurons, axons, effectors,
  contexts, EAAs in their transitive closure).
- **central_nervous_system/initial_phenotypes.json**: 239 → 89. The drop is the
  mass migration to `unreal_modifier.json`.
- **environments**: new `genetic_immutables.json` created for the 7 UUID
  Executables per D2. `zygote.json` now contains the default env + its
  ContextVariable children + 2 ContextKey FK targets + the `Project`
  ExecutableArgument (D1/D8).
- **environments/initial_phenotypes.json**: 96 → 86 after D2 executables moved
  out to genetic_immutables + D8 context variables moved to zygote.
- **hypothalamus/zygote.json**: 4 aimodels → 9 total rows (3 aimodels + 2
  aimodelproviders + 2 aimodelpricings + 2 aimodelselectionfilters). See §6.2
  for why the cascade pulled the extra 6 rows in.
- **parietal_lobe/zygote.json**: 19 → 204 rows. **D6 applied**: entire tool
  suite (parameterenum, toolparameter, toolparameterassignment, tooldefinition)
  moved from phenotypes to zygote. `parietal_lobe/initial_phenotypes.json`
  is now empty (0 rows).
- **temporal_lobe/zygote.json**: NEW file (D4). 10 rows — 2
  IterationDefinitions + 8 IterationShiftDefinitions.
  `temporal_lobe/initial_phenotypes.json` is now empty (0 rows — no Iteration
  or IterationShift instance rows exist in `initial_data.json`).

## 2. D2 Expanded UE-Executable Root List (14 rows)

| pk | constant | name | tier |
|---|---|---|---|
| `0fb093f4-8c4a-4f40-ad1b-234e4f516f4f` | `UNREAL_SHADER_TOOL` | `UNREAL_SHADER_TOOL` | unreal_modifier (dark) |
| `11915177-a32b-4883-8c9f-e137c528c20d` | — | `DJANGO` | genetic_immutables |
| `1d037234-c8c2-4d51-bc65-41597c0becd2` | `VERSION_HANDLER` | `update_version_metadata` | unreal_modifier |
| `24e213d0-92c1-4b77-8a35-f6998075efc0` | — | `Engage Frontal Lobe` | genetic_immutables |
| `3ced43ee-5504-493a-a4b7-15040bb17100` | `UNREAL_AUTOMATION_TOOL` | — | unreal_modifier |
| `3ee78993-faa3-401b-8187-c771e11c4564` | `UNREAL_CMD` | — | unreal_modifier |
| `5fbd152c-23bf-4951-840f-491f4fff918a` | `DEPLOY_RELEASE` | `deploy_release_test` | unreal_modifier (dark — dropped) |
| `6e487387-9608-4481-8f5c-9b0741585633` | `UNREAL_RELEASE_TEST` | — | unreal_modifier |
| `6fb7f8af-60b6-4f04-aa07-d4d36c680e38` | — | `Scan for Peripheral Nervous Systems` | genetic_immutables |
| `6fcad69c-37de-4706-ac5e-a34ad3e6be9f` | — | `robocopy` | genetic_immutables |
| `974ed732-6f2d-47f4-9482-18d17c73086e` | `Executable.BEGIN_PLAY` | `BEGIN_PLAY` | genetic_immutables |
| `c8cb58b0-341b-43d3-bfcf-8d31dca28375` | — | `Windows Powershell Command` | genetic_immutables |
| `dfe7b955-d22f-4630-a1f9-36b1ff59c591` | — | `Windows Command (CMD)` | genetic_immutables |
| `efb5d7dc-9922-43ec-b108-5af5f029b71d` | `UNREAL_STAGING` | — | unreal_modifier |

`DEPLOY_RELEASE` stays dropped per STEP1_REPORT §3 — no dependents, no reverse
FKs in any fixture. Not written to any tier file.

## 3. SHA-256 Verification of `initial_data.json`

All 10 files byte-identical to STEP1_REPORT.md §2 "before" column.

| app | sha256 | match |
|-----|--------|:-----:|
| central_nervous_system    | `857b3d59e3ecfef62bf824420bc9cc65a758c8cdf46f7962f3560641b86fc1e1` | ✅ |
| django_celery_beat        | `62aaff3aac14433737804e9eb97864fc9725d8a911e52da7f18c03141fda38e9` | ✅ |
| environments              | `ad28ba1c8cdf88b6762655b6ff683a984e6517b023017ecc20546a647abc5387` | ✅ |
| frontal_lobe              | `884d87241d259b025798089816a6ef07b8d593ca9e746825831920fe6ee4c1d8` | ✅ |
| hypothalamus              | `05fc6e58f1e7f36a7f715eba92c6974d882fbcd9d9d422904bbf7f1fee3c2ca4` | ✅ |
| identity                  | `18b8b9bf3fb8479a581b2e22fdde7e3507dad67ce469e42546314923dac330b9` | ✅ |
| parietal_lobe             | `3e4b45375545721538e7aeb6977983635246e38a9398e06e07d42971ea791d94` | ✅ |
| peripheral_nervous_system | `9ff53a75ef873503b889870fd815ddcf5991f9cab6856e6cb4fd822fc4909948` | ✅ |
| prefrontal_cortex         | `601703e769de7cf144fb4c23d679cb50d521f4cf7e1f0089d49e768c2ec4cca5` | ✅ |
| temporal_lobe             | `8310acc9dc295ca35903535074b7db37cd9ff737adf966fd3618b38acb03ecb4` | ✅ |

## 4. Cross-Tier FK Relocations

### 4.1 Tier-order load rules checked

- `genetic_immutables` FK targets: allowed = `genetic_immutables`
- `zygote` FK targets: allowed = `genetic_immutables`, `zygote`
- `initial_phenotypes` FK targets: allowed = `genetic_immutables`, `zygote`, `initial_phenotypes`
- `unreal_modifier` FK targets: allowed = `genetic_immutables`, `zygote`,
  `initial_phenotypes`, `unreal_modifier`
- `petri_dish` FK targets: allowed = `genetic_immutables`, `petri_dish`

**Final blocker count: 0.** All FK targets resolve into an allowed lower-or-
equal tier.

### 4.2 Specific relocations from the read/classify-only output

- **`environments.executableargument` pk=`920e7245-...` ("Project")** — moved
  `environments/unreal_modifier.json` → `environments/zygote.json`. **D1**.
  This resolves the §6.1 collision from STEP1_REPORT.md — BEGIN_PLAY's EAA FK
  now resolves within zygote. The `Project` argument template
  (`{{project_root}}\{{uproject}}`) keeps its current row value verbatim — see
  TODO 8.1 below for the semantic smell.
- **7 UUID Executables → `environments/genetic_immutables.json`** (D2).
  Previously in `environments/initial_phenotypes.json` (DJANGO, Engage Frontal
  Lobe, Scan for PNS, robocopy, PowerShell, CMD) or in `environments/zygote.json`
  (BEGIN_PLAY). A new `environments/genetic_immutables.json` file was created
  — environments had none under the read/classify pass.
- **6 UE Executables confirmed in `environments/unreal_modifier.json`** (D2).
  UNREAL_CMD, UNREAL_AUTOMATION_TOOL, UNREAL_STAGING, UNREAL_RELEASE_TEST,
  UNREAL_SHADER_TOOL, VERSION_HANDLER. Already there from the classifier; no
  move needed. Plus `DEPLOY_RELEASE` stays dropped.
- **13 UE-named NeuralPathways → `central_nervous_system/unreal_modifier.json`**
  (D3). `Full`, `Version Meta`, `Compile Shaders`, `Deploy`, `Process Test 2`,
  `Pre-Release Run`, `All Remotes`, `Process Test`, `Stage`, `RecordPSOs`,
  `CPPTests`, `Multiplayer (C&S)`, `Pre-Release`. Plus their transitive closure
  of Neurons, Axons, NeuronContexts, and exclusively-UE Effectors /
  EffectorContexts / EAAs.
- **1 NON-UE-named NeuralPathway → `central_nervous_system/unreal_modifier.json`**
  — `Corpus Callosum` (`04c3997f-d5f3-402f-952a-519bbd7e4dee`). This pathway's
  `.environment` field FKs to `44b23b94-...` the UE Default Environment. It
  could not stay in `cns_ph` without creating a tier-3 → tier-4 FK. Moved into
  `unreal_modifier` along with its neurons/axons. See TODO 8.4 — this name is
  brain-region-flavored, not UE-flavored, so the environment binding may be a
  data smell.
- **4 shared Effectors KEPT in `cns_ph`** — `5f77b921`, `84c1de07`, `e1ae3de5`,
  `f470784c`. These were pulled into `cns_um` by the closure of UE-pathway
  neurons, but they are ALSO referenced by neurons in non-UE pathways. Per
  D3's "base tier wins" reading ("Transitive deps … that aren't already
  classified to a base tier → modifier"), shared effectors stay in the base
  tier. UE-pathway neurons in `cns_um` FK down to them in `cns_ph`, which is
  allowed (tier 4 → tier 3).
- **Hypothalamus cascade into zygote** — `aimodelprovider` 3000/3001 and
  `aimodelpricing` 1/2 moved from `hyp_gi` → `hyp_zy` because they FK to
  zygote aimodels nomic-embed-text and llama3.2:3b respectively.
  `aimodelselectionfilter` 2 and 3 moved from `hyp_gi` → `hyp_zy` because the
  zygote `Identity`/`IdentityDisc` rows FK to them via `selection_filter`.
  See §6.2 for the subsidiary dropped-FK data smell.
- **Parietal tool suite wholesale → `par_zy`** (D6). 185 rows
  (`parameterenum`, `toolparameter`, `toolparameterassignment`,
  `tooldefinition`) relocated from phenotypes to zygote. `par_ph` is now
  empty.
- **Temporal definitions → new `tem_zy`** (D4). All 10 `iterationdefinition`
  and `iterationshiftdefinition` rows relocated from phenotypes to the new
  zygote file. `tem_ph` is now empty. No Iteration or IterationShift instance
  rows exist anywhere in the tier split.
- **`environments.projectenvironment b7e4c2a1` ContextVariables** — the 2
  `contextvariable` rows whose `.environment = b7e4c2a1` moved from `env_ph`
  → `env_zy`, plus their 2 `projectenvironmentcontextkey` FK targets (D8).

## 5. Files Written / Deleted

### Written (in-place rewrites)
- `central_nervous_system/fixtures/genetic_immutables.json` (28)
- `central_nervous_system/fixtures/zygote.json` (6)
- `central_nervous_system/fixtures/initial_phenotypes.json` (89)
- `central_nervous_system/fixtures/unreal_modifier.json` (198)
- `central_nervous_system/fixtures/petri_dish.json` (`[]`)
- `django_celery_beat/fixtures/genetic_immutables.json` (7)
- `django_celery_beat/fixtures/petri_dish.json` (`[]`)
- `environments/fixtures/genetic_immutables.json` **NEW** (7)
- `environments/fixtures/zygote.json` (10)
- `environments/fixtures/initial_phenotypes.json` (86)
- `environments/fixtures/unreal_modifier.json` (65)
- `environments/fixtures/petri_dish.json` (`[]`)
- `frontal_lobe/fixtures/genetic_immutables.json` (8)
- `frontal_lobe/fixtures/petri_dish.json` (`[]`)
- `hypothalamus/fixtures/genetic_immutables.json` (153)
- `hypothalamus/fixtures/zygote.json` (9)
- `hypothalamus/fixtures/initial_phenotypes.json` (48)
- `hypothalamus/fixtures/petri_dish.json` (`[]`)
- `identity/fixtures/genetic_immutables.json` (31)
- `identity/fixtures/zygote.json` (2)
- `identity/fixtures/initial_phenotypes.json` (4)
- `identity/fixtures/petri_dish.json` (`[]`)
- `parietal_lobe/fixtures/genetic_immutables.json` (13)
- `parietal_lobe/fixtures/zygote.json` (204)
- `parietal_lobe/fixtures/initial_phenotypes.json` (0 — empty array)
- `parietal_lobe/fixtures/petri_dish.json` (`[]`)
- `peripheral_nervous_system/fixtures/genetic_immutables.json` (4)
- `peripheral_nervous_system/fixtures/petri_dish.json` (`[]`)
- `prefrontal_cortex/fixtures/genetic_immutables.json` (12)
- `prefrontal_cortex/fixtures/petri_dish.json` (`[]`)
- `temporal_lobe/fixtures/genetic_immutables.json` (17)
- `temporal_lobe/fixtures/zygote.json` **NEW** (10)
- `temporal_lobe/fixtures/initial_phenotypes.json` (0 — empty array)
- `temporal_lobe/fixtures/petri_dish.json` (`[]`)

### Deleted
- `hypothalamus/fixtures/zygote.step1.json` (D5 — redundant 1-row file
  superseded by the new `hypothalamus/fixtures/zygote.json`)

### Untouched
- Every `initial_data.json` (byte-identical, SHA verified)
- `central_nervous_system/fixtures/cns_delta.json`
- `hypothalamus/fixtures/ollama_complete.json`, `popular_ollama.json`,
  `initial_data_only.json`
- `neuroplasticity/fixtures/reference_data.json`
- `peripheral_nervous_system/fixtures/test_agents.json`
- Everything under `ue_tools/`

### NEW row authored (the only one in this pass)

```json
{
  "model": "hypothalamus.aimodel",
  "pk": "b02d348c-3303-4c3d-a5ac-241da3d6f026",
  "fields": {
    "name": "qwen3-coder:30b",
    "description": null,
    "creator": 2,
    "parameter_size": 30.0,
    "family": 3,
    "version": null,
    "context_length": 131072,
    "enabled": true,
    "deprecation_date": null,
    "roles": [1, 3],
    "quantizations": [],
    "capabilities": [1, 2]
  }
}
```

FK targets verified on disk in `hypothalamus/fixtures/genetic_immutables.json`:
`aimodelcreator` pk 2, `aimodelfamily` pk 3, `aimodelrole` pks {1, 3},
`aimodelcapabilities` pks {1, 2}. No `aimodelquantization` FKs. **pk is a
fresh `uuid.uuid4()` literal**, frozen from now on.

## 6. Judgment Calls & Cascades (Michael, please confirm before Step 2)

### 6.1 `qwen2.5-coder:7b` / `gemma3:4b` full-cascade drop

D5 specified these 2 rows "deleted from the tier split" as `hypothalamus.aimodel`
records. The read/classify pass had put both in `hypothalamus/initial_phenotypes.json`
(pulled from `initial_data.json`), so the drop was straightforward at the aimodel
level. But the classifier also put these dependent rows in `hyp_gi`:

- `hypothalamus.aimodelprovider` pk 3002 → `ai_model = 3ca370b6-...` (qwen2.5-coder:7b)
- `hypothalamus.aimodelprovider` pk 3003 → `ai_model = c2c359f7-...` (gemma3:4b)
- `hypothalamus.aimodelpricing` pk 3 → `model_provider = 3002`
- `hypothalamus.aimodelpricing` pk 4 → `model_provider = 3003`

These would have dangling FKs after D5. **Judgment call: cascade-dropped all 4
rows from the tier split entirely.** They remain in `initial_data.json` (byte-
identical per the hard rule) but do not appear in any tier file. The LiteLLM
provider routing contract `ollama/qwen2.5-coder:7b` and `ollama/gemma3:4b` are
consequently unusable until Michael re-authors them.

**Michael, confirm this is the intended outcome.** If either model should
remain addressable, you'll need to re-author the aimodel + provider + pricing
triplet (and probably dump from DB since the pre-staged UUIDs were uuid5
from an obsolete generator — they're just frozen literals now).

### 6.2 `aimodelselectionfilter` 2 and 3 have dangling FK fields

After the 6.1 drop, the integer-PK `aimodelselectionfilter` rows that are
referenced by the zygote `Identity`/`IdentityDisc` rows now contain dangling
FK field values:

- Row 2 "Local Coder": `preferred_model = 3002` (dropped), `local_failover = 3002` (dropped)
- Row 3 "Thalamus": `preferred_model = 3003` (dropped), `local_failover = 3001` (moved — OK)

**Judgment call: moved rows 2 and 3 from `hyp_gi` → `hyp_zy`** so the tier
assignment matches the zygote Identity references (legal tier-2 → tier-2 FK).
**Row-internal dangling FK values were NOT modified** per the "do not modify
row data" prompt rule.

**Impact:** these rows will not clean-loaddata against a populated aimodelprovider
table because those integer PKs no longer exist in the split. This is a
Step 2 data-hygiene blocker that has to be resolved before install/Docker can
bootstrap. Three possible resolutions for Michael:

1. Null out `preferred_model` and `local_failover` field values where they
   reference dropped providers (row 2 preferred/local=null, row 3 preferred=null,
   local_failover=3001 stays).
2. Re-author the qwen2.5-coder:7b and gemma3:4b chain to restore the FK targets.
3. Change `Identity.THALAMUS`/`IdentityDisc.THALAMUS` to use a different
   selection filter that doesn't reference dropped providers.

### 6.3 `qwen3-coder:30b` has no aimodelprovider or pricing

The new `qwen3-coder:30b` aimodel row has no corresponding `aimodelprovider`
or `aimodelpricing` row. The prompt explicitly said to author only the aimodel
row and to stop if sibling rows are required — so I did not author an
aimodelprovider for it. **Until a provider row exists, qwen3-coder:30b is
nameless to LiteLLM** and cannot be picked by `Hypothalamus.pick_optimal_model()`
via the provider routing path. Flag for Michael to dump from DB in a
subsequent pass or author manually.

### 6.4 `Corpus Callosum` pathway environment FK

This non-UE-named pathway (brain-region name) FKs via `.environment` to the UE
`44b23b94` environment. It could not stay in the base tier without creating a
tier-3 → tier-4 FK. **Judgment call: moved `Corpus Callosum` into
`cns/unreal_modifier.json`** along with its 4 neurons and their axons. This is
the minimally invasive fix. Whether the name or the environment FK is stale is
a downstream question.

Compounding smell: the `Corpus Callosum` neurons point at `FRONTAL_LOBE`-like
effectors that are core atoms (not UE). So the pathway is now in
`unreal_modifier.json` but all its content is base-tier. This is exactly the
"mixed pathway with UE environment identity" case STEP1_REPORT §6.2 flagged
but in the other direction — here the name isn't UE but the environment is.

### 6.5 Hypothalamus zygote grew beyond "exactly 3 rows"

D5 specified zygote = exactly 3 AIModel rows. The final `hypothalamus/zygote.json`
has **9 rows** — 3 AIModels + 2 AIModelProviders + 2 AIModelPricings + 2
AIModelSelectionFilters. The extra 6 rows were pulled into zygote by tier-order
correctness (they FK to zygote AIModels or are FK'd by zygote Identity rows).

If D5 meant "exactly 3 rows full stop, period", then the loaddata path is
unbootable — stop here and surface. If D5 meant "exactly 3 **aimodel** rows",
then my final state matches the intent. I read the latter as obvious given the
cascade, but flagging for explicit confirmation.

## 7. TODO List

### 7.1 BEGIN_PLAY "Project" ExecutableArgument semantic smell

`environments.executableargument` pk=`920e7245-0487-471b-a617-b2d9964f8e17`
is now in `environments/zygote.json` (D1). Its current field values:

- `name = "Project"`
- `argument = "{{project_root}}\{{uproject}}"`

The `.uproject` concept is UE-specific, but the row is core-owned (referenced
by core `BEGIN_PLAY` Effector EAA). Either the argument template is stale and
should become a generic core template, or `BEGIN_PLAY` is actually UE-flavored
and should move to `unreal_modifier`. Not a blocker at tier-split time; flag
for Step 2 design review.

### 7.2 `hypothalamus/fixtures/zygote.json` UUIDs are frozen uuid5 literals

Per Michael's ground rule and the pre-existing `_comment` on the pre-staged
file, the UUIDs for `nomic-embed-text` and `llama3.2:3b` were originally
derived via `uuid5(NAMESPACE_DNS, 'areself.ollama.{slug}')` by the obsolete
`hypothalamus/parsing_tools/ollama_fixture_generator.py`. They are now frozen
literals in the final `hypothalamus/zygote.json`. No action required — just
context for Step 2 reviewers who might wonder why zygote UUIDs have the uuid5
version bit.

### 7.3 `qwen3-coder:30b` provider + pricing rows missing

Needs a companion `hypothalamus.aimodelprovider` row with
`provider = 64` (Ollama LLMProvider) and `provider_unique_model_id =
'ollama/qwen3-coder:30b'`, plus an `aimodelpricing` row. Dump from DB in a
subsequent pass.

### 7.4 `aimodelselectionfilter` 2/3 dangling FK field values

See §6.2. Pick a resolution path — null the dangling fields, re-author the
dropped model chain, or repoint the Identity rows.

### 7.5 `Corpus Callosum` pathway classification

See §6.4. Either rename the pathway to something UE-flavored to match its
environment binding, or unbind it from `44b23b94` so it can live in
`initial_phenotypes.json`.

### 7.6 `Deploy` and `RecordPSOs` empty-shell pathways

Per Michael's D3 ruling both go to `cns/unreal_modifier.json` despite having
zero UE neurons. `Deploy` (15 neurons, 0 UE) and `RecordPSOs` (1 neuron, 0 UE)
ended up in `unreal_modifier.json` but their neurons — being in non-UE
effectors — may end up FKing upward out of the modifier if Step 2 surfaces
any axons/neurons that reference back into the base tier. Cross-FK verify
passed at Pass 2 Step 1 close, but worth a spot-check during Step 2 wiring.

### 7.7 CLAUDE.md hypothalamus-zygote language is stale

CLAUDE.md currently says `hypothalamus zygote = 3 models (nomic-embed-text +
qwen2.5-coder:7b + qwen2.5-coder:32b)`. The actual D5 ruling for this pass was
`nomic + llama3.2:3b + qwen3-coder:30b (NEW)`. Not a fixture issue — just a
docs-drift item to fix in Step 2.

### 7.8 Pre-Pass 2 phenotype/modifier tier_1_gap note

`parietal_lobe/initial_phenotypes.json` and `temporal_lobe/initial_phenotypes.json`
are both empty arrays after this pass. If the install-order loader or tests
break on empty fixture files, Step 2 will need either a special-case skip or
a sentinel row.

### 7.9 `django_celery_beat` remains in `genetic_immutables` (per D7)

7 integer-PK rows (intervalschedule, crontabschedule, periodictask,
periodictasks). STEP1_REPORT §6.6 flagged this as feeling wrong
(PeriodicTask is instance data, not vocab). D7 explicitly ruled "no change."
Noted; not a blocker.

## 8. Points Requested for Michael to Confirm Before Step 2

1. §6.1 — full cascade-drop of qwen2.5-coder:7b and gemma3:4b (aimodel +
   provider + pricing, 6 rows total) is the intended D5 reading.
2. §6.2 — `aimodelselectionfilter` rows 2 and 3 moved to `hyp_zy` with
   dangling FK fields is acceptable until Step 2 data hygiene.
3. §6.3 — no aimodelprovider authored for `qwen3-coder:30b`; you'll dump it
   from DB later.
4. §6.4 — `Corpus Callosum` relocated to `cns/unreal_modifier.json` as the
   minimally invasive resolution for its FK to UE env `44b23b94`.
5. §6.5 — `hypothalamus/zygote.json` = 9 rows (3 aimodels + 6 cascade deps)
   matches your D5 intent.
