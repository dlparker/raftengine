#!/usr/bin/env python
import asyncio
from src.base.server import Server
from src.transports.astream.proxy import ASServer

async def main():
    server = Server()
    as_server = ASServer(server, '127.0.0.1', 9999)
    
    sock_server = await asyncio.start_server(
        as_server.handle_client, '127.0.0.1', 9999)

    async with sock_server:
        await sock_server.serve_forever()

asyncio.run(main())
      

