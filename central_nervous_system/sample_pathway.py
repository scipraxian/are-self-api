"""
Pathway Sampling — surgical fixture extraction for a single NeuralPathway.

Given a pathway UUID, collects the full subgraph (Neurons, NeuronContexts,
Axons) and optionally its dependency closure (Effectors, Executables, etc.).
Objects already present in the baseline fixture tiers (genetic_immutables,
zygote, initial_phenotypes) are automatically excluded so the result is a
clean, minimal fixture ready for loaddata or neuroplasticity installation.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core import serializers

logger = logging.getLogger(__name__)

# Fixture tiers that constitute the "baseline genome".
# Anything found in these files is already guaranteed to exist at boot,
# so we never duplicate it into a sampled fixture.
BASELINE_TIERS = [
    'genetic_immutables.json',
    'zygote.json',
    'initial_phenotypes.json',
]


def _build_baseline_index():
    """
    Scan every app's fixtures/ directory for the baseline tier files.
    Returns a set of (model_label, pk_str) tuples representing every
    object that's already spoken for in the organism's genome.
    """
    index = set()
    base_dir = Path(settings.BASE_DIR)

    for child in sorted(base_dir.iterdir()):
        fixture_dir = child / 'fixtures'
        if not fixture_dir.is_dir():
            continue

        for tier_filename in BASELINE_TIERS:
            tier_path = fixture_dir / tier_filename
            if not tier_path.exists():
                continue

            try:
                with open(tier_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)

                for record in records:
                    index.add((record['model'], str(record['pk'])))

            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning(
                    'Skipping malformed fixture %s: %s', tier_path, exc
                )

    logger.info('Baseline index built: %d objects across all tiers.', len(index))
    return index


def sample_pathway(pathway_id, include_dependencies=True):
    """
    Export a NeuralPathway and its complete subgraph as a list of
    Django fixture dicts, ready for json.dumps() or loaddata.

    Args:
        pathway_id: UUID (str or UUID) of the NeuralPathway.
        include_dependencies: If True, walks the FK chain through
            Effectors → Executables → Arguments/Switches and includes
            any that are NOT already in baseline fixtures.

    Returns:
        list[dict]: Fixture records in Django's standard format.
    """
    from central_nervous_system.models import (
        Axon,
        Effector,
        EffectorArgumentAssignment,
        EffectorContext,
        NeuralPathway,
        Neuron,
        NeuronContext,
    )
    from environments.models import (
        Executable,
        ExecutableArgument,
        ExecutableArgumentAssignment,
        ExecutableSupplementaryFileOrPath,
        ExecutableSwitch,
    )

    pathway_id = str(pathway_id)
    baseline = _build_baseline_index()

    # ── Core subgraph (always included) ──────────────────────────
    pathway = NeuralPathway.objects.get(pk=pathway_id)
    neurons = list(Neuron.objects.filter(pathway=pathway))
    neuron_ids = [n.pk for n in neurons]
    neuron_contexts = list(NeuronContext.objects.filter(neuron__in=neuron_ids))
    axons = list(Axon.objects.filter(pathway=pathway))

    objects = [pathway] + neurons + neuron_contexts + axons

    # ── Dependency closure (optional) ────────────────────────────
    if include_dependencies:
        # Effectors referenced by neurons on this pathway
        effector_ids = set(n.effector_id for n in neurons)
        effectors = list(Effector.objects.filter(pk__in=effector_ids))

        effector_contexts = list(
            EffectorContext.objects.filter(effector__in=effector_ids)
        )
        effector_arg_assignments = list(
            EffectorArgumentAssignment.objects.filter(effector__in=effector_ids)
        )

        # Arguments referenced by effector-level assignments
        eff_arg_ids = set(a.argument_id for a in effector_arg_assignments)

        # Executables referenced by effectors
        exec_ids = set(e.executable_id for e in effectors)
        executables = list(Executable.objects.filter(pk__in=exec_ids))

        # Executable-level argument assignments + their arguments
        exec_arg_assignments = list(
            ExecutableArgumentAssignment.objects.filter(
                executable__in=exec_ids
            )
        )
        exec_arg_ids = set(a.argument_id for a in exec_arg_assignments)

        # Union of all referenced arguments
        all_arg_ids = eff_arg_ids | exec_arg_ids
        arguments = list(ExecutableArgument.objects.filter(pk__in=all_arg_ids))

        # Switches referenced by effectors (M2M)
        eff_switch_ids = set()
        for eff in effectors:
            eff_switch_ids.update(
                eff.switches.values_list('pk', flat=True)
            )

        # Switches referenced by executables (M2M)
        exec_switch_ids = set()
        for ex in executables:
            exec_switch_ids.update(
                ex.switches.values_list('pk', flat=True)
            )

        all_switch_ids = eff_switch_ids | exec_switch_ids
        switches = list(ExecutableSwitch.objects.filter(pk__in=all_switch_ids))

        # Supplementary files/paths on executables
        supplementary = list(
            ExecutableSupplementaryFileOrPath.objects.filter(
                executable__in=exec_ids
            )
        )

        objects.extend(
            executables
            + arguments
            + switches
            + effectors
            + effector_contexts
            + effector_arg_assignments
            + exec_arg_assignments
            + supplementary
        )

    # ── Serialize and filter against baseline ────────────────────
    raw_json_str = serializers.serialize('json', objects, indent=2)
    all_records = json.loads(raw_json_str)

    fixture = []
    seen = set()  # deduplicate (an object might appear via multiple paths)

    for record in all_records:
        key = (record['model'], str(record['pk']))

        if key in baseline:
            continue  # already in the genome, skip

        if key in seen:
            continue  # already captured on this sample

        seen.add(key)
        fixture.append(record)

    logger.info(
        'Sampled pathway "%s": %d records (%d filtered as baseline).',
        pathway.name,
        len(fixture),
        len(all_records) - len(fixture),
    )

    return fixture
