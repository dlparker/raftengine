#!/usr/bin/env python
import asyncio
from src.server import Server
from src.proxy import ServerProxy, ServerWrapper
from src.client import Client


async def main():
    server = Server()
    wrapper = ServerWrapper(server)
    proxy = ServerProxy(wrapper)
    client = Client(proxy)
    
    
    print(await client.create_customer("Jones", "Bob", "1 Main Street, Hometown USA"))

asyncio.run(main())
      

