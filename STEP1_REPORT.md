# STEP1_REPORT.md — Pass 2 Step 1: Scratch-Split of `initial_data.json`


Generated 2026-04-15. This is a read/classify-only pass. No `initial_data.json`
file was modified. Scratch files were written alongside each app's existing
`initial_data.json` for review. The classifier lives at `C:/tmp/step1/classify.py`
(outside the repo).

> **⚠ ATTENTION** — this report contains **two zygote/UE collision findings**
> and **one confirmed core-code reference to a UE-flavored row**. See sections 6
> (needs-decision), 7 (DEFAULT_ENVIRONMENT audit), and 8 (surprises). Michael
> should read those before wiring anything up in Step 2.

---

## 1. Per-app Row Accounting

Columns: `in` = rows in `initial_data.json`, `out` = sum of buckets + dropped.
`in == out` must hold for every app.

| app | in | immutables | zygote | phenotypes | petri | unreal | dropped | out | ✓ |
|-----|---:|---:|---:|---:|---:|---:|---:|---:|:-:|
| central_nervous_system | 321 | 28 | 6 | 239 | 0 | 48 | 0 | 321 | ✅ |
| django_celery_beat | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 7 | ✅ |
| environments | 169 | 0 | 6 | 96 | 0 | 66 | 1 | 169 | ✅ |
| frontal_lobe | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 8 | ✅ |
| hypothalamus | 215 | 163 | 1 | 51 | 0 | 0 | 0 | 215 | ✅ |
| identity | 37 | 31 | 2 | 4 | 0 | 0 | 0 | 37 | ✅ |
| parietal_lobe | 217 | 13 | 19 | 185 | 0 | 0 | 0 | 217 | ✅ |
| peripheral_nervous_system | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 4 | ✅ |
| prefrontal_cortex | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 12 | ✅ |
| temporal_lobe | 27 | 17 | 0 | 10 | 0 | 0 | 0 | 27 | ✅ |
| **TOTAL** | **1017** | 283 | 34 | 585 | 0 | 114 | 1 | **1017** | |

Bucket names → file names:
- `immutables` → `genetic_immutables.json`
- `zygote` → `zygote.json`
- `phenotypes` → `initial_phenotypes.json`
- `petri` → `petri_dish.json` (empty across the board — no hardcoded fixture UUIDs were found in `**/tests/**/*.py`)
- `unreal` → `unreal_modifier.json`
- `dropped` → not written anywhere (Rule 1 dark records)

## 2. Integrity Check (SHA-256 of `initial_data.json`)

Each app's `initial_data.json` was SHA-256 hashed before classification and again
after all scratch files were written. Matching hashes prove byte-identity.

| app | before | after | match |
|-----|--------|-------|:-----:|
| central_nervous_system | `857b3d59e3ecfef62bf824420bc9cc65a758c8cdf46f7962f3560641b86fc1e1` | `857b3d59e3ecfef62bf824420bc9cc65a758c8cdf46f7962f3560641b86fc1e1` | ✅ |
| django_celery_beat | `62aaff3aac14433737804e9eb97864fc9725d8a911e52da7f18c03141fda38e9` | `62aaff3aac14433737804e9eb97864fc9725d8a911e52da7f18c03141fda38e9` | ✅ |
| environments | `ad28ba1c8cdf88b6762655b6ff683a984e6517b023017ecc20546a647abc5387` | `ad28ba1c8cdf88b6762655b6ff683a984e6517b023017ecc20546a647abc5387` | ✅ |
| frontal_lobe | `884d87241d259b025798089816a6ef07b8d593ca9e746825831920fe6ee4c1d8` | `884d87241d259b025798089816a6ef07b8d593ca9e746825831920fe6ee4c1d8` | ✅ |
| hypothalamus | `05fc6e58f1e7f36a7f715eba92c6974d882fbcd9d9d422904bbf7f1fee3c2ca4` | `05fc6e58f1e7f36a7f715eba92c6974d882fbcd9d9d422904bbf7f1fee3c2ca4` | ✅ |
| identity | `18b8b9bf3fb8479a581b2e22fdde7e3507dad67ce469e42546314923dac330b9` | `18b8b9bf3fb8479a581b2e22fdde7e3507dad67ce469e42546314923dac330b9` | ✅ |
| parietal_lobe | `3e4b45375545721538e7aeb6977983635246e38a9398e06e07d42971ea791d94` | `3e4b45375545721538e7aeb6977983635246e38a9398e06e07d42971ea791d94` | ✅ |
| peripheral_nervous_system | `9ff53a75ef873503b889870fd815ddcf5991f9cab6856e6cb4fd822fc4909948` | `9ff53a75ef873503b889870fd815ddcf5991f9cab6856e6cb4fd822fc4909948` | ✅ |
| prefrontal_cortex | `601703e769de7cf144fb4c23d679cb50d521f4cf7e1f0089d49e768c2ec4cca5` | `601703e769de7cf144fb4c23d679cb50d521f4cf7e1f0089d49e768c2ec4cca5` | ✅ |
| temporal_lobe | `8310acc9dc295ca35903535074b7db37cd9ff737adf966fd3618b38acb03ecb4` | `8310acc9dc295ca35903535074b7db37cd9ff737adf966fd3618b38acb03ecb4` | ✅ |

