import collections
import datetime
import os

# Rigid context structure
HydraContext = collections.namedtuple('HydraContext', [
    'project_root', 'engine_root', 'build_root', 'staging_dir', 'project_name',
    'dynamic_context'
])


def get_timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def log_system(head, message):
    """Helper to append to execution_log and save immediately."""
    entry = f"[{get_timestamp()}] {message}\n"
    # we fetch a fresh copy to avoid overwriting spell_log stream updates
    # or just append safely since we are the primary writer
    head.execution_log += entry
    head.save(update_fields=['execution_log'])


def resolve_template(template_str, context: HydraContext):
    if not template_str:
        return ""
    format_data = context._asdict()
    if context.dynamic_context:
        format_data.update(context.dynamic_context)
    try:
        return template_str.format(**format_data)
    except KeyError:
        return template_str
