import struct
import asyncio

class BlockWriter:
    BLOCK_SIZE = 4096
    MAGIC_BLOCK = 0x424C4B00  # 'BLK\0'
    MAGIC_RECORD = 0x52454300  # 'REC\0'
    MAGIC_SLICE = 0x534C4300   # 'SLC\0'
    
    def __init__(self, filename, min_content_size=64):
        self.filename = filename
        self.min_content_size = min_content_size
        self.block_buffer = bytearray(self.BLOCK_SIZE)
        self.buffer_pos = 0
        self.record_index = 0
        self.first_record_index = 0
        self.last_record_index = -1
        self.file = None
        self.block_number = 0
        
    async def open(self):
        self.file = open(self.filename, 'wb')
        
    async def write_record(self, record_header, record_trailer, data_bytes):
        if self.file is None:
            await self.open()
            
        # Create sausage content
        sausage_content = record_header + data_bytes + record_trailer
        content_size = len(sausage_content)
        
        # Calculate slice overhead
        slice_header_size = 12  # magic(4) + record_index(4) + slice_number(4)
        slice_trailer_size = 16  # magic(4) + record_index(4) + slice_number(4) + block_offset(4)
        slice_overhead = slice_header_size + slice_trailer_size
        
        remaining_sausage = sausage_content
        slice_number = 0
        current_record_index = self.record_index
        
        while remaining_sausage:
            available_space = self.BLOCK_SIZE - self.buffer_pos
            trial_slice_size = len(remaining_sausage) + slice_overhead
            
            if trial_slice_size <= available_space:
                # Entire remaining sausage fits
                slice_content = remaining_sausage
                remaining_sausage = b''
            else:
                # Need to slice
                max_content_size = available_space - slice_overhead
                slice_content = remaining_sausage[:max_content_size]
                remaining_sausage = remaining_sausage[max_content_size:]
            
            # Create slice header
            slice_header = struct.pack('<III', self.MAGIC_SLICE, current_record_index, slice_number)
            
            # Create slice trailer
            slice_start_offset = self.buffer_pos
            slice_trailer = struct.pack('<IIII', self.MAGIC_SLICE, current_record_index, slice_number, slice_start_offset)
            
            # Write slice to buffer
            slice_data = slice_header + slice_content + slice_trailer
            slice_size = len(slice_data)
            
            self.block_buffer[self.buffer_pos:self.buffer_pos + slice_size] = slice_data
            self.buffer_pos += slice_size
            
            slice_number += 1
            
            # Check if we need to flush buffer
            min_space_needed = (slice_header_size + slice_trailer_size + 
                              20 + 24 +  # record header + trailer sizes
                              self.min_content_size)
            
            if (self.BLOCK_SIZE - self.buffer_pos) < min_space_needed:
                await self._flush_buffer()
        
        self.last_record_index = current_record_index
        self.record_index += 1
        return current_record_index
        
    async def _flush_buffer(self):
        if self.buffer_pos > 0:
            # Create block header
            block_header = struct.pack('<II', self.MAGIC_BLOCK, self.buffer_pos)
            
            # Find last slice start (simplified - just use current pos)
            last_slice_start = max(0, self.buffer_pos - 32)  # approximate
            
            # Create block trailer
            block_trailer = struct.pack('<III', self.MAGIC_BLOCK, self.buffer_pos, last_slice_start)
            
            # Pad buffer and add header/trailer
            padded_buffer = bytearray(self.BLOCK_SIZE)
            padded_buffer[:8] = block_header
            padded_buffer[8:8 + self.buffer_pos] = self.block_buffer[:self.buffer_pos]
            padded_buffer[-12:] = block_trailer
            
            # Write to file
            self.file.write(padded_buffer)
            self.file.flush()
            
            # Reset buffer
            self.block_buffer = bytearray(self.BLOCK_SIZE)
            self.buffer_pos = 0
            self.block_number += 1
            
    async def flush(self):
        await self._flush_buffer()
        
    async def close(self):
        await self.flush()
        if self.file:
            self.file.close()
            self.file = None

            
