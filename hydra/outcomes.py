import glob
import os
import shutil

from talos_frontal.logic import process_stimulus
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID
from .models import HydraHead, HydraHeadStatus, HydraOutcomeActionID
from .utils import HydraContext, log_system, resolve_template


def process_outcomes(head_id):
    try:
        head = HydraHead.objects.select_related(
            'spawn__environment__project_environment', 'spell').get(id=head_id)
    except HydraHead.DoesNotExist:
        return

    spawn = head.spawn
    env = spawn.environment.project_environment
    context = HydraContext(project_root=env.project_root,
                           engine_root=env.engine_root,
                           build_root=env.build_root,
                           staging_dir=env.staging_dir or "",
                           project_name=env.project_name,
                           dynamic_context={})

    outcomes = head.spell.outcome_configs.select_related('action').all()
    if not outcomes:
        return

    log_system(
        head,
        f"Processing {outcomes.count()} outcomes for spell '{head.spell.name}'..."
    )

    for outcome in outcomes:
        action_code = outcome.action_id
        action_name = outcome.action.name if outcome.action else "UNKNOWN"

        try:
            if action_code == HydraOutcomeActionID.ANALYZE:
                log_system(head, "Outcome ANALYZE: Triggering Stimulus Processor.")
                stimulus = Stimulus(
                    source='hydra',
                    description=f"Automated Analysis Triggered by Spell: {head.spell.name}",
                    context_data=dict(
                        spawn_id=str(spawn.id),
                        head_id=str(head.id),
                        event_type=SignalTypeID.SPAWN_SUCCESS
                )
                )
                process_stimulus(stimulus)
                continue
            src_pattern = resolve_template(outcome.source_path_template, context)
            dest_template = resolve_template(outcome.dest_path_template, context)

            src_pattern = os.path.normpath(src_pattern)
            if dest_template:
                dest_template = os.path.normpath(dest_template)

            matches = glob.glob(src_pattern)

            if not matches:
                if outcome.must_exist:
                    raise FileNotFoundError(
                        f"Source pattern matched nothing: {src_pattern}")
                else:
                    log_system(
                        head,
                        f"Skipping {action_name}: No matches for '{src_pattern}'"
                    )
                    continue

            for src in matches:
                if action_code == HydraOutcomeActionID.DELETE:
                    log_system(head, f"Outcome DELETE: {src}")
                    if os.path.isfile(src):
                        os.remove(src)
                    else:
                        shutil.rmtree(src)

                elif action_code == HydraOutcomeActionID.VALIDATE_EXISTS:
                    log_system(head, f"Outcome VALIDATE: Found {src}")

                elif action_code in (HydraOutcomeActionID.COPY,
                                     HydraOutcomeActionID.MOVE):
                    if not dest_template:
                        raise ValueError(
                            "Destination path required for COPY/MOVE")

                    target_path = dest_template
                    is_dir_target = outcome.dest_path_template.endswith(
                        '/') or outcome.dest_path_template.endswith('\\')

                    if is_dir_target:
                        os.makedirs(target_path, exist_ok=True)
                        dest_final = os.path.join(target_path,
                                                  os.path.basename(src))
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        dest_final = target_path

                    if action_code == HydraOutcomeActionID.MOVE:
                        log_system(head, f"Outcome MOVE: {src} -> {dest_final}")
                        shutil.move(src, dest_final)
                    else:  # COPY
                        log_system(head, f"Outcome COPY: {src} -> {dest_final}")
                        if os.path.isfile(src):
                            shutil.copy2(src, dest_final)
                        else:
                            shutil.copytree(src, dest_final, dirs_exist_ok=True)

        except Exception as e:
            log_system(head, f"OUTCOME ERROR: {str(e)}")
            head.status_id = HydraHeadStatus.FAILED
            head.save()
            return

    log_system(head, "Outcome processing complete.")