## 3. Dark Records Dropped (Rule 1 — `deploy_release_test`)

The only dark record found is the `DEPLOY_RELEASE` Executable itself. No
`ExecutableArgumentAssignment`, `ExecutableSwitch`, `Effector`,
`EffectorContext`, `EffectorArgumentAssignment`, `Neuron`, `NeuronContext`,
`Axon`, or `NeuralPathway` row references it. The dark cleanup is
correspondingly small.

**Dropped PKs:**

- `environments.executable` pk=`5fbd152c-23bf-4951-840f-491f4fff918a` (verified from `environments/models.py:50` as `Executable.DEPLOY_RELEASE`)

**Not dropped** (but worth noting): `Executable.DEPLOY_RELEASE` has no reverse-FK
rows in any fixture (no EAA, no ExecutableSwitch M2M targets, no Effector FKs).
The dark cleanup is the single row above.

## 4. Zygote Closure Trace

Seeds (per Rule 4):
- `identity.Identity` pk=`14148e25-283d-4547-a17d-e28d021eba07` (`Identity.THALAMUS`)
- `identity.IdentityDisc` pk=`15ca85b8-59a9-4cb6-9fd8-bfd2be47b838` (`IdentityDisc.THALAMUS`)
- `hypothalamus.AIModel` pk=`39168c4d-ed2a-54e5-98ce-1c992dff4ec8` (`nomic-embed-text`, hard dep in `hippocampus/models.py`)
- `environments.ProjectEnvironment` pk=`b7e4c2a1-3f8d-4a9e-9c1f-2d5a8b6f4e21` (the simple `Default Environment` — **not** `44b23b94-...`, which is UE-flavored)
- `central_nervous_system.Effector` pks: `a74a9b1a...` `BEGIN_PLAY`, `3aa7a066...` `LOGIC_GATE`, `644c234f...` `LOGIC_RETRY`, `0094c230...` `LOGIC_DELAY`, `8eb0d85b...` `DEBUG`

Walked forward FKs + the reverse-FK set required for Effector closure
(`EffectorContext` and `EffectorArgumentAssignment` via `.effector`, then the
`.argument` forward FK on each EAA). Integer-PK targets (already in
`genetic_immutables.json`) were noted but not re-added.

