import logging
from typing import Any, Dict

from asgiref.sync import sync_to_async

from common.queries import guess_model

logger = logging.getLogger(__name__)


@sync_to_async
def _get_record_stats(model_name: str, record_id: str) -> Dict[str, Any]:
    """Synchronous Django ORM work."""
    result = guess_model(model_name)
    if not result.success:
        return {'error': result.message}
    model_class = result.model_class

    try:
        record = model_class.objects.get(pk=record_id)
    except model_class.DoesNotExist:
        return {'error': f'Record {record_id} not found in {model_name}.'}
    except Exception as e:
        return {
            'error':
                f'Invalid record ID {record_id} for {model_name}. Reason: {str(e)}'
        }

    stats = {'id': str(record.pk)}

    # Introspect the fields
    for field in model_class._meta.get_fields():
        if field.is_relation or field.auto_created:
            continue

        val = getattr(record, field.name, None)
        field_type = field.get_internal_type()

        info = {'type': field_type}

        # Calculate sizes for text fields
        if field_type in ['TextField', 'CharField'] and val:
            info['size_chars'] = len(str(val))
            info['preview'] = (str(val)[:50] +
                               '...' if len(str(val)) > 50 else str(val))
        else:
            info['value'] = str(val)

        stats[field.name] = info

    return stats


async def mcp_inspect_record(model_name: str, record_id: str) -> str:
    """
    MCP Tool: Inspects a database record, returning its schema and field sizes.
    """
    import json

    logger.info(f'[MCP] Inspecting {model_name} ({record_id})')

    stats = await _get_record_stats(model_name, record_id)
    return json.dumps(stats, indent=2)
