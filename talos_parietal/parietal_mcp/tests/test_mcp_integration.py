import asyncio
import json
import uuid

import pytest

from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
)
from talos_parietal.parietal_mcp.gateway import ParietalMCP


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_file_operations(tmp_path):
    # Setup: Create a temporary file
    test_file = tmp_path / 'test_doc.txt'
    test_content = (
        'Line 1: Hello World\nLine 2: Testing MCP\nLine 3: End of file'
    )
    test_file.write_text(test_content, encoding='utf-8')

    # We use the absolute path from tmp_path directly.
    # The tools no longer accept or need 'root_path'.
    absolute_file_path = str(test_file)
    absolute_dir_path = str(tmp_path)

    # 1. Test mcp_read_file
    print(f'Testing mcp_read_file with {absolute_file_path}')
    result = await ParietalMCP.execute(
        'mcp_read_file', {'path': absolute_file_path}
    )

    assert 'Line 1: Hello World' in result
    assert 'Line 2: Testing MCP' in result

    # 2. Test mcp_list_files
    print(f'Testing mcp_list_files in {absolute_dir_path}')
    result = await ParietalMCP.execute(
        'mcp_list_files', {'path': absolute_dir_path}
    )

    assert 'Listing for:' in result
    assert 'test_doc.txt' in result

    # 3. Test mcp_grep (formerly mcp_search_file)
    print(f'Testing mcp_grep in {absolute_file_path}')
    result = await ParietalMCP.execute(
        'mcp_grep', {'path': absolute_file_path, 'pattern': 'Testing'}
    )

    assert '2:Line 2: Testing MCP' in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_record_operations():
    # Setup: Create required status models and spawn

    # Create Statuses if they don't exist
    head_status, _ = await asyncio.to_thread(
        HydraHeadStatus.objects.get_or_create,
        id=1,
        defaults={'name': 'Created'},
    )
    spawn_status, _ = await asyncio.to_thread(
        HydraSpawnStatus.objects.get_or_create,
        id=1,
        defaults={'name': 'Created'},
    )

    # Create Spawn
    spawn = await asyncio.to_thread(
        HydraSpawn.objects.create, status=spawn_status
    )

    # Setup: Create a HydraHead
    head_id = uuid.uuid4()

    head = await asyncio.to_thread(
        HydraHead.objects.create,
        id=head_id,
        spawn=spawn,
        status=head_status,
        blackboard={'initial': 'value'},
    )

    # 4. Test mcp_inspect_record
    print(f'Testing mcp_inspect_record for {head_id}')
    result = await ParietalMCP.execute(
        'mcp_inspect_record',
        {
            'app_label': 'hydra',
            'model_name': 'HydraHead',
            'record_id': str(head_id),
        },
    )

    data = json.loads(result)
    assert data['id']['value'] == str(head_id)
    assert 'blackboard' in data
    assert 'value' in data['blackboard']

    # 5. Test mcp_query_model (Basic Filters)
    print(f'Testing mcp_query_model for HydraHead')
    result = await ParietalMCP.execute(
        'mcp_query_model',
        {
            'app_label': 'hydra',
            'model_name': 'HydraHead',
            'filters': {'id': str(head_id)},
        },
    )

    data = json.loads(result)
    assert data['count_returned'] == 1
    assert data['records'][0]['id'] == str(head_id)

    # 5b. Test mcp_query_model (Q Objects & Count Action)
    print(f'Testing mcp_query_model Q() string and Count')
    q_string = f"Q(id='{str(head_id)}') | Q(status__name='NonExistent')"
    result = await ParietalMCP.execute(
        'mcp_query_model',
        {
            'app_label': 'hydra',
            'model_name': 'HydraHead',
            'q_string': q_string,
            'action': 'count',
        },
    )

    data = json.loads(result)
    assert 'count' in data
    assert data['count'] == 1

    # 6. Test mcp_update_blackboard
    print(f'Testing mcp_update_blackboard for {head_id}')
    new_key = 'status'
    new_value = 'active'
    result = await ParietalMCP.execute(
        'mcp_update_blackboard',
        {'head_id': str(head_id), 'key': new_key, 'value': new_value},
    )

    assert 'Success' in result

    # Verify update
    await asyncio.to_thread(head.refresh_from_db)
    assert head.blackboard.get(new_key) == new_value

    # 7. Test mcp_read_record_field
    print(f'Testing mcp_read_record_field for {head_id}')
    result = await ParietalMCP.execute(
        'mcp_read_record_field',
        {
            'app_label': 'hydra',
            'model_name': 'HydraHead',
            'record_id': str(head_id),
            'field_name': 'blackboard',
        },
    )

    assert 'status' in result
    assert 'active' in result

    # 8. Test mcp_search_record_field
    print(f'Testing mcp_search_record_field for {head_id}')
    result = await ParietalMCP.execute(
        'mcp_search_record_field',
        {
            'app_label': 'hydra',
            'model_name': 'HydraHead',
            'record_id': str(head_id),
            'field_name': 'blackboard',
            'pattern': 'active',
        },
    )

    assert 'Match 1' in result
    assert 'active' in result
