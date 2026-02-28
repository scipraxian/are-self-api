import asyncio
import json

import pytest

from central_nervous_system.models import CNSHead, CNSHeadStatus, CNSSpawn, \
    CNSSpawnStatus
from parietal_lobe.parietal_mcp.gateway import ParietalMCP


@pytest.fixture
def db_setup():
    """Sets up base database records for the tools to query."""
    # Create required statuses
    spawn_status, _ = CNSSpawnStatus.objects.get_or_create(
        id=1, defaults={'name': 'Created'})
    head_status_active, _ = CNSHeadStatus.objects.get_or_create(
        id=2, defaults={'name': 'Active'})
    head_status_error, _ = CNSHeadStatus.objects.get_or_create(
        id=6, defaults={'name': 'Error'})

    # Create a Spawn
    spawn = CNSSpawn.objects.create(status=spawn_status)

    # Create Heads
    head_1 = CNSHead.objects.create(spawn=spawn,
                                      status=head_status_active,
                                      blackboard={"var": "alpha"})
    head_2 = CNSHead.objects.create(spawn=spawn,
                                      status=head_status_error,
                                      application_log="Fatal error on line 42")

    return {
        "spawn": spawn,
        "head_1": head_1,
        "head_2": head_2,
        "status_error_id": head_status_error.id
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_dynamic_routing(db_setup):
    """Ensures the ParietalMCP gateway actually routes to the correct file."""
    head_id = str(db_setup["head_1"].id)

    result = await ParietalMCP.execute("mcp_update_blackboard", {
        "head_id": head_id,
        "key": "test_gateway",
        "value": "routed"
    })

    assert "Success" in result

    await asyncio.to_thread(db_setup["head_1"].refresh_from_db)
    assert db_setup["head_1"].blackboard.get("test_gateway") == "routed"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_query_model_basic_filters(db_setup):
    """Ensures basic kwargs filtering works."""
    result = await ParietalMCP.execute(
        "mcp_query_model", {
            "model_name": "CNSHead",
            "filters": {
                "status_id": db_setup["status_error_id"]
            }
        })

    data = json.loads(result)
    assert len(data["records"]) == 1
    assert data["records"][0]["id"] == str(db_setup["head_2"].id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_query_model_q_string_logic(db_setup):
    """Ensures the AI can write raw Q() objects for complex queries."""
    # Test an OR query that should return both heads
    q_string = (f"Q(status_id={db_setup['status_error_id']}) | Q("
                f"blackboard__var='alpha')")

    result = await ParietalMCP.execute("mcp_query_model", {
        "model_name": "CNSHead",
        "q_string": q_string
    })

    data = json.loads(result)
    assert len(data["records"]) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_query_model_count_action(db_setup):
    """Ensures the AI can request a raw integer count instead of heavy data."""
    result = await ParietalMCP.execute("mcp_query_model",
                                       {"model_name": "CNSHead"})

    data = json.loads(result)
    assert "Total Records:" in data["meta"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_inspect_record(db_setup):
    """Ensures the radar/stat checker correctly maps the schema and field
    sizes."""
    head_id = str(db_setup["head_2"].id)

    result = await ParietalMCP.execute("mcp_inspect_record", {
        "model_name": "CNSHead",
        "record_id": head_id
    })

    data = json.loads(result)
    assert "id" in data
    assert "application_log" in data
    assert data["application_log"]["type"] == "TextField"
    assert "size_chars" in data["application_log"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_search_and_read_record(db_setup):
    """Simulates the AI's 1-2 punch of searching a log, then reading the
    chunk."""
    head_id = str(db_setup["head_2"].id)

    # 1. Search the log
    search_result = await ParietalMCP.execute(
        "mcp_search_record_field", {
            "app_label": "central_nervous_system",
            "model_name": "CNSHead",
            "record_id": head_id,
            "field_name": "application_log",
            "pattern": "Fatal"
        })

    assert "Match 1" in search_result
    assert "Fatal error" in search_result

    # 2. Read the log
    read_result = await ParietalMCP.execute(
        "mcp_read_record_field", {
            "app_label": "central_nervous_system",
            "model_name": "CNSHead",
            "record_id": head_id,
            "field_name": "application_log",
            "start_line": 1,
            "max_lines": 5
        })

    assert "1: Fatal error on line 42" in read_result