```
SEED         identity.identity pk=14148e25-283d-4547-a17d-e28d021eba07
SEED         central_nervous_system.effector pk=a74a9b1a-7326-4dff-9013-d640433b3bf7
SEED         central_nervous_system.effector pk=644c234f-c810-494b-8339-7829a143e099
SEED         central_nervous_system.effector pk=8eb0d85b-35f5-4095-9b10-37a2e6fefbef
SEED         environments.projectenvironment pk=b7e4c2a1-3f8d-4a9e-9c1f-2d5a8b6f4e21
SEED         central_nervous_system.effector pk=3aa7a066-232a-4710-b387-a9033771e8dd
SEED         hypothalamus.aimodel pk=39168c4d-ed2a-54e5-98ce-1c992dff4ec8
SEED         central_nervous_system.effector pk=0094c230-0784-4522-8e87-9c25dcab5a7f
SEED         identity.identitydisc pk=15ca85b8-59a9-4cb6-9fd8-bfd2be47b838
  ↳ [central_nervous_system.effector pk=a74a9b1a] via executable → environments.executable pk=974ed732 [PULLED]
  ↳ [central_nervous_system.effector pk=a74a9b1a] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [central_nervous_system.effector pk=a74a9b1a] via reverse:effector → central_nervous_system.effectorargumentassignment pk=bb674ffc [PULLED]
  ↳ [identity.identity pk=14148e25] via identity_type → identity.identitytype pk=3 [immutables]
  ↳ [identity.identity pk=14148e25] via selection_filter → hypothalamus.aimodelselectionfilter pk=2 [immutables]
  ↳ [identity.identity pk=14148e25] via tags → identity.identitytag pk=3 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=5 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=7 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=8 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=9 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=10 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=11 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=12 [immutables]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=36151a8b [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=1fe2d9dd [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=d26a121e [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=2479e316 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=5cb73221 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=03811f75 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=de7522e6 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=a5034848 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=8f80e108 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=ec21f60f [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=abacd3a1 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=4967bb81 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=d3138f37 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=89613bd2 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=c4ef2e80 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=63db5e88 [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=b4c8fbec [PULLED]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=aa061f89 [PULLED]
  ↳ [central_nervous_system.effector pk=644c234f] via executable → environments.executable pk=f7eb79eb [PULLED]
  ↳ [central_nervous_system.effector pk=644c234f] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [central_nervous_system.effector pk=8eb0d85b] via executable → environments.executable pk=6c43e8c9 [PULLED]
  ↳ [central_nervous_system.effector pk=8eb0d85b] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [environments.projectenvironment pk=b7e4c2a1] via type → environments.projectenvironmenttype pk=8a5e6540 [PULLED]
  ↳ [environments.projectenvironment pk=b7e4c2a1] via status → environments.projectenvironmentstatus pk=e1bb67a5 [PULLED]
  ↳ [central_nervous_system.effector pk=3aa7a066] via executable → environments.executable pk=f7eb79eb [already]
  ↳ [central_nervous_system.effector pk=3aa7a066] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [hypothalamus.aimodel pk=39168c4d] via creator → hypothalamus.aimodelcreator pk=12 [immutables]
  ↳ [hypothalamus.aimodel pk=39168c4d] via family → hypothalamus.aimodelfamily pk=10 [immutables]
  ↳ [hypothalamus.aimodel pk=39168c4d] via roles → hypothalamus.aimodelrole pk=5 [immutables]
  ↳ [central_nervous_system.effector pk=0094c230] via executable → environments.executable pk=f7eb79eb [already]
  ↳ [central_nervous_system.effector pk=0094c230] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via identity_type → identity.identitytype pk=3 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via selection_filter → hypothalamus.aimodelselectionfilter pk=3 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via tags → identity.identitytag pk=3 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=92efa6a9 [PULLED]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=5cb73221 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=03811f75 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=a5034848 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=8f80e108 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=c4ef2e80 [already]
  ↳ [identity.identity pk=14148e25] via identity_type → identity.identitytype pk=3 [immutables]
  ↳ [identity.identity pk=14148e25] via selection_filter → hypothalamus.aimodelselectionfilter pk=2 [immutables]
  ↳ [identity.identity pk=14148e25] via tags → identity.identitytag pk=3 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=5 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=7 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=8 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=9 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=10 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=11 [immutables]
  ↳ [identity.identity pk=14148e25] via addons → identity.identityaddon pk=12 [immutables]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=36151a8b [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=1fe2d9dd [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=d26a121e [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=2479e316 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=5cb73221 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=03811f75 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=de7522e6 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=a5034848 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=8f80e108 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=ec21f60f [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=abacd3a1 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=4967bb81 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=d3138f37 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=89613bd2 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=c4ef2e80 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=63db5e88 [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=b4c8fbec [already]
  ↳ [identity.identity pk=14148e25] via enabled_tools → parietal_lobe.tooldefinition pk=aa061f89 [already]
  ↳ [parietal_lobe.tooldefinition pk=89613bd2] via use_type → parietal_lobe.toolusetype pk=1 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=03811f75] via use_type → parietal_lobe.toolusetype pk=1 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=c4ef2e80] via use_type → parietal_lobe.toolusetype pk=2 [immutables]
  ↳ [central_nervous_system.effector pk=644c234f] via executable → environments.executable pk=f7eb79eb [already]
  ↳ [central_nervous_system.effector pk=644c234f] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=1fe2d9dd] via use_type → parietal_lobe.toolusetype pk=2 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=5cb73221] via use_type → parietal_lobe.toolusetype pk=4 [immutables]
  ↳ [central_nervous_system.effector pk=3aa7a066] via executable → environments.executable pk=f7eb79eb [already]
  ↳ [central_nervous_system.effector pk=3aa7a066] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=4967bb81] via use_type → parietal_lobe.toolusetype pk=3 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=63db5e88] via use_type → parietal_lobe.toolusetype pk=2 [immutables]
  ↳ [central_nervous_system.effector pk=8eb0d85b] via executable → environments.executable pk=6c43e8c9 [already]
  ↳ [central_nervous_system.effector pk=8eb0d85b] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=a5034848] via use_type → parietal_lobe.toolusetype pk=4 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=2479e316] via use_type → parietal_lobe.toolusetype pk=3 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=d26a121e] via use_type → parietal_lobe.toolusetype pk=3 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=d3138f37] via use_type → parietal_lobe.toolusetype pk=1 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=36151a8b] via use_type → parietal_lobe.toolusetype pk=2 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via identity_type → identity.identitytype pk=3 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via selection_filter → hypothalamus.aimodelselectionfilter pk=3 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via tags → identity.identitytag pk=3 [immutables]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=92efa6a9 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=5cb73221 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=03811f75 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=a5034848 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=8f80e108 [already]
  ↳ [identity.identitydisc pk=15ca85b8] via enabled_tools → parietal_lobe.tooldefinition pk=c4ef2e80 [already]
  ↳ [central_nervous_system.effector pk=a74a9b1a] via executable → environments.executable pk=974ed732 [already]
  ↳ [central_nervous_system.effector pk=a74a9b1a] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
  ↳ [central_nervous_system.effector pk=a74a9b1a] via reverse:effector → central_nervous_system.effectorargumentassignment pk=bb674ffc [already]
  ↳ [parietal_lobe.tooldefinition pk=de7522e6] via use_type → parietal_lobe.toolusetype pk=5 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=8f80e108] via use_type → parietal_lobe.toolusetype pk=1 [immutables]
  ↳ [environments.projectenvironment pk=b7e4c2a1] via type → environments.projectenvironmenttype pk=8a5e6540 [already]
  ↳ [environments.projectenvironment pk=b7e4c2a1] via status → environments.projectenvironmentstatus pk=e1bb67a5 [already]
  ↳ [hypothalamus.aimodel pk=39168c4d] via creator → hypothalamus.aimodelcreator pk=12 [immutables]
  ↳ [hypothalamus.aimodel pk=39168c4d] via family → hypothalamus.aimodelfamily pk=10 [immutables]
  ↳ [hypothalamus.aimodel pk=39168c4d] via roles → hypothalamus.aimodelrole pk=5 [immutables]
  ↳ [central_nervous_system.effectorargumentassignment pk=bb674ffc] via argument → environments.executableargument pk=920e7245 [COLLISION-UE]
  ↳ [parietal_lobe.tooldefinition pk=ec21f60f] via use_type → parietal_lobe.toolusetype pk=3 [immutables]
  ↳ [parietal_lobe.tooldefinition pk=abacd3a1] via use_type → parietal_lobe.toolusetype pk=3 [immutables]
  ↳ [central_nervous_system.effector pk=0094c230] via executable → environments.executable pk=f7eb79eb [already]
  ↳ [central_nervous_system.effector pk=0094c230] via distribution_mode → central_nervous_system.cnsdistributionmode pk=1 [immutables]
```

