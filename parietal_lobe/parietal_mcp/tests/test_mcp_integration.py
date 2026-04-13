import asyncio
import json
import uuid

import pytest

from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from parietal_lobe.parietal_mcp.gateway import ParietalMCP


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_file_operations(tmp_path):
    # Setup: Create a temporary file
    test_file = tmp_path / 'test_doc.txt'
    test_content = (
        'Line 1: Hello World\nLine 2: Testing MCP\nLine 3: End of file')
    test_file.write_text(test_content, encoding='utf-8')

    # We use the absolute path from tmp_path directly.
    # The tools no longer accept or need 'root_path'.
    absolute_file_path = str(test_file)
    absolute_dir_path = str(tmp_path)

    # 1. Test mcp_read_file
    print(f'Testing mcp_read_file with {absolute_file_path}')
    result = await ParietalMCP.execute('mcp_read_file',
                                       {'path': absolute_file_path})

    assert 'Line 1: Hello World' in result
    assert 'Line 2: Testing MCP' in result

    # 2. Test mcp_list_files
    print(f'Testing mcp_list_files in {absolute_dir_path}')
    result = await ParietalMCP.execute('mcp_list_files',
                                       {'path': absolute_dir_path})

    assert 'Listing for:' in result
    assert 'test_doc.txt' in result

    # 3. Test mcp_grep (formerly mcp_search_file)
    print(f'Testing mcp_grep in {absolute_file_path}')
    result = await ParietalMCP.execute('mcp_grep', {
        'path': absolute_file_path,
        'pattern': 'Testing'
    })

    assert '2:Line 2: Testing MCP' in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_record_operations():
    # Setup: Create required status models and spike_train

    # Create Statuses if they don't exist
    spike_status, _ = await asyncio.to_thread(
        SpikeStatus.objects.get_or_create,
        id=1,
        defaults={'name': 'Created'},
    )
    spike_train_status, _ = await asyncio.to_thread(
        SpikeTrainStatus.objects.get_or_create,
        id=1,
        defaults={'name': 'Created'},
    )

    # Create Spawn
    spike_train = await asyncio.to_thread(SpikeTrain.objects.create,
                                    status=spike_train_status)

    # Setup: Create a Spike
    spike_id = uuid.uuid4()

    spike = await asyncio.to_thread(
        Spike.objects.create,
        id=spike_id,
        spike_train=spike_train,
        status=spike_status,
        axoplasm={'initial': 'value'},
    )

    # 4. Test mcp_inspect_record
    print(f'Testing mcp_inspect_record for {spike_id}')
    result = await ParietalMCP.execute(
        'mcp_inspect_record',
        {
            'model_name': 'Spike',
            'record_id': str(spike_id),
        },
    )

    data = json.loads(result)
    assert data['id']['value'] == str(spike_id)
    assert 'axoplasm' in data
    assert 'value' in data['axoplasm']

    # 5. Test mcp_query_model (Basic Filters)
    print(f'Testing mcp_query_model for Spike')
    result = await ParietalMCP.execute(
        'mcp_query_model',
        {
            'model_name': 'Spike',
            'filters': {
                'id': str(spike_id)
            },
        },
    )

    data = json.loads(result)
    assert len(data['records']) == 1
    assert data['records'][0]['id'] == str(spike_id)

    # 5b. Test mcp_query_model (Q Objects & Count Action)
    print(f'Testing mcp_query_model Q() string and Count')
    q_string = f"Q(id='{str(spike_id)}') | Q(status__name='NonExistent')"
    result = await ParietalMCP.execute(
        'mcp_query_model',
        {
            'model_name': 'Spike',
            'q_string': q_string,
        },
    )

    data = json.loads(result)
    assert 'Total Records:' in data['meta']

    # 6. Test mcp_update_axoplasm
    print(f'Testing mcp_update_axoplasm for {spike_id}')
    new_key = 'status'
    new_value = 'active'
    result = await ParietalMCP.execute(
        'mcp_update_axoplasm',
        {
            'spike_id': str(spike_id),
            'key': new_key,
            'value': new_value
        },
    )

    assert 'Success' in result

    # Verify update
    await asyncio.to_thread(spike.refresh_from_db)
    assert spike.axoplasm.get(new_key) == new_value

    # 7. Test mcp_read_record_field
    print(f'Testing mcp_read_record_field for {spike_id}')
    result = await ParietalMCP.execute(
        'mcp_read_record_field',
        {
            'app_label': 'central_nervous_system',
            'model_name': 'Spike',
            'record_id': str(spike_id),
            'field_name': 'axoplasm',
        },
    )

    assert 'status' in result
    assert 'active' in result

    # 8. Test mcp_search_record_field
    print(f'Testing mcp_search_record_field for {spike_id}')
    result = await ParietalMCP.execute(
        'mcp_search_record_field',
        {
            'app_label': 'central_nervous_system',
            'model_name': 'Spike',
            'record_id': str(spike_id),
            'field_name': 'axoplasm',
            'pattern': 'active',
        },
    )

    assert 'Match 1' in result
    assert 'active' in result
