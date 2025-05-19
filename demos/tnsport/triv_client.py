#!/usr/bin/env python
import asyncio
import json

async def send_request(host, port, method, params):
    reader, writer = await asyncio.open_connection(host, port)
    request = json.dumps({'method': method, 'params': params}).encode()
    writer.write(request)
    await writer.drain()
    data = await reader.read(100)
    response = json.loads(data.decode())
    writer.close()
    return response['result']

async def send_request_list(host, port, requests):
    reader, writer = await asyncio.open_connection(host, port)
    for method, params in requests:
        request = json.dumps({'method': method, 'params': params}).encode()
        count = str(len(request))
        writer.write(f"{count:20s}".encode())
        writer.write(request)
        await writer.drain()
        data = await reader.read(100)
        response = json.loads(data.decode())
        print(response['result'])
    writer.close()


# Example usage
#result = asyncio.run(send_request('127.0.0.1', 8080, 'compute', [4, 5]))
requests = []
requests.append([ 'compute', [1, 2]])
requests.append([ 'compute', [2, 3]])
result = asyncio.run(send_request_list('127.0.0.1', 8080, requests))
print(result)
