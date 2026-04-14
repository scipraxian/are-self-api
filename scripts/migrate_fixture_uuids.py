"""One-off fixture transform for the UUID migration pass.

Rewrites every Django `dumpdata`-style initial_data.json in the repo so that
PKs (and FK/M2M references to them) for plugin-extensible models are UUIDs
instead of integers.

Usage:
    python scripts/migrate_fixture_uuids.py

The script is idempotent on already-UUID values: if it encounters a PK that is
already a string-shaped UUID, it skips it. The mapping of every old int PK to
its new UUID is written to `uuid_migration_mapping.json` at the repo root for
audit and cross-referencing.

Canonical class-level PK constants (Effector.BEGIN_PLAY, Executable.PYTHON,
etc.) are pre-seeded in MAPPING_SEED so they keep stable UUIDs matching the
Python model definitions. Every other row is assigned a fresh uuid4.
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING_PATH = REPO_ROOT / 'uuid_migration_mapping.json'

# Models whose PK type is flipping from int -> UUID in this pass.
MIGRATING_MODELS = {
    'central_nervous_system.effector',
    'central_nervous_system.effectorcontext',
    'central_nervous_system.effectorargumentassignment',
    'central_nervous_system.neuron',
    'central_nervous_system.neuroncontext',
    'central_nervous_system.axon',
    'environments.executable',
    'environments.executableswitch',
    'environments.executableargument',
    'environments.executableargumentassignment',
    'environments.contextvariable',
    'parietal_lobe.tooldefinition',
    'parietal_lobe.toolparameter',
    'parietal_lobe.parameterenum',
    'parietal_lobe.toolparameterassignment',
    'hypothalamus.aimodeldescription',
    'temporal_lobe.iterationdefinition',
    'temporal_lobe.iterationshiftdefinition',
}

# (owning_model, field_name) -> target_model for every FK/OneToOne that points
# at a migrating model, regardless of whether the owning model is migrating.
# Field names use the exact key as they appear in fixture JSON (no _id suffix).
FK_MAP: Dict[Tuple[str, str], str] = {
    ('central_nervous_system.effector', 'executable'): 'environments.executable',
    ('central_nervous_system.effectorcontext', 'effector'): 'central_nervous_system.effector',
    ('central_nervous_system.effectorargumentassignment', 'effector'): 'central_nervous_system.effector',
    ('central_nervous_system.effectorargumentassignment', 'argument'): 'environments.executableargument',
    ('central_nervous_system.effectortarget', 'effector'): 'central_nervous_system.effector',
    ('central_nervous_system.neuron', 'effector'): 'central_nervous_system.effector',
    ('central_nervous_system.neuroncontext', 'neuron'): 'central_nervous_system.neuron',
    ('central_nervous_system.axon', 'source'): 'central_nervous_system.neuron',
    ('central_nervous_system.axon', 'target'): 'central_nervous_system.neuron',
    ('environments.executableargumentassignment', 'executable'): 'environments.executable',
    ('environments.executableargumentassignment', 'argument'): 'environments.executableargument',
    ('environments.executablesupplementaryfileorpath', 'executable'): 'environments.executable',
    ('parietal_lobe.toolparameterassignment', 'tool'): 'parietal_lobe.tooldefinition',
    ('parietal_lobe.toolparameterassignment', 'parameter'): 'parietal_lobe.toolparameter',
    ('parietal_lobe.parameterenum', 'parameter'): 'parietal_lobe.toolparameter',
    ('parietal_lobe.toolcall', 'tool'): 'parietal_lobe.tooldefinition',
    ('temporal_lobe.iterationshiftdefinition', 'definition'): 'temporal_lobe.iterationdefinition',
    ('environments.projectenvironment', 'default_iteration_definition'): 'temporal_lobe.iterationdefinition',
    ('temporal_lobe.iteration', 'iteration_definition'): 'temporal_lobe.iterationdefinition',
    ('temporal_lobe.iterationshiftdefinitionparticipant', 'shift_definition'): 'temporal_lobe.iterationshiftdefinition',
}

# (owning_model, field_name) -> target_model for every M2M that references a
# migrating model. Each such field value is a list of PKs that need rewriting.
M2M_MAP: Dict[Tuple[str, str], str] = {
    ('environments.executable', 'switches'): 'environments.executableswitch',
    ('central_nervous_system.effector', 'switches'): 'environments.executableswitch',
    ('identity.identity', 'enabled_tools'): 'parietal_lobe.tooldefinition',
    ('identity.identitydisc', 'enabled_tools'): 'parietal_lobe.tooldefinition',
}

# Pre-seeded canonical class-constant UUIDs. These MUST match the values in
# central_nervous_system/models.py (Effector) and environments/models.py
# (Executable). If you change one side, change the other.
MAPPING_SEED: Dict[str, Dict[str, str]] = {
    'central_nervous_system.effector': {
        '1': 'a74a9b1a-7326-4dff-9013-d640433b3bf7',  # BEGIN_PLAY
        '5': '3aa7a066-232a-4710-b387-a9033771e8dd',  # LOGIC_GATE
        '6': '644c234f-c810-494b-8339-7829a143e099',  # LOGIC_RETRY
        '7': '0094c230-0784-4522-8e87-9c25dcab5a7f',  # LOGIC_DELAY
        '8': '64c0995a-cbd2-47d3-a452-e36ea4d46154',  # FRONTAL_LOBE
        '9': '8eb0d85b-35f5-4095-9b10-37a2e6fefbef',  # DEBUG
    },
    'environments.executable': {
        '1': '974ed732-6f2d-47f4-9482-18d17c73086e',  # BEGIN_PLAY
        '2': '558806d7-d009-4e89-8e4e-86979dcd0594',  # PYTHON
        '3': '11915177-a32b-4883-8c9f-e137c528c20d',  # DJANGO
        '4': '3ee78993-faa3-401b-8187-c771e11c4564',  # UNREAL_CMD
        '5': '3ced43ee-5504-493a-a4b7-15040bb17100',  # UNREAL_AUTOMATION_TOOL
        '6': 'efb5d7dc-9922-43ec-b108-5af5f029b71d',  # UNREAL_STAGING
        '7': '6e487387-9608-4481-8f5c-9b0741585633',  # UNREAL_RELEASE_TEST
        '8': '0fb093f4-8c4a-4f40-ad1b-234e4f516f4f',  # UNREAL_SHADER_TOOL
        '9': '1d037234-c8c2-4d51-bc65-41597c0becd2',  # VERSION_HANDLER
        '10': '5fbd152c-23bf-4951-840f-491f4fff918a',  # DEPLOY_RELEASE
    },
}


def discover_fixture_files(root: Path) -> List[Path]:
    """Returns every .json file under a */fixtures/ directory in the repo."""
    out: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if os.sep + 'venv' + os.sep in dirpath or os.sep + 'node_modules' + os.sep in dirpath:
            continue
        if os.sep + 'fixtures' + os.sep not in dirpath + os.sep:
            continue
        for fname in filenames:
            if fname.endswith('.json'):
                out.append(Path(dirpath) / fname)
    return out


def load_fixture(path: Path) -> List[dict]:
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def save_fixture(path: Path, rows: List[dict]) -> None:
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def is_uuid_string(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def build_mapping(
    fixture_paths: Iterable[Path],
) -> Dict[str, Dict[str, str]]:
    """Walks every fixture row once and assigns a UUID for each migrating PK.

    Returns a nested dict: mapping[model] = {str(old_int_pk): uuid_string}.
    Pre-seeded canonical constants are honored. Any row whose PK is already a
    UUID string is mapped to itself so FK rewriters can still look it up.
    """
    mapping: Dict[str, Dict[str, str]] = {
        model: dict(seeds) for model, seeds in MAPPING_SEED.items()
    }
    for path in fixture_paths:
        rows = load_fixture(path)
        for row in rows:
            model = row.get('model', '').lower()
            if model not in MIGRATING_MODELS:
                continue
            pk = row.get('pk')
            if pk is None:
                continue
            bucket = mapping.setdefault(model, {})
            key = str(pk)
            if key in bucket:
                continue
            if is_uuid_string(pk):
                bucket[key] = str(pk)
            else:
                bucket[key] = str(uuid.uuid4())
    return mapping


def rewrite_pk(row: dict, mapping: Dict[str, Dict[str, str]]) -> None:
    """If this row's own PK is migrating, replace it in place."""
    model = row.get('model', '').lower()
    if model not in MIGRATING_MODELS:
        return
    pk = row.get('pk')
    if pk is None:
        return
    bucket = mapping.get(model, {})
    new_pk = bucket.get(str(pk))
    if new_pk is None:
        raise RuntimeError(
            f'No mapping entry for {model} pk={pk!r}. Mapping pass missed it.'
        )
    row['pk'] = new_pk


