import json

from asgiref.sync import sync_to_async
from django.db.models import Q

from common.queries import guess_model


@sync_to_async
def _query_model_sync(
    model_name: str,
    filters: dict = None,
    q_string: str = None,
    page: int = 1,
) -> str:

    result = guess_model(model_name)
    if not result.success:
        return result.message
    model_class = result.model_class
    app_label = result.app_label

    qs = model_class.objects.all()

    if filters:
        # Post-UUID-migration alias: the PK field is always 'id', but the LLM
        # frequently guesses 'uuid' because the value IS a UUID. Silently
        # rewrite rather than scolding it in tool descriptions. If the caller
        # supplied both 'id' and 'uuid', explicit 'id' wins and 'uuid' is
        # discarded — we never want a raw 'uuid' key reaching the ORM.
        if 'uuid' in filters:
            alias_value = filters.pop('uuid')
            filters.setdefault('id', alias_value)
        try:
            qs = qs.filter(**filters)
        except Exception as e:
            return f'Error applying filters: {str(e)}'

    if q_string:
        try:
            q_obj = eval(q_string, {'__builtins__': {}}, {'Q': Q})
            qs = qs.filter(q_obj)
        except Exception as e:
            return f'Error evaluating q_string: {str(e)}'

    # --- STRICT PAGINATION ---
    page_size = 5  # HARD CAP FOR DB ROWS TO PROTECT CONTEXT
    total_records = qs.count()
    total_pages = max(1, (total_records + page_size - 1) // page_size)

    safe_page = max(1, min(int(page), total_pages))
    start_idx = (safe_page - 1) * page_size
    end_idx = start_idx + page_size

    try:
        qs_page = qs[start_idx:end_idx]
        results = []
        for obj in qs_page:
            # 1. Base identity
            item = {'_model': f'{app_label}.{model_name}', 'id': str(obj.pk)}

            # 2. Extract all native fields safely
            for field in obj._meta.get_fields():
                if field.is_relation:
                    continue  # Skip relational dumps to prevent recursive explosions

                val = getattr(obj, field.name, None)
                if val is None:
                    item[field.name] = None
                    continue

                str_val = str(val)

                # 3. Truncate heavy text fields (protects the AI from gorging)
                if len(str_val) > 200:
                    item[field.name] = (
                        str_val[:200]
                        + '... [TRUNCATED: Use mcp_read_record_field to read full content]'
                    )
                else:
                    item[field.name] = str_val

            results.append(item)

        output = {
            'meta': f'Page {safe_page} of {total_pages} (Total Records: {total_records})',
            'records': results,
        }
        return json.dumps(output, indent=2)
    except Exception as e:
        return f'Error executing query: {str(e)}'


async def mcp_query_model(
    model_name: str,
    filters: dict = None,
    q_string: str = None,
    page: int = 1,
    thought: str = '',
) -> str:
    """MCP Tool: Queries database via pagination. Auto-truncates massive fields."""
    filters = filters or {}
    return await _query_model_sync(model_name, filters, q_string, page)