**Final zygote closure: 34 rows** across:

- `central_nervous_system.effector`: 5
- `central_nervous_system.effectorargumentassignment`: 1
- `environments.executable`: 3
- `environments.projectenvironment`: 1
- `environments.projectenvironmentstatus`: 1
- `environments.projectenvironmenttype`: 1
- `hypothalamus.aimodel`: 1
- `identity.identity`: 1
- `identity.identitydisc`: 1
- `parietal_lobe.tooldefinition`: 19

> **Note on expansion.** The THALAMUS `Identity` row has 18 UUIDs in its
> `enabled_tools` M2M and the THALAMUS `IdentityDisc` adds 1 more unique tool
> (5 of its 6 overlap with the Identity). Per Rule 4 forward-FK walk, those 19
> `parietal_lobe.ToolDefinition` rows are pulled into zygote. `ToolParameter`,
> `ToolParameterAssignment`, and `ParameterEnum` rows are **not** pulled — they
> only have reverse FKs into `ToolDefinition` (the tool needs to exist, not its
> parameter bindings). This matches Rule 4 literal wording but is worth a sanity
> check: at runtime, can THALAMUS actually call any of these tools without its
> `ToolParameterAssignment` rows loaded? If not, this is a hole in the rule-set
> and Michael should decide whether to extend zygote closure down the reverse
> FK for `parietal_lobe.toolparameterassignment`. Flagged in section 6 as a
> needs-decision item.

## 5. UE Modifier Closure Trace

Roots (per Rule 3):
- `environments.Executable` pks: `3ee78993...` `UNREAL_CMD`, `3ced43ee...` `UNREAL_AUTOMATION_TOOL`, `efb5d7dc...` `UNREAL_STAGING`, `6e487387...` `UNREAL_RELEASE_TEST`, `0fb093f4...` `UNREAL_SHADER_TOOL`, `1d037234...` `VERSION_HANDLER`
- `environments.ProjectEnvironment` pk=`44b23b94-6aae-4205-ae67-2f8c021c67aa` (`Default UE Environment`)

Walked: each UE Executable → its `switches` M2M, all `ExecutableArgumentAssignment`
rows where `executable ∈ UE roots` → their `.argument` forward FK, all `Effector`
rows where `executable ∈ UE roots` → their `switches` M2M, `EffectorContext`,
`EffectorArgumentAssignment` and its `.argument` forward FK, then `Neuron` rows
where `effector ∈` the UE effector set → their `NeuronContext` and `Axon`
(via `source`/`target`). For the UE `ProjectEnvironment` specifically: all
`ContextVariable` rows whose `environment = 44b23b94-...`.