def rewrite_fks(row: dict, mapping: Dict[str, Dict[str, str]]) -> None:
    """Rewrites every FK/M2M field on this row that points at a migrating model."""
    model = row.get('model', '').lower()
    fields = row.get('fields') or {}
    for field_name, value in list(fields.items()):
        target = FK_MAP.get((model, field_name))
        if target is not None and value is not None:
            new_value = mapping.get(target, {}).get(str(value))
            if new_value is None:
                if is_uuid_string(value):
                    continue
                raise RuntimeError(
                    f'No mapping for FK {model}.{field_name}={value!r} '
                    f'(target {target}).'
                )
            fields[field_name] = new_value
            continue
        m2m_target = M2M_MAP.get((model, field_name))
        if m2m_target is not None and isinstance(value, list):
            rewritten: List[str] = []
            for item in value:
                new_item = mapping.get(m2m_target, {}).get(str(item))
                if new_item is None:
                    if is_uuid_string(item):
                        rewritten.append(item)
                        continue
                    raise RuntimeError(
                        f'No mapping for M2M {model}.{field_name}={item!r} '
                        f'(target {m2m_target}).'
                    )
                rewritten.append(new_item)
            fields[field_name] = rewritten


def main() -> int:
    fixture_paths = discover_fixture_files(REPO_ROOT)
    fixture_paths = [p for p in fixture_paths if 'are-self-api' in str(p)]
    if not fixture_paths:
        print('No fixtures found.', file=sys.stderr)
        return 1
    print(f'Found {len(fixture_paths)} fixture file(s).')
    for path in fixture_paths:
        print(f'  {path.relative_to(REPO_ROOT)}')

    print('Building mapping...')
    mapping = build_mapping(fixture_paths)
    total = sum(len(bucket) for bucket in mapping.values())
    print(f'Mapped {total} row(s) across {len(mapping)} model(s).')

    with open(MAPPING_PATH, 'w', encoding='utf-8') as fh:
        json.dump(mapping, fh, indent=2, sort_keys=True)
        fh.write('\n')
    print(f'Wrote {MAPPING_PATH.relative_to(REPO_ROOT)}.')

    print('Rewriting fixtures...')
    for path in fixture_paths:
        rows = load_fixture(path)
        touched = 0
        for row in rows:
            before = json.dumps(row, sort_keys=True)
            rewrite_pk(row, mapping)
            rewrite_fks(row, mapping)
            after = json.dumps(row, sort_keys=True)
            if before != after:
                touched += 1
        if touched:
            save_fixture(path, rows)
            print(f'  rewrote {touched} row(s) in {path.relative_to(REPO_ROOT)}')
        else:
            print(f'  unchanged: {path.relative_to(REPO_ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
