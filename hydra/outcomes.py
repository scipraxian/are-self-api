import os
import shutil
import glob
from .models import HydraHead, HydraHeadStatus, HydraOutcomeAction, HydraOutcomeActionID
from .utils import HydraContext, resolve_template, log_system


def process_outcomes(head_id):
    try:
        # Select related to avoid N+1 on action lookup (though spelled out logic handles it cleanly too)
        head = HydraHead.objects.select_related(
            'spawn__environment__project_environment', 'spell').get(id=head_id)
    except HydraHead.DoesNotExist:
        return

    # Reconstruct context
    spawn = head.spawn
    env = spawn.environment.project_environment
    context = HydraContext(project_root=env.project_root,
                           engine_root=env.engine_root,
                           build_root=env.build_root,
                           staging_dir=env.staging_dir or "",
                           project_name=env.project_name,
                           dynamic_context={})

    # prefetch actions?
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
            src_pattern = resolve_template(outcome.source_path_template,
                                           context)
            dest_template = resolve_template(outcome.dest_path_template,
                                             context)

            # Helper to handle Windows paths if needed, though python handles / fine mostly
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
                # Handle actions
                if action_code == HydraOutcomeActionID.DELETE:
                    log_system(head, f"Outcome DELETE: {src}")
                    if os.path.isfile(src):
                        os.remove(src)
                    else:
                        shutil.rmtree(src)

                elif action_code == HydraOutcomeActionID.VALIDATE_EXISTS:
                    log_system(head, f"Outcome VALIDATE: Found {src}")
                    # implicit success if loop runs

                elif action_code in (HydraOutcomeActionID.COPY,
                                     HydraOutcomeActionID.MOVE):
                    if not dest_template:
                        raise ValueError(
                            "Destination path required for COPY/MOVE")

                    # Logic: If querying multiple files, dest MUST be a directory.
                    # Or if dest ends with separator.

                    # We assume dest is a directory if we are processing a list?
                    # Or if the path ends with slash (but normpath kills slashes).
                    # Let's rely on os.path.isdir logic.

                    # If dest_template looks like a file (has extension) and we have single match, maybe generic copy?
                    # But prompt example: Dest: .../PipelineCaches/ (folder)
                    # Source: ...file.spc

                    # If I move File -> Dir, I need to join the filename.
                    target_path = dest_template

                    # Ensure dest dir exists
                    # If target path is meant to be a file name, we need its dirname.
                    # If target path is a dir, we make it.

                    # Heuristic: If dest ends in slash (in template) -> Dir.
                    # But resolving template might strip it if I use normpath?
                    # os.path.normpath("C:/Foo/") -> "C:\Foo" (no slash).

                    # Let's check if the raw template ended in slash?
                    # Or just assume we copy into it?

                    # If simply passing dest to shutil.move(src, dest):
                    # If dest is dir, it moves into it.
                    # If dest doesn't exist, it moves AS it (rename).

                    # The prompt example:
                    # Source: ..._PCD3D_SM6.spc
                    # Dest: .../PipelineCaches/ (Directory)

                    # If I just do shutil.move(src, dest), and dest doesn't exist, it renames spc to PipelineCaches (file).
                    # THAT IS BAD if it was meant to be a directory.

                    # So I should ensure the destination directory exists.
                    # Does dest_template represent the directory?
                    # If the user put a trailing slash, probably yes.
                    # If I stripped it, I lost that info.

                    # Let's look at `outcome.dest_path_template` (raw).
                    # If it ends with / or \, treat as directory.
                    is_dir_target = outcome.dest_path_template.endswith(
                        '/') or outcome.dest_path_template.endswith('\\')

                    if is_dir_target:
                        os.makedirs(target_path, exist_ok=True)
                        dest_final = os.path.join(target_path,
                                                  os.path.basename(src))
                    else:
                        # Maybe it's a full path rename?
                        # Ensure parent exists
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
