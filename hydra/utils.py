import datetime
from typing import NamedTuple


class HydraContext(NamedTuple):  # depreciated.
    project_root: str
    engine_root: str
    build_root: str
    staging_dir: str
    project_name: str
    dynamic_context: dict


def get_timestamp():
    return datetime.datetime.now().strftime('%H:%M:%S')


def log_system(head, message):
    entry = f'[{get_timestamp()}] {message}\n'
    head.execution_log += entry
    head.save(update_fields=['execution_log'])


def resolve_template(template_str, context: HydraContext):
    if not template_str:
        return ''
    format_data = context._asdict()
    if context.dynamic_context:
        format_data.update(context.dynamic_context)
    try:
        return template_str.format(**format_data)
    except KeyError:
        return template_str
