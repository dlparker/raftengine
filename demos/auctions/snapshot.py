#!/usr/bin/env python
import asyncio
import sys
import sqlite3
import pickle
import os
import base64
import zlib
from pathlib import Path
from itertools import islice
from typing import Optional
from dataclasses import dataclass, field
from pprint import pprint
from records import Records, Person, Item, Sale, Bid

@dataclass
class ChunkObjs:
    items: Optional[list] = field(default=None) 
    people: Optional[list] = field(default=None) 
    sales: Optional[list] = field(default=None) 
    bids: Optional[list] = field(default=None) 

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


class SnapshotTool:

    def __init__(self, records):
        self.records = records

    async def start(self):
        await self.make_snap_db()

    async def make_snap_db(self):
        snap_records = self.records.take_snapshot()
        db_dir = Path(__file__).parent
        self.db_path = Path(db_dir, 'auction.snapshot.db')
        if self.db_path.exists():
            self.db_path.unlink()
        self.db = sqlite3.connect(self.db_path,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row

        cursor = self.db.cursor()
        cursor.execute('create table chunks (chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, data BLOB)')

        items_offset = people_offset = sales_offset = bids_offset = 0
        items_done = people_done = sales_done = bids_done = False
        self.totals = dict(full=0, pickled=0, compressed=0, encoded=0)
        while True:
            co = ChunkObjs()
            if not items_done:
                items = snap_records.fetch_items(items_offset, 10)
                if len(items) == 0:
                    items_done = True
                else:
                    items_offset += len(items)
                co.items = items

            if not people_done:
                people = snap_records.fetch_people(people_offset, 10)
                if len(people) == 0:
                    people_done = True
                else:
                    people_offset += len(people)
                co.people = people
        
            if not sales_done:
                sales = snap_records.fetch_sales(sales_offset, 10)
                if len(sales) == 0:
                    sales_done = True
                else:
                    sales_offset += len(sales)
                co.sales = sales

            if not bids_done:
                bids = snap_records.fetch_bids(bids_offset, 10)
                if len(bids) == 0:
                    bids_done = True
                else:
                    bids_offset += len(bids)
                co.bids = bids

            if items_done and people_done and sales_done and bids_done:
                break

            pickled = pickle.dumps(co)
            compressed = zlib.compress(pickled)
            self.totals['full'] += get_size(co)
            self.totals['pickled'] += len(pickled)
            self.totals['compressed'] += len(compressed)
            cursor.execute('insert into chunks (data) values (?)', [compressed,])
        self.db.commit()
        cursor.close()
                       
    async def get_chunk_encoded(self, index=0):
        index += 1
        cursor = self.db.cursor()
        cursor.execute('select min(chunk_id) as min_id, max(chunk_id) as max_id from chunks')
        row = cursor.fetchone()
        if index >= row['min_id'] and index <= row['max_id']:
            cursor.execute("select * from chunks where chunk_id = ?", (index,))
            row = cursor.fetchone()
            encoded = base64.a85encode(row['data']).decode('ascii')
            self.totals['encoded'] += len(encoded)
            return row['chunk_id'], encoded
        return -1, None

async def example(st):
    await st.start()
    last_index = 0
    while last_index > -1:
        last_index, chunk = await st.get_chunk_encoded(last_index)
        if last_index > -1:
            compressed = base64.a85decode(chunk.encode('ascii'))
            serialized = zlib.decompress(compressed)
            chunk_data = pickle.loads(serialized)
            #pprint(chunk_data)


    print(f"full = {st.totals['full']} pickled = {st.totals['pickled']} compressed = {st.totals['compressed']} encoded = {st.totals['encoded']}")
    # now fake collecting a snap shot from another server and creating local db
    db_dir = Path(__file__).parent
    snap_db_path = Path(db_dir, 'in.auction.snapshot.db')
    if snap_db_path.exists():
        snap_db_path.unlink()
    snap_db = sqlite3.connect(snap_db_path,
                              detect_types=sqlite3.PARSE_DECLTYPES |
                              sqlite3.PARSE_COLNAMES)
    snap_db.row_factory = sqlite3.Row
    cursor = snap_db.cursor()
    cursor.execute('create table chunks (chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, data BLOB)')
    records = Records(base_dir=Path(db_dir), clear=True, db_file_name="in.auction.db")
    last_index = 0
    while last_index > -1:
        last_index, chunk = await st.get_chunk_encoded(last_index)
        if last_index > -1:
            compressed = base64.a85decode(chunk.encode('ascii'))
            # save it in snap db, as we would do so that we could share it with other nodes
            cursor.execute('insert into chunks (chunk_id, data) values (?,?)', [last_index, compressed,])
            serialized = zlib.decompress(compressed)
            chunk_data = pickle.loads(serialized)
            if chunk_data.items:
                for item in chunk_data.items:
                    records.add_item(item)
            if chunk_data.people:
                for person in chunk_data.people:
                    records.add_person(person)
            if chunk_data.sales:
                for sale in chunk_data.sales:
                    records.add_sale(sale)
            if chunk_data.bids:
                for bid in chunk_data.bids:
                    records.add_bid(bid)
    
    
def get_size(obj, seen=None):
    """Recursively finds size of objects"""
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_size(v, seen) + get_size(k, seen) for k, v in obj.items()])
    elif hasattr(obj, '__dict__'):
        size += get_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_size(i, seen) for i in obj])
    return size
    
if __name__=="__main__":
    db_dir = Path(__file__).parent
    records = Records(base_dir=Path(db_dir), clear=False)
    st = SnapshotTool(records)
    asyncio.run(example(st))



    
