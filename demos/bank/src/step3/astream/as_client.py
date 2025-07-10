import asyncio

class ASClient:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def send_message(self, message):
        if self.reader is None:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        if not isinstance(message, str):
            raise Exception("Message must be string!")
        msg = message.encode()
        count = str(len(msg))
        self.writer.write(f"{count:20s}".encode())
        self.writer.write(msg)
        await self.writer.drain()
        len_data = (await self.reader.read(20))
        if not len_data:
            raise Exception('server gone!')
        msg_len = int(len_data.decode())
        data = await self.reader.read(msg_len)
        if not data:
            raise Exception('server gone!')
        return data.decode()
