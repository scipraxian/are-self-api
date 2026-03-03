import os

from django.core.management import call_command
from django.core.management.base import BaseCommand

# The canonical map of apps to their structural (non-volatile) models.
CANONICAL_MODELS = {
    'environments': [
        'TalosExecutableSwitch',
        'TalosExecutableArgument',
        'TalosExecutable',
        'TalosExecutableArgumentAssignment',
        'TalosExecutableSupplementaryFileOrPath',
        'ProjectEnvironmentContextKey',
        'ProjectEnvironmentStatus',
        'ProjectEnvironmentType',
        'ProjectEnvironment',
        'ContextVariable',
    ],
    'central_nervous_system': [
        'CNSTag',
        'SpikeTrainStatus',
        'SpikeStatus',
        'CNSDistributionMode',
        'Effector',
        'EffectorContext',
        'EffectorTarget',
        'EffectorArgumentAssignment',
        'NeuralPathway',
        'Neuron',
        'NeuronContext',
        'AxonType',
        'Axon',
    ],
    'frontal_lobe': ['ReasoningStatus', 'ModelRegistry'],
    'parietal_lobe': [
        'ToolParameterType',
        'ToolUseType',
        'ToolDefinition',
        'ToolParameter',
        'ToolParameterAssignment',
        'ParameterEnum',
    ],
    'prefrontal_cortex': ['PFCItemStatus', 'PFCTag'],
    'temporal_lobe': [
        'IterationStatus',
        'Shift',
        'IterationDefinition',
        'IterationShift',
    ],
    'identity': ['IdentityType', 'IdentityTag', 'IdentityAddon', 'Identity'],
    'peripheral_nervous_system': ['NerveTerminalStatus'],
}


class Command(BaseCommand):
    help = 'Dumps all canonical structure and baseline definitions into app-specific initial_data.json fixtures.'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING('[TALOS] Engaging Structural Memory Dump...')
        )

        for app_label, model_names in CANONICAL_MODELS.items():
            # Build full identifiers (e.g., 'environments.TalosExecutable')
            full_model_names = [f'{app_label}.{name}' for name in model_names]

            output_dir = os.path.join(app_label, 'fixtures')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'initial_data.json')

            self.stdout.write(f'  > Exporting {app_label}...')

            try:
                call_command(
                    'dumpdata', *full_model_names, output=output_file, indent=2
                )
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'Failed to export {app_label}: {e}')
                )

        self.stdout.write(
            self.style.SUCCESS('[TALOS] Export Complete. Memory crystalized.')
        )
