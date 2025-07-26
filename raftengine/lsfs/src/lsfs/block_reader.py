import struct
from lsfs.block_writer import BlockWriter

class BlockReader:
    def __init__(self, filename):
        self.filename = filename
        self.catalog = {}
        self.first_record_index = None
        self.last_record_index = None
        self.file = None
        
    async def open(self):
        self.file = open(self.filename, 'rb')
        await self._build_catalog()
        
    async def _build_catalog(self):
        self.file.seek(0)
        block_number = 0
        
        while True:
            block_data = self.file.read(BlockWriter.BLOCK_SIZE)
            if not block_data or len(block_data) < BlockWriter.BLOCK_SIZE:
                break
                
            await self._process_block(block_data, block_number)
            block_number += 1
            
    async def _process_block(self, block_data, block_number):
        # Read block header
        magic, byte_count = struct.unpack('<II', block_data[:8])
        if magic != BlockWriter.MAGIC_BLOCK:
            print(f"Invalid block magic in block {block_number}")
            return
            
        # Read block trailer
        trailer_magic, trailer_byte_count, last_slice_start = struct.unpack('<III', block_data[-12:])
        if trailer_magic != BlockWriter.MAGIC_BLOCK:
            print(f"Invalid block trailer magic in block {block_number}")
            return
            
        # Process slices in the block
        pos = 8  # Skip block header
        
        while pos < 8 + byte_count:
            if pos + 12 > len(block_data):
                break
                
            # Read slice header
            slice_magic, record_index, slice_number = struct.unpack('<III', block_data[pos:pos+12])
            if slice_magic != BlockWriter.MAGIC_SLICE:
                break
                
            pos += 12
            
            # Find slice trailer by scanning backwards from end of data
            slice_trailer_pos = None
            for scan_pos in range(min(pos + 1000, 8 + byte_count - 16), pos - 1, -1):
                if scan_pos + 16 <= len(block_data):
                    trailer_data = block_data[scan_pos:scan_pos+16]
                    trailer_magic, trailer_record_index, trailer_slice_number, block_offset = struct.unpack('<IIII', trailer_data)
                    if (trailer_magic == BlockWriter.MAGIC_SLICE and 
                        trailer_record_index == record_index and
                        trailer_slice_number == slice_number):
                        slice_trailer_pos = scan_pos
                        break
                        
            if slice_trailer_pos is None:
                print(f"Could not find slice trailer for record {record_index}, slice {slice_number}")
                break
                
            # Extract slice content
            slice_content = block_data[pos:slice_trailer_pos]
            
            # Update catalog
            if record_index not in self.catalog:
                self.catalog[record_index] = {
                    'record_index': record_index,
                    'record_type_code': None,
                    'first_slice_location': (block_number, pos - 12),
                    'last_slice_location': (block_number, slice_trailer_pos),
                    'slices': []
                }
                
            self.catalog[record_index]['slices'].append({
                'slice_number': slice_number,
                'block_number': block_number,
                'content': slice_content,
                'start_offset': pos - 12
            })
            
            # Update last slice location
            self.catalog[record_index]['last_slice_location'] = (block_number, slice_trailer_pos)
            
            pos = slice_trailer_pos + 16
            
        # Update first/last record indices
        record_indices = list(self.catalog.keys())
        if record_indices:
            self.first_record_index = min(record_indices)
            self.last_record_index = max(record_indices)
            
    async def get_record(self, record_index):
        if record_index not in self.catalog:
            return None, None
            
        record_info = self.catalog[record_index]
        
        # Sort slices by slice number
        slices = sorted(record_info['slices'], key=lambda x: x['slice_number'])
        
        # Reconstruct the sausage
        sausage_content = b''.join(slice_data['content'] for slice_data in slices)
        
        # Parse record header to get type code
        if len(sausage_content) >= 16:
            magic, rec_idx, type_code = struct.unpack('<IIQ', sausage_content[:16])
            if magic == BlockWriter.MAGIC_RECORD:
                # Find record trailer and extract data
                # Record trailer is at the end: magic(4) + record_index(4) + type_code(8) + first_block(4) + first_offset(4)
                if len(sausage_content) >= 40:  # min size for header + trailer
                    trailer_start = len(sausage_content) - 24
                    data_bytes = sausage_content[16:trailer_start]
                    return data_bytes, type_code
                    
        return None, None
        
    async def close(self):
        if self.file:
            self.file.close()
            self.file = None
