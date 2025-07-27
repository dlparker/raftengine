import struct
from lsfs.block_writer import BlockWriter

class Recorder:
    def __init__(self, block_writer, cache_size=100):
        self.block_writer = block_writer
        self.cache_size = cache_size
        self.cache = []
        
    async def record(self, data_bytes, record_type_code):
        # Create record header
        record_header = struct.pack('<IIQ', 
                                  BlockWriter.MAGIC_RECORD,
                                  0,  # Will be filled by BlockWriter
                                  record_type_code)
        
        # Create incomplete record trailer (will be completed by BlockWriter)
        record_trailer = struct.pack('<IIQII',
                                   BlockWriter.MAGIC_RECORD,
                                   0,  # Will be filled by BlockWriter
                                   record_type_code,
                                   0,  # first_block_number - to be filled
                                   0)  # first_block_offset - to be filled
        
        # Submit to BlockWriter
        record_index = await self.block_writer.write_record(record_header, record_trailer, data_bytes)
        
        # Add to cache
        cache_entry = {
            'record_index': record_index,
            'record_type_code': record_type_code,
            'data_bytes': data_bytes
        }
        
        self.cache.append(cache_entry)
        
        # Maintain cache size
        if len(self.cache) > self.cache_size:
            self.cache.pop(0)
            
        return record_index
        
    async def get_cached_record(self, record_index):
        for entry in self.cache:
            if entry['record_index'] == record_index:
                return entry['data_bytes'], entry['record_type_code']
        return None, None
    
