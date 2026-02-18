import json

from asgiref.sync import sync_to_async
from django.apps import apps
from django.db.models import Q


@sync_to_async
def _query_model_sync(app_label: str, model_name: str, filters: dict = None,
                      q_string: str = None, action: str = "list") -> str:
    try:
        model_class = apps.get_model(app_label, model_name)
    except LookupError:
        return f"Error: Model '{app_label}.{model_name}' not found."

    qs = model_class.objects.all()

    # Apply standard kwargs filters if provided
    if filters:
        try:
            qs = qs.filter(**filters)
        except Exception as e:
            return f"Error applying filters: {str(e)}"

    # Apply advanced Q() object string if provided
    if q_string:
        try:
            # Safely evaluate the string using a restricted environment
            # containing ONLY 'Q'
            q_obj = eval(q_string, {"__builtins__": {}}, {"Q": Q})
            if not isinstance(q_obj, Q):
                return "Error: q_string must evaluate to a Django Q object."
            qs = qs.filter(q_obj)
        except Exception as e:
            return f"Error evaluating q_string '{q_string}': {str(e)}"

    # Handle the requested action
    if action == "count":
        try:
            return json.dumps({"count": qs.count()}, indent=2)
        except Exception as e:
            return f"Error performing count: {str(e)}"

    # Default action: return a list of records
    try:
        qs = qs[:50]  # Hard limit to prevent memory explosions
        results = []
        for obj in qs:
            item = {"id": str(obj.pk), "display": str(obj)}
            if hasattr(obj, 'name'): item['name'] = obj.name
            if hasattr(obj, 'status'): item['status'] = str(obj.status)
            results.append(item)

        return json.dumps({"count_returned": len(results), "records": results},
                          indent=2)
    except Exception as e:
        return f"Error executing query: {str(e)}"


async def mcp_query_model(app_label: str, model_name: str, filters: dict = None,
                          q_string: str = None, action: str = "list") -> str:
    """MCP Tool: Queries a database model using kwargs or complex Q()
    objects."""
    # Ensure at least an empty dict if None is passed by the LLM
    filters = filters or {}
    return await _query_model_sync(app_label, model_name, filters, q_string,
                                   action)
