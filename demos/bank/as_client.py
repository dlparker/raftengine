#!/usr/bin/env python
import asyncio
from src.base.client import Client
from src.transports.astream.proxy import ASClient, ServerProxy

async def main():
    as_client = ASClient('localhost', 9999)
    proxy = ServerProxy(as_client)
    client = Client(proxy)
    print(await client.create_customer("Jones", "Bob", "1 Main Street, Hometown USA"))

asyncio.run(main())
      