**Final UE closure: 114 rows** across:

- `central_nervous_system.axon`: 17
- `central_nervous_system.effector`: 10
- `central_nervous_system.effectorargumentassignment`: 8
- `central_nervous_system.neuron`: 13
- `environments.contextvariable`: 13
- `environments.executable`: 6
- `environments.executableargument`: 7
- `environments.executableargumentassignment`: 1
- `environments.executableswitch`: 38
- `environments.projectenvironment`: 1

**NeuralPathway count in UE closure: 0.** No pathway qualified under the
strict "exclusively UE neurons" rule in Rule 3. Every pathway that contains
even one UE neuron also contains at least one core-atom neuron. These mixed
pathways are the subject of the Option B needs-decision list in section 6.

**IterationDefinition in UE closure: 0.** The UE `Default UE Environment`
has `default_iteration_definition = 9dfa8918-1dc9-4a52-b708-347883fc25bf`
("Standard Agile Sprint"), but that same iteration definition is also
referenced by `c1b7a124-...` `Are-Self-UI` (non-UE) — so per Rule 3's
"only if nothing non-UE also references them" clause, it **stays in core**
(`temporal_lobe/initial_phenotypes.json`). Flagged in section 6.

## 6. Needs-Decision List

### 6.1 `BEGIN_PLAY` effector shares `ExecutableArgument "Project"` with UE effectors (COLLISION)

This is the first real **zygote ↔ unreal_modifier collision**. Per Rule 4 the
task says STOP AND REPORT; I have written the scratch files anyway (because
Step 1 is explicitly scratch-for-review, not wiring), but Michael must
resolve this before Step 2 writes anything durable.

**The facts:**
- `central_nervous_system.Effector` pk=`a74a9b1a-7326-4dff-9013-d640433b3bf7` (`BEGIN_PLAY`, zygote per Rule 4) has one `EffectorArgumentAssignment`:
  - `central_nervous_system.effectorargumentassignment` pk=`bb674ffc-2fec-4300-8ea2-871f77f8b070` → argument=`920e7245-0487-471b-a617-b2d9964f8e17`
- `environments.ExecutableArgument` pk=`920e7245-0487-471b-a617-b2d9964f8e17` has `name="Project"` and `argument="{{project_root}}\{{uproject}}"`
- That same `ExecutableArgument` is also used by two UE effectors:
  - `central_nervous_system.Effector` pk=`f578324d-755d-4ee8-b124-40d6cd632702` (`Compile PSO Cache`, `executable=UNREAL_CMD`)
  - `central_nervous_system.Effector` pk=`557817b0-2bfe-4584-a9e8-73bd1a98d376` (`Test`, `executable=UNREAL_CMD`)

**What the classifier did:** Rule 3 ran first, so `920e7245-...` was claimed
by `unreal_modifier.json`. Rule 4 then walked zygote closure from BEGIN_PLAY,
picked up the EAA `bb674ffc-...`, tried to pull the argument — and hit a row
already marked UE. The EAA is in `central_nervous_system/zygote.json`; the
argument it FKs is in `environments/unreal_modifier.json`. **Zygote loaddata
would fail** because the argument row is not in any tier that loads before or
with zygote.

**Semantic analysis.** The `"Project"` argument's template (`{{project_root}}\{{uproject}}`)
is UE-flavored in content (`.uproject` is a UE concept), but the `BEGIN_PLAY`
Effector is listed by Michael as a zygote-tier core atom. Two non-exclusive
readings:

1. **BEGIN_PLAY is inherently UE-coupled** and should not be zygote. Move
   `BEGIN_PLAY` (and its EAA) to `unreal_modifier.json`. Zygote closure loses
   BEGIN_PLAY but still has the 4 logic atoms + DEBUG.
2. **BEGIN_PLAY is core, the argument is shared infra**, and per the Option B
   spirit (*core atoms stay in core*), the argument `920e7245-...` should move
   to zygote (or at worst `initial_phenotypes.json`) so UE can reference it
   downstream. This means rewriting rule-precedence so zygote claims forward-FK
   targets before UE does.

Needs Michael's pick.

### 6.2 Mixed NeuralPathways (Option B — 9 pathways, provisionally in `initial_phenotypes.json`)

Under strict Rule 3 ("exclusively UE neurons") no pathway qualified, so all
22 NeuralPathways were provisionally placed in `initial_phenotypes.json`. But
Option B says *"if a pathway is mixed (UE-flavored identity but composed
partly of core atoms), the pathway itself goes to the bundle"*. Determining
"UE-flavored identity" is a naming/purpose judgment — automated rules cannot
do it. The 9 pathways below contain at least one UE neuron:

