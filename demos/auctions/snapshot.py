import pickle
import os
import base64
import zlib
from itertools import islice

class StartStats:

    def __init__(self, start_ids: dict, end_ids: dict):
        self.start_ids = start_ids
        self.end_ids = end_ids

class SnapshotSerializer:

    def __init__(self, out_function=None, in_function=None):
        self.out_function = out_function
        self.in_function = in_function

    async def next_out_chunk(self, data:dict):
        if self.out_function is None:
            raise Exception("no output function, can't serialize")
        pickled = pickle.dumps(chunk)
        # compress
        compressed = zlib.compress(pickled)
        encoded = base64.a85encode(compressed).decode('ascii')
        await self.out_function(encoded)

    async def next_in_chunk(self, chunk:str):
        if self.in_function is None:
            raise Exception("no input function, can't deserialize")
        # Decode Base85
        compressed = base64.a85decode(chunk.encode('ascii'))
        # Decompress
        serialized = zlib.decompress(compressed)
        # Deserialize
        chunk_data = pickle.loads(serialized)
        await self.in_function(chunk_data)


        

def chunk_dict(data: dict, chunk_size: int):
    """Split a dictionary into chunks of approximately chunk_size items."""
    iterator = iter(data.items())
    while chunk := dict(islice(iterator, chunk_size)):
        yield chunk

def encode_snapshot(data: dict, chunk_size: int) -> list[str]:
    """Chunk a dictionary, pickle each chunk, and encode to Base85."""
    chunks = []
    for chunk in chunk_dict(data, chunk_size):
        # Pickle the chunk
        pickled = pickle.dumps(chunk)
        # Encode to Base85 (ASCII)
        encoded = base64.a85encode(pickled).decode('ascii')
        chunks.append(encoded)
    return chunks

def save_snapshot(chunks: list[str], snapshot_dir: str, snapshot_id: str):
    """Save encoded chunks to files."""
    os.makedirs(snapshot_dir, exist_ok=True)
    for i, chunk in enumerate(chunks):
        with open(os.path.join(snapshot_dir, f"snapshot_{snapshot_id}_chunk_{i}.txt"), "w") as f:
            f.write(chunk)

def send_snapshot_chunks(chunks: list[str], follower_id: str):
    """Send snapshot chunks to a follower (pseudo-code)."""
    for i, chunk in enumerate(chunks):
        message = {
            "type": "snapshot_chunk",
            "chunk_index": i,
            "total_chunks": len(chunks),
            "data": chunk,  # Base85-encoded ASCII string
            "snapshot_id": "some_unique_id"  # Raft term/index
        }
        # Send message to follower (e.g., via your existing Raft messaging)
        send_to_follower(follower_id, message)            

def decode_snapshot(chunks: list[str]) -> dict:
    """Decode Base85 chunks and reconstruct the dictionary."""
    result = {}
    for chunk in chunks:
        # Decode Base85 to binary
        pickled = base64.a85decode(chunk.encode('ascii'))
        # Unpickle to dictionary
        chunk_dict = pickle.loads(pickled)
        # Merge into result
        result.update(chunk_dict)
    return result

def receive_snapshot_chunk(message: dict, snapshot_dir: str):
    """Handle incoming snapshot chunk (pseudo-code)."""
    chunk_index = message["chunk_index"]
    snapshot_id = message["snapshot_id"]
    chunk_data = message["data"]

    # Save chunk to temporary file
    chunk_path = os.path.join(snapshot_dir, f"snapshot_{snapshot_id}_chunk_{chunk_index}.txt")
    with open(chunk_path, "w") as f:
        f.write(chunk_data)

    # Check if all chunks received
    total_chunks = message["total_chunks"]
    if len(os.listdir(snapshot_dir)) == total_chunks:
        # Reassemble snapshot
        chunks = []
        for i in range(total_chunks):
            with open(os.path.join(snapshot_dir, f"snapshot_{snapshot_id}_chunk_{i}.txt")) as f:
                chunks.append(f.read())
        snapshot = decode_snapshot(chunks)
        return snapshot
    return None


pickled = zlib.compress(pickle.dumps(chunk))
encoded = base64.a85encode(pickled).decode('ascii')


# Leader: Encode and send snapshot
data = {"key" + str(i): i for i in range(10000)}  # Large dictionary
chunks = encode_snapshot(data, chunk_size=1000)
save_snapshot(chunks, "snapshots", "term_5_index_100")
send_snapshot_chunks(chunks, "follower_1")

# Follower: Receive and decode
# (Assume chunks received via messages and stored)
chunks = [open(f"snapshots/snapshot_term_5_index_100_chunk_{i}.txt").read() for i in range(len(chunks))]
restored = decode_snapshot(chunks)
assert restored == data
