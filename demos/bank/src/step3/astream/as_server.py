import asyncio


class ASServer:

    def __init__(self, dispatcher,  port):
        self.dispatcher = dispatcher
        self.port = port
        print(f"asyncio_streams server on  {self.port}")

    async def handle_client(self, reader, writer):
        info = writer.get_extra_info("peername")
        print(f"Client connected f{info}")
        ascf = ASClientFollower(self, reader, writer)
        asyncio.create_task(ascf.go())

class ASClientFollower:

    def __init__(self, as_server:ASServer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.as_server = as_server
        self.reader = reader
        self.writer = writer
        self.dispatcher = as_server.dispatcher
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
            request = data.decode()
            result = await self.dispatcher.run_command(request)
            response = result.encode()
            count = str(len(response))
            self.writer.write(f"{count:20s}".encode())
            self.writer.write(response)
            await self.writer.drain()
    
        self.writer.close()
        await self.writer.wait_closed()
        print(self.info, "closed")

