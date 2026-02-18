import pytest
import os
import uuid
import json
import asyncio
from django.conf import settings
from hydra.models import HydraHead
from talos_parietal.parietal_mcp.gateway import ParietalMCP


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_file_operations(tmp_path):
    # Setup: Create a temporary file
    test_file = tmp_path / "test_doc.txt"
    test_content = "Line 1: Hello World\nLine 2: Testing MCP\nLine 3: End of file"
    test_file.write_text(test_content, encoding="utf-8")

    # We need to temporarily override settings.BASE_DIR or use a relative path if possible
    # But the MCP strict checks BASE_DIR. Let's try passing the tmp_path as root_path to the MCP if it supports it.
    # Looking at mcp_read_file: def mcp_read_file(path: str, start_line: int = 1, max_lines: int = 50, root_path: str = None)

    root_path = str(tmp_path)
    file_name = "test_doc.txt"

    # 1. Test mcp_read_file
    print(f"Testing mcp_read_file with {file_name} in {root_path}")
    result = await ParietalMCP.execute("mcp_read_file", {
        "path": file_name,
        "root_path": root_path
    })

    assert "Line 1: Hello World" in result
    assert "Line 2: Testing MCP" in result

    # 2. Test mcp_list_files
    print(f"Testing mcp_list_files in {root_path}")
    result = await ParietalMCP.execute(
        "mcp_list_files",
        {
            "path": ".",  # Check root of the provided root_path
            "root_path": root_path
        })

    assert "Listing for:" in result
    assert "test_doc.txt" in result

    # 3. Test mcp_search_file
    print(f"Testing mcp_search_file in {file_name}")
    result = await ParietalMCP.execute("mcp_search_file", {
        "path": file_name,
        "pattern": "Testing",
        "root_path": root_path
    })

    assert "Match 1" in result
    assert "Line 2" in result
    assert "Testing MCP" in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_record_operations():
    # Setup: Create required status models and spawn
    from hydra.models import HydraHeadStatus, HydraSpawnStatus, HydraSpawn

    # Create Statuses if they don't exist (using IDs to match constants)
    head_status, _ = await asyncio.to_thread(
        HydraHeadStatus.objects.get_or_create,
        id=1,
        defaults={'name': 'Created'})
    spawn_status, _ = await asyncio.to_thread(
        HydraSpawnStatus.objects.get_or_create,
        id=1,
        defaults={'name': 'Created'})

    # Create Spawn
    spawn = await asyncio.to_thread(HydraSpawn.objects.create,
                                    status=spawn_status)

    # Setup: Create a HydraHead
    head_id = uuid.uuid4()

    head = await asyncio.to_thread(HydraHead.objects.create,
                                   id=head_id,
                                   spawn=spawn,
                                   status=head_status,
                                   blackboard={"initial": "value"})

    # 4. Test mcp_inspect_record
    print(f"Testing mcp_inspect_record for {head_id}")
    result = await ParietalMCP.execute("mcp_inspect_record", {
        "app_label": "hydra",
        "model_name": "HydraHead",
        "record_id": str(head_id)
    })

    # Verify result is valid JSON and contains fields
    data = json.loads(result)
    assert data["id"]["value"] == str(head_id)
    assert "blackboard" in data
    assert "value" in data["blackboard"]

    # 5. Test mcp_query_model
    print(f"Testing mcp_query_model for HydraHead")
    result = await ParietalMCP.execute(
        "mcp_query_model", {
            "app_label": "hydra",
            "model_name": "HydraHead",
            "filters": {
                "id": str(head_id)
            }
        })

    data = json.loads(result)
    assert data["count_returned"] == 1
    assert data["records"][0]["id"] == str(head_id)

    # 6. Test mcp_update_blackboard
    print(f"Testing mcp_update_blackboard for {head_id}")
    new_key = "status"
    new_value = "active"
    result = await ParietalMCP.execute("mcp_update_blackboard", {
        "head_id": str(head_id),
        "key": new_key,
        "value": new_value
    })

    assert "Success" in result

    # Verify update
    await asyncio.to_thread(head.refresh_from_db)
    assert head.blackboard.get(new_key) == new_value

    # 7. Test mcp_read_record_field (reading the blackboard as string representation)
    # Blackboard is a JSONField/Dict, so it gets converted to string
    print(f"Testing mcp_read_record_field for {head_id}")
    result = await ParietalMCP.execute(
        "mcp_read_record_field", {
            "app_label": "hydra",
            "model_name": "HydraHead",
            "record_id": str(head_id),
            "field_name": "blackboard"
        })

    assert "status" in result
    assert "active" in result

    # 8. Test mcp_search_record_field
    print(f"Testing mcp_search_record_field for {head_id}")
    result = await ParietalMCP.execute(
        "mcp_search_record_field", {
            "app_label": "hydra",
            "model_name": "HydraHead",
            "record_id": str(head_id),
            "field_name": "blackboard",
            "pattern": "active"
        })

    assert "Match 1" in result
    assert "active" in result
