import asyncio
import logging
import grpc
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType
from step5.base_plus.proxy_api import OpsProxyAPI
from base.msgpack_helpers import bank_msgpack_dumps, bank_msgpack_loads
from raftengine.api.deck_api import CommandResult

# These will be generated from the proto file
from . import step5_banking_pb2 as banking_pb2
from . import step5_banking_pb2_grpc as banking_pb2_grpc

logger = logging.getLogger("gRPC")

class RPCClient(OpsProxyAPI):
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
        logger.debug(f"connecting to gRPC server at {address}")
        self.channel = grpc.aio.insecure_channel(address)
        self.stub = banking_pb2_grpc.BankingServiceStub(self.channel)
        logger.debug("connected to gRPC server")

    async def _ensure_connected(self):
        """Ensure we're connected to the server"""
        if self.stub is None:
            await self.connect()
    
    def _convert_response(self, pb_result):
        """Convert protobuf CommandResult to raftengine CommandResult"""
        # Convert msgpack bytes to JSON string for proxy decorator
        result_str = None
        if pb_result.result:
            # Deserialize msgpack to get the object, then serialize to JSON
            obj = bank_msgpack_loads(pb_result.result)
            from base.json_helpers import bank_json_dumps
            result_str = bank_json_dumps(obj)
        
        # Handle redirect: protobuf has separate boolean + string, CommandResult uses string
        redirect_addr = None
        if pb_result.redirect and pb_result.redirect_to:
            redirect_addr = pb_result.redirect_to
        
        return CommandResult(
            command="banking_operation",  # Generic command name
            error=pb_result.error if pb_result.error else None,
            redirect=redirect_addr,
            retry=pb_result.retry,
            result=result_str
        )

    async def create_customer(self, first_name: str, last_name: str, address: str) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.CreateCustomerRequest(
            first_name=first_name,
            last_name=last_name,
            address=address
        )
        response = await self.stub.CreateCustomer(request)
        return self._convert_response(response)

    async def create_account(self, customer_id: str, account_type: AccountType) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.CreateAccountRequest(
            customer_id=customer_id,
            account_type=account_type.value
        )
        response = await self.stub.CreateAccount(request)
        return self._convert_response(response)

    async def deposit(self, account_id: int, amount: Decimal) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.DepositRequest(
            account_id=account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.Deposit(request)
        return self._convert_response(response)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.WithdrawRequest(
            account_id=account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.Withdraw(request)
        return self._convert_response(response)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.TransferRequest(
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.Transfer(request)
        return self._convert_response(response)

    async def cash_check(self, account_id: int, amount: Decimal) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.CashCheckRequest(
            account_id=account_id,
            amount=bank_msgpack_dumps(amount)
        )
        response = await self.stub.CashCheck(request)
        return self._convert_response(response)
    
    async def list_accounts(self) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.ListAccountsRequest()
        response = await self.stub.ListAccounts(request)
        return self._convert_response(response)
    
    async def get_accounts(self, customer_id: str) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.GetAccountsRequest(customer_id=customer_id)
        response = await self.stub.GetAccounts(request)
        return self._convert_response(response)
    
    async def list_statements(self, account_id: int) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.ListStatementsRequest(account_id=account_id)
        response = await self.stub.ListStatements(request)
        return self._convert_response(response)
    
    async def advance_time(self, delta_time: timedelta) -> CommandResult:
        await self._ensure_connected()
        request = banking_pb2.AdvanceTimeRequest(
            delta_time=bank_msgpack_dumps(delta_time)
        )
        response = await self.stub.AdvanceTime(request)
        return self._convert_response(response)
    
    async def raft_message(self, message: str) -> str:
        await self._ensure_connected()
        request = banking_pb2.RaftMessageRequest(message=message)
        response = await self.stub.RaftMessage(request)
        #logger.debug(f"sent raft message {request} got {response.response}")
        return response.response

    async def close(self):
        """Close the gRPC connection"""
        if self.channel:
            await self.channel.close()
