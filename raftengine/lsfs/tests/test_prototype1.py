import json
import random
import string
import os
import sys
import pytest
import pytest_asyncio
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from block_writer import BlockWriter
from recorder import Recorder
from block_reader import BlockReader


@pytest.fixture
def temp_file():
    fd, path = tempfile.mkstemp(suffix='.lsfs')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def generate_test_data():
    test_dict = {}
    for _ in range(5):
        key = random.choice(string.ascii_lowercase)
        value = random.randint(1, 1000)
        test_dict[key] = value
    
    json_str = json.dumps(test_dict)
    data_bytes = json_str.encode('utf-8')
    
    return data_bytes, test_dict


class TestPrototype1:
    
    @pytest.mark.asyncio
    async def test_single_record_write_and_read(self, temp_file):
        # Generate test data
        data_bytes, original_dict = generate_test_data()
        
        # Test writing
        block_writer = BlockWriter(temp_file)
        recorder = Recorder(block_writer)
        
        record_type_code = 42
        record_index = await recorder.record(data_bytes, record_type_code)
        
        assert record_index == 0
        await recorder.block_writer.close()
        
        # Test reading
        block_reader = BlockReader(temp_file)
        await block_reader.open()
        
        assert len(block_reader.catalog) == 1
        assert block_reader.first_record_index == 0
        assert block_reader.last_record_index == 0
        
        # Read back the record
        read_data, read_type_code = await block_reader.get_record(record_index)
        
        assert read_data is not None
        assert read_type_code == record_type_code
        
        # Deserialize and compare
        read_json = read_data.decode('utf-8')
        read_dict = json.loads(read_json)
        
        assert read_dict == original_dict
        
        await block_reader.close()

    @pytest.mark.asyncio
    async def test_multiple_records(self, temp_file):
        block_writer = BlockWriter(temp_file)
        recorder = Recorder(block_writer)
        
        records = []
        num_records = 10
        
        # Write multiple records
        for i in range(num_records):
            data_bytes, original_dict = generate_test_data()
            record_type_code = 100 + i
            record_index = await recorder.record(data_bytes, record_type_code)
            records.append((record_index, original_dict, record_type_code))
            assert record_index == i
        
        await recorder.block_writer.close()
        
        # Read back all records
        block_reader = BlockReader(temp_file)
        await block_reader.open()
        
        assert len(block_reader.catalog) == num_records
        assert block_reader.first_record_index == 0
        assert block_reader.last_record_index == num_records - 1
        
        # Verify all records
        for record_index, original_dict, expected_type_code in records:
            read_data, read_type_code = await block_reader.get_record(record_index)
            
            assert read_data is not None
            assert read_type_code == expected_type_code
            
            read_json = read_data.decode('utf-8')
            read_dict = json.loads(read_json)
            
            assert read_dict == original_dict
        
        await block_reader.close()

    @pytest.mark.asyncio
    async def test_recorder_cache(self, temp_file):
        block_writer = BlockWriter(temp_file)
        recorder = Recorder(block_writer, cache_size=3)
        
        # Write more records than cache size
        data_list = []
        for i in range(5):
            data_bytes, original_dict = generate_test_data()
            record_type_code = 200 + i
            record_index = await recorder.record(data_bytes, record_type_code)
            data_list.append((record_index, original_dict, record_type_code))
        
        # Cache should only contain last 3 records
        assert len(recorder.cache) == 3
        
        # Check cache contains records 2, 3, 4
        cached_indices = [entry['record_index'] for entry in recorder.cache]
        assert cached_indices == [2, 3, 4]
        
        # Test cache retrieval
        for i in range(2, 5):
            cached_data, cached_type = await recorder.get_cached_record(i)
            assert cached_data is not None
            assert cached_type == 200 + i
        
        # Earlier records should not be in cache
        cached_data, cached_type = await recorder.get_cached_record(0)
        assert cached_data is None
        assert cached_type is None
        
        await recorder.block_writer.close()

    @pytest.mark.asyncio
    async def test_nonexistent_record(self, temp_file):
        block_writer = BlockWriter(temp_file)
        recorder = Recorder(block_writer)
        
        # Write one record
        data_bytes, _ = generate_test_data()
        await recorder.record(data_bytes, 42)
        await recorder.block_writer.close()
        
        # Try to read nonexistent record
        block_reader = BlockReader(temp_file)
        await block_reader.open()
        
        read_data, read_type_code = await block_reader.get_record(999)
        assert read_data is None
        assert read_type_code is None
        
        await block_reader.close()

    @pytest.mark.asyncio
    async def test_empty_data(self, temp_file):
        block_writer = BlockWriter(temp_file)
        recorder = Recorder(block_writer)
        
        # Write empty data
        empty_data = b''
        record_type_code = 1
        record_index = await recorder.record(empty_data, record_type_code)
        
        await recorder.block_writer.close()
        
        # Read back empty data
        block_reader = BlockReader(temp_file)
        await block_reader.open()
        
        read_data, read_type_code = await block_reader.get_record(record_index)
        
        assert read_data == empty_data
        assert read_type_code == 1
        
        await block_reader.close()