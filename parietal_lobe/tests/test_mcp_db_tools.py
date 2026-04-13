import asyncio
import json

import pytest

from central_nervous_system.models import Spike, SpikeStatus, SpikeTrain, \
    SpikeTrainStatus
from parietal_lobe.parietal_mcp.gateway import ParietalMCP


@pytest.fixture
def db_setup():
    """Sets up base database records for the tools to query."""
    # Create required statuses
    spike_train_status, _ = SpikeTrainStatus.objects.get_or_create(
        id=1, defaults={'name': 'Created'})
    head_status_active, _ = SpikeStatus.objects.get_or_create(
        id=2, defaults={'name': 'Active'})
    head_status_error, _ = SpikeStatus.objects.get_or_create(
        id=6, defaults={'name': 'Error'})

    # Create a Spawn
    spike_train = SpikeTrain.objects.create(status=spike_train_status)

    # Create Spikes
    spike_1 = Spike.objects.create(spike_train=spike_train,
                                      status=head_status_active,
                                      axoplasm={"var": "alpha"})
    spike_2 = Spike.objects.create(spike_train=spike_train,
                                      status=head_status_error,
                                      application_log="Fatal error on line 42")

    return {
        "spike_train": spike_train,
        "spike_1": spike_1,
        "spike_2": spike_2,
        "status_error_id": head_status_error.id
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_dynamic_routing(db_setup):
    """Ensures the ParietalMCP gateway actually routes to the correct file."""
    spike_id = str(db_setup["spike_1"].id)

    result = await ParietalMCP.execute("mcp_update_axoplasm", {
        "spike_id": spike_id,
        "key": "test_gateway",
        "value": "routed"
    })

    assert "Success" in result

    await asyncio.to_thread(db_setup["spike_1"].refresh_from_db)
    assert db_setup["spike_1"].axoplasm.get("test_gateway") == "routed"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_query_model_basic_filters(db_setup):
    """Ensures basic kwargs filtering works."""
    result = await ParietalMCP.execute(
        "mcp_query_model", {
            "model_name": "Spike",
            "filters": {
                "status_id": db_setup["status_error_id"]
            }
        })

    data = json.loads(result)
    assert len(data["records"]) == 1
    assert data["records"][0]["id"] == str(db_setup["spike_2"].id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_query_model_q_string_logic(db_setup):
    """Ensures the AI can write raw Q() objects for complex queries."""
    # Test an OR query that should return both spikes
    q_string = (f"Q(status_id={db_setup['status_error_id']}) | Q("
                f"axoplasm__var='alpha')")

    result = await ParietalMCP.execute("mcp_query_model", {
        "model_name": "Spike",
        "q_string": q_string
    })

    data = json.loads(result)
    assert len(data["records"]) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_query_model_count_action(db_setup):
    """Ensures the AI can request a raw integer count instead of heavy data."""
    result = await ParietalMCP.execute("mcp_query_model",
                                       {"model_name": "Spike"})

    data = json.loads(result)
    assert "Total Records:" in data["meta"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_inspect_record(db_setup):
    """Ensures the radar/stat checker correctly maps the schema and field
    sizes."""
    spike_id = str(db_setup["spike_2"].id)

    result = await ParietalMCP.execute("mcp_inspect_record", {
        "model_name": "Spike",
        "record_id": spike_id
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
    spike_id = str(db_setup["spike_2"].id)

    # 1. Search the log
    search_result = await ParietalMCP.execute(
        "mcp_search_record_field", {
            "app_label": "central_nervous_system",
            "model_name": "Spike",
            "record_id": spike_id,
            "field_name": "application_log",
            "pattern": "Fatal"
        })

    assert "Match 1" in search_result
    assert "Fatal error" in search_result

    # 2. Read the log
    read_result = await ParietalMCP.execute(
        "mcp_read_record_field", {
            "app_label": "central_nervous_system",
            "model_name": "Spike",
            "record_id": spike_id,
            "field_name": "application_log",
            "start_line": 1,
            "max_lines": 5
        })

    assert "1: Fatal error on line 42" in read_result
