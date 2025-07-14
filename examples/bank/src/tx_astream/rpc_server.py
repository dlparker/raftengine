import asyncio
import json


class RPCServer:

    def __init__(self, raft_server):
        self.raft_server = raft_server

    def get_raft_server(self):
        return self.raft_server
    
    async def handle_client(self, reader, writer):
        info = writer.get_extra_info("peername")
        cf = ClientFollower(self, reader, writer)
        asyncio.create_task(cf.go())

class ClientFollower:

    def __init__(self, rpc_server:RPCServer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.rpc_server = rpc_server
        self.reader = reader
        self.writer = writer
        self.raft_server = rpc_server.get_raft_server()
        self.info = writer.get_extra_info("peername")

    async def go(self):
        while True:
            len_data = await self.reader.read(20)
            if not len_data:
                break
            msg_len = int(len_data.decode())
            data = await self.reader.read(msg_len)
            if not data:
                break
            # Process the line
            request = json.loads(data.decode())
            
            if request['mtype'] == "command":
                command = request['message']
                result = await self.raft_server.run_command(command)
            else:
                result = await self.raft_server.raft_message(request['message'])
            response = result.encode()
            count = str(len(response))
            self.writer.write(f"{count:20s}".encode())
            self.writer.write(response)
            await self.writer.drain()

        self.writer.close()
        await self.writer.wait_closed()

