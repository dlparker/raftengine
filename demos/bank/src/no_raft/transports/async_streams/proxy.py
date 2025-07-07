import asyncio
from operator import methodcaller
from typing import List, Optional, Dict, Any
from datetime import timedelta, date
from decimal import Decimal

from src.base.client import Client
from src.base.datatypes import Customer, Account, AccountType, CommandType
from src.base.proxy_api import ProxyAPI
from src.base.json_helpers import bank_json_dumps, bank_json_loads


class ASClient:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def do_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        if self.reader is None:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        send_data = dict(command_name=command_name, args=argsdict)
        request = bank_json_dumps(send_data).encode()
        count = str(len(request))
        self.writer.write(f"{count:20s}".encode())
        self.writer.write(request)
        await self.writer.drain()
        len_data = await self.reader.read(20)
        if not len_data:
            raise Exception('server gone!')
        msg_len = int(len_data.decode())
        data = await self.reader.read(msg_len)
        if not data:
            raise Exception('server gone!')
        # Process the response
        response = bank_json_loads(data.decode())
        return response

    async def close(self):
        self.writer.close()

class ASServer:

    def __init__(self, server, addr, port):
        self.server = server
        self.addr = addr
        self.port = port
        self.clients = {}
        print(f"server on {self.addr} {self.port}")

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
            request = bank_json_loads(data.decode())
            result = await self.do_command(request['command_name'], request['args'])
            response = bank_json_dumps(result).encode()
            count = str(len(response))
            self.writer.write(f"{count:20s}".encode())
            self.writer.write(response)
            await self.writer.drain()
    
        self.writer.close()
        await self.writer.wait_closed()
        print(self.info, "closed")

    async def do_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        callable_method = methodcaller(command_name, **argsdict)
        res = await callable_method(self.as_server.server)
        return res
    
class ServerProxy(ProxyAPI):

    def __init__(self, as_client: ASClient) -> None:
        self.as_client = as_client
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.CREATE_CUSTOMER, args)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.CREATE_ACCOUNT, args)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.DEPOSIT, args)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.WITHDRAW, args)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.TRANSFER, args)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.CASH_CHECK, args)
    
    async def list_accounts(self) -> List[Account]:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.LIST_ACCOUNTS, args)
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.GET_ACCOUNTS, args)
    
    async def list_statements(self, account_id: int) -> List[date]:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.LIST_STATEMENTS, args)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        args = locals()
        del args['self']
        return await self.as_client.do_command(CommandType.ADVANCE_TIME, args)


def get_astream_client(host: str, port: int):
    """Create an async streams client"""
    as_client = ASClient(host, port)
    proxy = ServerProxy(as_client)
    client = Client(proxy)

    async def cleanup():
        await as_client.close()

    return client, cleanup
