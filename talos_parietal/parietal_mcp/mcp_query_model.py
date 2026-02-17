import json

from asgiref.sync import sync_to_async
from django.apps import apps


@sync_to_async
def _query_model_sync(app_label: str, model_name: str, filters: dict) -> str:
    try:
        model_class = apps.get_model(app_label, model_name)
    except LookupError:
        return f"Error: Model '{app_label}.{model_name}' not found."

    try:
        qs = model_class.objects.filter(**filters)[:50]
        results = []
        for obj in qs:
            # Try to grab standard identifiable fields, default to string
            # representation
            item = {"id": str(obj.pk), "display": str(obj)}
            if hasattr(obj, 'name'): item['name'] = obj.name
            if hasattr(obj, 'status'): item['status'] = str(obj.status)
            results.append(item)

        return json.dumps({"count_returned": len(results), "records": results},
                          indent=2)
    except Exception as e:
        return f"Error executing query: {str(e)}"


async def mcp_query_model(app_label: str, model_name: str,
                          filters: dict) -> str:
    """MCP Tool: Queries a database model and returns a list of matching
    records."""
    return await _query_model_sync(app_label, model_name, filters)
