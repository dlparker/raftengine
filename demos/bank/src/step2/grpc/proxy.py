import asyncio
import grpc
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType
from base.proxy_api import ProxyAPI
from base.msgpack_helpers import bank_msgpack_dumps, bank_msgpack_loads

# These will be generated from the proto file
from . import banking_pb2
from . import banking_pb2_grpc


class ServerProxy(ProxyAPI):
    """
    gRPC client proxy for banking operations with msgpack serialization
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None

    async def connect(self):
        """Connect to the gRPC server"""
        address = f'{self.host}:{self.port}'
        print(f"connecting to gRPC server at {address}")
        self.channel = grpc.aio.insecure_channel(address)
        self.stub = banking_pb2_grpc.BankingServiceStub(self.channel)
        print("connected to gRPC server")

    async def _ensure_connected(self):
        """Ensure we're connected to the server"""
        if self.stub is None:
            await self.connect()

    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        await self._ensure_connected()
        request = banking_pb2.CreateCustomerRequest(
            first_name=first_name,
            last_name=last_name,
            address=address
        )
        response = await self.stub.CreateCustomer(request)
        return bank_msgpack_loads(response.customer_data)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        await self._ensure_connected()
        request = banking_pb2.CreateAccountRequest(
            customer_id=customer_id,
            account_type=account_type.value
        )
        response = await self.stub.CreateAccount(request)
        return bank_msgpack_loads(response.account_data)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        await self._ensure_connected()
        request = banking_pb2.DepositRequest(
            account_id=account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.Deposit(request)
        return bank_msgpack_loads(response.balance)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        await self._ensure_connected()
        request = banking_pb2.WithdrawRequest(
            account_id=account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.Withdraw(request)
        return bank_msgpack_loads(response.balance)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        await self._ensure_connected()
        request = banking_pb2.TransferRequest(
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.Transfer(request)
        return bank_msgpack_loads(response.result)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        await self._ensure_connected()
        request = banking_pb2.CashCheckRequest(
            account_id=account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.CashCheck(request)
        return bank_msgpack_loads(response.balance)
    
    async def list_accounts(self) -> List[Account]:
        await self._ensure_connected()
        request = banking_pb2.ListAccountsRequest()
        response = await self.stub.ListAccounts(request)
        return bank_msgpack_loads(response.accounts)
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        await self._ensure_connected()
        request = banking_pb2.GetAccountsRequest(customer_id=customer_id)
        response = await self.stub.GetAccounts(request)
        return bank_msgpack_loads(response.account_ids)
    
    async def list_statements(self, account_id: int) -> List[date]:
        await self._ensure_connected()
        request = banking_pb2.ListStatementsRequest(account_id=account_id)
        response = await self.stub.ListStatements(request)
        return bank_msgpack_loads(response.dates)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        await self._ensure_connected()
        request = banking_pb2.AdvanceTimeRequest(
            delta_time=bank_msgpack_dumps(delta_time)
        )
        await self.stub.AdvanceTime(request)

    async def close(self):
        """Close the gRPC connection"""
        if self.channel:
            await self.channel.close()