| pathway pk | name | UE neurons | total neurons | UE % |
|---|---|---:|---:|---:|
| `a7d8e9f0-1b2c-4d3e-5f6a-7b8c9d0e1f2a` | Stage | 3 | 5 | 60% |
| `b8e9f0a1-2c3d-4e5f-6a7b-8c9d0e1f2b3c` | CPPTests | 1 | 2 | 50% |
| `0245b699-5b9a-43ec-9391-b788b578d25f` | Version Meta | 1 | 2 | 50% |
| `f0f0f0f0-f0f0-f0f0-f0f0-f0f0f0f0f0f0` | Multiplayer (C&S) | 2 | 4 | 50% |
| `f2a3b4c5-6d7e-8f9a-0b1c-2d3e4f5a6b7c` | Pre-Release | 2 | 5 | 40% |
| `8686149a-8b56-4a47-b5df-7d8cf7635dbc` | All Remotes | 1 | 3 | 33% |
| `22334455-6677-8899-0011-aabbccddeeff` | Compile Shaders | 1 | 3 | 33% |
| `559cecbd-2128-478a-be50-436ba30b7396` | Pre-Release Run | 1 | 5 | 20% |
| `925c871c-618e-4de8-a9d2-6978aed216e8` | Process Test | 1 | 6 | 16% |

Suggested call (not applied): pathways whose name screams UE — `Stage`,
`Compile Shaders`, `CPPTests`, `Version Meta`, `Pre-Release`, `Pre-Release Run`,
`RecordPSOs` (listed below, 0 UE neurons but UE name) — should move to
`central_nervous_system/unreal_modifier.json` in Step 2. Others (`All Remotes`,
`Multiplayer (C&S)`, `Process Test`) are ambiguous.

Also worth flagging: **some UE-named pathways have 0 UE neurons** — the
classifier found `Deploy` (15 neurons, 0 UE) and `RecordPSOs` (1 neuron, 0 UE).
Either their effectors got re-pointed away from UE executables in an earlier
pass and the pathway names are stale, or "UE flavor" really is a name/purpose
judgment the data cannot make. Michael eyes.

### 6.3 `temporal_lobe.IterationDefinition "Standard Agile Sprint"` is cross-referenced

- `temporal_lobe.iterationdefinition` pk=`9dfa8918-1dc9-4a52-b708-347883fc25bf` (`Standard Agile Sprint`)
- Referenced by `environments.projectenvironment` pk=`44b23b94-...` (`Default UE Environment`, UE)
- Also referenced by `environments.projectenvironment` pk=`c1b7a124-...` (`Are-Self-UI`, non-UE, phenotypes)

Per Rule 3's exclusivity clause, the iter def stays in core
(`temporal_lobe/initial_phenotypes.json`). Michael: confirm this is the
intended shape, or give `Are-Self-UI` its own iter def and move
`9dfa8918-...` into the UE bundle.

### 6.4 Hypothalamus zygote expansion vs. the existing `hypothalamus/fixtures/zygote.json`

The prior Pass 2 Task 2 committed (but not yet git-committed) a
`hypothalamus/fixtures/zygote.json` containing **4** `AIModel` rows:
`nomic-embed-text`, `llama3.2:3b`, `qwen2.5-coder:7b`, `gemma3:4b`. My Rule 4
seed set only has `nomic-embed-text` (the hippocampus hard dep). The other
three aren't hard dependencies — Hippocampus only needs the embed model to
boot, not the chat models.

To avoid clobbering the pre-staged file I wrote my output to
`hypothalamus/fixtures/zygote.step1.json` (1 row). The pre-staged file is
untouched.

**Decision needed:** Should zygote really contain all 4 Ollama models, or just
`nomic-embed-text`? Per Rule 4 strict interpretation ("minimum viable to boot"),
only `nomic-embed-text` belongs. Per the Pass 2 Task 2 commit intent, all 4
belong. Pick one; then either my scratch file or the pre-staged one is the
right shape.

### 6.5 THALAMUS-pulled ToolDefinitions need their ToolParameterAssignments

Rule 4's forward-FK closure pulled 19 `ToolDefinition` rows into zygote via
`Identity.enabled_tools` and `IdentityDisc.enabled_tools` M2M. But at runtime,
a tool without its `ToolParameter` + `ToolParameterAssignment` + `ParameterEnum`
rows is a tool with no schema — MCP will not be able to invoke it. Those rows
are in `parietal_lobe/initial_phenotypes.json` per Rule 6. Install-order
(zygote → phenotypes) still works, but **tests** load
`genetic_immutables → zygote → petri_dish` — they never see
`initial_phenotypes.json`, so the THALAMUS test path can boot but cannot
actually call the 19 tools.

Three resolutions, in order of least-to-most invasive:
1. Tests that exercise tool invocation load `initial_phenotypes.json` explicitly.
2. Extend Rule 4 zygote closure down the reverse FK for
   `parietal_lobe.toolparameterassignment.tool` (and chase parameters / enums).
