import asyncio
import traceback
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


    async def do_command(self, command):
        raw_result = await self.raft_server.run_command(command)
        result = json.dumps(raw_result, default=lambda o:o.__dict__)
        return result

    async def local_command(self, command):
        raw_result = await self.raft_server.local_command(command)
        result = json.dumps(raw_result, default=lambda o:o.__dict__)
        return result

    async def do_raft(self, message):
        # we don't wait for the response, gets tricky with overlapping
        # calls
        asyncio.create_task(self.raft_server.raft_message(message))
        result = json.dumps(dict(result=None))
        return result
        
    async def go(self):
        try:
            while True:
                try:
                    len_data = await self.reader.read(20)
                    if not len_data:
                        break
                    msg_len = int(len_data.decode())
                    data = await self.reader.read(msg_len)
                    if not data:
                        break
                    # Process the line
                    request = json.loads(data.decode())
                    try:
                        if request['mtype'] == "command":
                            result = await self.do_command(request['message'])
                        elif request['mtype'] == "local_command":
                            result = await self.local_command(request['message'])
                        else:
                            result = await self.do_raft(request['message'])
                        response = result.encode()
                    except:
                        res = dict(result=None, error=traceback.format_exc())
                        result = json.dumps(res)
                        response = res.encode()
                    count = str(len(response))
                    self.writer.write(f"{count:20s}".encode())
                    self.writer.write(response)
                    await self.writer.drain()
                except asyncio.CancelledError:
                    # Server is shutting down, exit gracefully
                    break
                except Exception:
                    # Other errors, print and continue
                    traceback.print_exc()
                    break
        finally:
            # Always close the writer
            if not self.writer.is_closing():
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except asyncio.CancelledError:
                    pass

