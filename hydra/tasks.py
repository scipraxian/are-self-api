import collections
import subprocess
from celery import shared_task
from .models import HydraHead, HydraHeadStatus

# Rigid context structure
HydraContext = collections.namedtuple('HydraContext', [
    'project_root',
    'engine_root',
    'build_root',
    'staging_dir',
    'project_name',
    'dynamic_context'  # For the "Quarks" (Git hash, etc)
])

def resolve_template(template_str, context: HydraContext):
    """
    Substitutes {VARIABLES} in the string using the NamedTuple.
    """
    if not template_str:
        return ""
    
    # Merge named fields and the dynamic dict for formatting
    # This allows {project_root} AND {GIT_HASH} to work in the same string
    format_data = context._asdict()
    if context.dynamic_context:
        format_data.update(context.dynamic_context)
        
    try:
        return template_str.format(**format_data)
    except KeyError:
        return template_str

def build_command(hydra_head):
    """
    Constructs the CLI argument list for a HydraHead.
    """
    spawn = hydra_head.spawn
    env = spawn.environment.project_environment
    spell = hydra_head.spell
    exe = spell.executable
    
    # 1. Build Context
    # Note: We treat spawn.context (if it existed) as the source of dynamic_context
    # Since we can't use JSONField on SQLite easily, we assume this is handled elsewhere 
    # or passed via a different mechanism. For now, empty dict.
    context = HydraContext(
        project_root=env.project_root,
        engine_root=env.engine_root,
        build_root=env.build_root,
        staging_dir=env.staging_dir or "",
        project_name=env.project_name,
        dynamic_context=dict()
    )

    # 2. Resolve Executable Path
    exe_path = resolve_template(exe.path_template, context)
    cmd = [exe_path]
    
    # 3. Append Switches
    for switch in spell.active_switches.all():
        flag_str = resolve_template(switch.flag, context)
        cmd.append(flag_str)
        
        if switch.value:
            val_str = resolve_template(switch.value, context)
            cmd.append(val_str)
            
    return cmd

@shared_task(bind=True)
def cast_hydra_spell(self, hydrahead_id):
    """
    The Celery Task that actually runs the command.
    """
    try:
        hydra_head = HydraHead.objects.get(id=hydrahead_id)
        
        # Build Command
        cmd = build_command(hydra_head)
        
        # Update Status (Using ID constants)
        hydra_head.status_id = HydraHeadStatus.RUNNING
        hydra_head.celery_task_id = self.request.id
        hydra_head.save()
        
        # Execute
        process = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            cwd=hydra_head.spawn.environment.project_environment.project_root
        )
        
        # Save Result
        hydra_head.spell_log = f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}"
        hydra_head.result_code = process.returncode
        
        if process.returncode == 0:
            hydra_head.status_id = HydraHeadStatus.SUCCESS
        else:
            hydra_head.status_id = HydraHeadStatus.FAILED
            
        hydra_head.save()
        
        return f"Spell {hydra_head.spell.name} finished with {process.returncode}"
        
    except Exception as e:
        if hydra_head:
            hydra_head.status_id = HydraHeadStatus.FAILED
            hydra_head.execution_log += f"\nInternal Error: {str(e)}"
            hydra_head.save()
        raise e