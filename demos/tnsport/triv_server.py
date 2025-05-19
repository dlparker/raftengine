#!/usr/bin/env python
import asyncio
import json

async def compute(var1, var2):
    result = var1 + var2
    return result

async def read_until_closed(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        len_data = await reader.read(20)
        if not len_data:
            break
        msg_len = int(len_data.decode())
        data = await reader.read(msg_len)
        if not data:
            break
        # Process the line
        request = json.loads(data.decode())
        method = request['method']
        params = request['params']
        result = await compute(*params)
        writer.write(json.dumps({'result': result}).encode())
        await writer.drain()

async def main():
    # Example usage with a dummy server
    server = await asyncio.start_server(
        handle_client, '127.0.0.1', 8080)

    async with server:
        await server.serve_forever()

async def handle_client(reader, writer):
    info = writer.get_extra_info("peername")
    print(f"Client connected f{info}")
    await read_until_closed(reader, writer)
    writer.close()
    await writer.wait_closed()
    print(f"Client disconnected f{info}")

if __name__ == "__main__":
    asyncio.run(main())
    