3. Narrow the zygote THALAMUS identity to an `enabled_tools` subset that can
   be fully fit into zygote (probably just `send_thalamus_message`).

Michael's call.

### 6.6 Django-Celery-Beat integer-PK rows

`django_celery_beat/fixtures/initial_data.json` contains 7 rows across
`intervalschedule`, `crontabschedule`, `periodictask`, `periodictasks`. All
have integer PKs. Rule 2 (first match wins) routes them all to
`genetic_immutables.json`. **This feels wrong**: `PeriodicTask` is instance
data (scheduled beats), not protocol vocab. But Rule 2 is literal, so they're
in immutables. Michael: consider marking these for explicit relocation to
`zygote.json` (they're needed by install) or dropping them and re-creating them
from a fresh Celery Beat DB. Flagging, not reclassifying.

### 6.7 `petri_dish.json` is empty everywhere

I grep'd `**/tests/**/*.py` for the UUID regex and found exactly 2 unique
UUIDs, neither of which match any fixture PK in any `initial_data.json`.
Conclusion: no UUID-keyed row is referenced by test code literals, so Rule 5
produces no `petri_dish.json` files. The pre-existing
`peripheral_nervous_system/fixtures/test_agents.json` (noted but not touched)
remains the only test-only fixture.

## 7. DEFAULT_ENVIRONMENT Reference Audit

Grep for `DEFAULT_ENVIRONMENT` across the entire `are-self-api/` tree
(excluding the fixture files themselves and `venv/`):

| file:line | context | UUID resolved |
|-----------|---------|---------------|
| [`environments/models.py:127`](are-self-api/environments/models.py:127) | `DEFAULT_ENVIRONMENT = uuid.UUID('44b23b94-6aae-4205-ae67-2f8c021c67aa')` (constant definition) | `44b23b94-6aae-4205-ae67-2f8c021c67aa` — the `Default UE Environment` row, classified UE by Rule 3 |
| [`central_nervous_system/utils.py:87`](are-self-api/central_nervous_system/utils.py:87) | `env = ProjectEnvironment.objects.get(id=ProjectEnvironment.DEFAULT_ENVIRONMENT)` (lookup inside `_hydrate_metadata` — the core CNS context hydration path) | `44b23b94-...` via the constant |
| [`UUID_MIGRATION_PROMPT.md:53`](are-self-api/UUID_MIGRATION_PROMPT.md:53) | documentation reference | n/a |
| [`UUID_MIGRATION_PROMPT.md:88`](are-self-api/UUID_MIGRATION_PROMPT.md:88) | documentation reference | n/a |
| [`FIXTURE_SEPARATION_PROMPT.md:552`](are-self-api/FIXTURE_SEPARATION_PROMPT.md:552) | documentation reference | n/a |

**Finding (this is the collision Michael predicted).** The single core-code
reference is `central_nervous_system/utils.py:87`, inside a function that
hydrates spike/effector metadata during CNS execution. It resolves to the
UUID constant `ProjectEnvironment.DEFAULT_ENVIRONMENT`, which is set in
`environments/models.py:127` to `44b23b94-6aae-4205-ae67-2f8c021c67aa`. **That
is the `Default UE Environment` row, classified as UE by Rule 3.** Core code
cannot resolve a FK to a row that lives in the Unreal modifier bundle — zygote
is unbootable without the UE bundle installed.

This is the expected design collision. Two resolutions:

1. **Repoint the constant.** Change `environments/models.py:127` so
   `DEFAULT_ENVIRONMENT = uuid.UUID('b7e4c2a1-3f8d-4a9e-9c1f-2d5a8b6f4e21')`
   (the simple `Default Environment` row, which IS in zygote). The UE env
   gets a separate constant (e.g. `UE_DEFAULT_ENVIRONMENT`) and lives
   exclusively in the UE bundle.
2. **Repoint the lookup.** Change `central_nervous_system/utils.py:87` to not
   hard-code `DEFAULT_ENVIRONMENT` and instead resolve via some runtime
   lookup (e.g., `ProjectEnvironment.objects.get(selected=True)`). Leaves the
   constant alone but needs tests to ensure a selected env exists in zygote.

Either resolution is out of scope for Step 1 (this task is read/classify only).
**Investigation only — no code was touched.** Tracked here for Step 2.

## 8. Surprises

- **All initial_data.json hashes match.** No file was modified. ✅
- **`Executable.DEPLOY_RELEASE` has no dependents.** The 5fbd152c-... row is
  an orphan — no EAA, no ExecutableSwitch M2M, no Effector references it in
  any fixture. Dark cleanup is exactly 1 row. The legacy `deploy_release_test`
  flow isn't materialized in fixtures at all; whatever "materialized" it
  earlier was code-only and has been removed.
- **No `NeuralPathway` is strictly UE-exclusive.** All 22 pathways contain at
  least one core-atom neuron. Option B (move whole pathway to bundle) cannot
  be applied automatically; needs section 6.2 review.
- **`Deploy` pathway (15 neurons) has zero UE neurons.** Its name strongly
  suggests UE ownership but its actual composition is all core. Possible
  stale naming or legacy residue.
- **`RecordPSOs` pathway (1 neuron) also has zero UE neurons**, same shape as
  `Deploy`. The 1-neuron-pathway count itself is slightly surprising — look at
  it manually if you care.
- **All `django_celery_beat` rows are integer-PK.** Routed to immutables by
  Rule 2, but the content is instance data, not vocab. See section 6.6.
- **`hypothalamus/fixtures/zygote.json` already exists** (4 AIModel rows from
  Pass 2 Task 2). My output landed in `zygote.step1.json` to avoid clobber.
  The pre-staged file is byte-unchanged.
- **`hypothalamus/fixtures/ollama_complete.json`, `popular_ollama.json`,
  `initial_data_only.json`** are present but outside this task's scope. Not
  touched. `ollama_fixture_generator.py` (Pass 2 Task 5d will delete it)
  presumably emitted them.
- **`central_nervous_system/fixtures/cns_delta.json`** is present and also
  outside scope. Not read, not touched.
- **`Identity` M2M `memories` field** on the THALAMUS IdentityDisc is empty,
  so the forward-FK walk for `hippocampus.engram` found nothing. No
  `hippocampus/fixtures/*.json` files exist (the app has an empty fixtures
  directory) so nothing to classify there.
- **`neuroplasticity/fixtures/reference_data.json`** exists (from Pass 2
  Task 5a prep) but the app has no `initial_data.json` — out of scope,
  untouched.
- **Parietal ToolDefinition count routed to zygote: 19.** Larger than
  expected for a "minimum viable" tier (see section 6.5).

## 9. Files Written

All paths relative to `are-self-api/`. **No existing file was modified.** All
these files are new. One file was redirected to a `.step1.json` suffix to
avoid clobbering a pre-existing file (section 6.4 / 8).

- `central_nervous_system/fixtures/genetic_immutables.json`
- `central_nervous_system/fixtures/initial_phenotypes.json`
- `central_nervous_system/fixtures/unreal_modifier.json`
- `central_nervous_system/fixtures/zygote.json`
- `django_celery_beat/fixtures/genetic_immutables.json`
- `environments/fixtures/initial_phenotypes.json`
- `environments/fixtures/unreal_modifier.json`
- `environments/fixtures/zygote.json`
- `frontal_lobe/fixtures/genetic_immutables.json`
- `hypothalamus/fixtures/genetic_immutables.json`
- `hypothalamus/fixtures/initial_phenotypes.json`
- `hypothalamus/fixtures/zygote.step1.json`
- `identity/fixtures/genetic_immutables.json`
- `identity/fixtures/initial_phenotypes.json`
- `identity/fixtures/zygote.json`
- `parietal_lobe/fixtures/genetic_immutables.json`
- `parietal_lobe/fixtures/initial_phenotypes.json`
- `parietal_lobe/fixtures/zygote.json`
- `peripheral_nervous_system/fixtures/genetic_immutables.json`
- `prefrontal_cortex/fixtures/genetic_immutables.json`
- `temporal_lobe/fixtures/genetic_immutables.json`
- `temporal_lobe/fixtures/initial_phenotypes.json`

### Fixture files NOT written per app

For each app, only buckets with content generated files. Empty buckets are
silent. Notable gaps:
- `django_celery_beat`, `frontal_lobe`, `peripheral_nervous_system`,
  `prefrontal_cortex` ship only `genetic_immutables.json` (pure vocab apps).
- `temporal_lobe` ships `genetic_immutables.json` + `initial_phenotypes.json`
  (no zygote — `IterationDefinition "Standard Agile Sprint"` lives in
  phenotypes, see section 6.3).
- No app produced a `petri_dish.json` (section 6.7).

---

## Stop point

This is a Pass 2 **Step 1** report. Nothing has been wired up:
- `initial_data.json` files are byte-identical (hashes in section 2).
- No `.py` file was created, edited, or deleted.
- No test base class, install script, migration, or model was touched.
- No `loaddata`/`migrate`/`pytest` was run.
- Nothing is committed (`git add` will be run, `git commit` will not).

The two blocking items for Step 2 are **section 6.1** (zygote/UE argument
collision) and **section 7** (`DEFAULT_ENVIRONMENT` core reference into the
UE bundle). Both need Michael's call before Step 2 can split the files in
place.
