import asyncio
import time
import json
import traceback
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult


class RPCClient(RPCAPI):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.in_progress = False

    async def send_message(self, message):
        try:
            start_time = time.time()
            while self.in_progress:
                await asyncio.sleep(0.00001)
                if time.time() - start_time > 3:
                    raise Exception('too long waiting for in progress to clear')
            self.in_progress = True
            if self.reader is None:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            if not isinstance(message, str):
                self.in_progress = False
                raise Exception("Message must be string!")
            msg = message.encode()
            count = str(len(msg))
            self.writer.write(f"{count:20s}".encode())
            self.writer.write(msg)
            await self.writer.drain()
            len_data = (await self.reader.read(20))
            if not len_data:
                self.in_progress = False
                raise Exception('server gone!')
            msg_len = int(len_data.decode())
            data = await self.reader.read(msg_len)
            if not data:
                self.in_progress = False
                raise Exception('server gone!')
            self.in_progress = False
            return data.decode()
        except:
            traceback.print_exc()
            raise

    async def run_command(self, command):
        wrapped = dict(mtype="command", message=command)
        msg = json.dumps(wrapped)
        res =  await self.send_message(msg)
        result = CommandResult(**json.loads(res))
        return result

    async def raft_message(self, message):
        wrapped = dict(mtype="raft_message", message=message)
        msg = json.dumps(wrapped)
        await self.send_message(msg)
        return None
    
    async def close(self):
        """Close the connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None
            
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
