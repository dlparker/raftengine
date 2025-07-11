import asyncio
import grpc
from concurrent import futures
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal

from base.datatypes import Customer, Account, AccountType
from base.operations import Ops
from base.msgpack_helpers import bank_msgpack_dumps, bank_msgpack_loads

# These will be generated from the proto file
from . import step4_banking_pb2 as banking_pb2
from . import step4_banking_pb2_grpc as banking_pb2_grpc


class BankingServiceImpl(banking_pb2_grpc.BankingServiceServicer):
    """
    gRPC service implementation for banking operations with msgpack serialization
    """

    def __init__(self, server: Ops):
        self.server = server
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def _run_async(self, coro):
        """Helper to run async methods in the event loop"""
        return self.loop.run_until_complete(coro)

    async def CreateCustomer(self, request, context):
        """Create a new customer"""
        try:
            customer = await self.server.create_customer(
                request.first_name,
                request.last_name,
                request.address
            )
            return banking_pb2.CreateCustomerResponse(
                customer_data=bank_msgpack_dumps(customer)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.CreateCustomerResponse()

    async def CreateAccount(self, request, context):
        """Create a new account"""
        try:
            account_type = AccountType(request.account_type)
            account = await self.server.create_account(
                request.customer_id,
                account_type
            )
            return banking_pb2.CreateAccountResponse(
                account_data=bank_msgpack_dumps(account)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.CreateAccountResponse()

    async def Deposit(self, request, context):
        """Deposit money to an account"""
        try:
            amount = bank_msgpack_loads(request.amount)
            balance = await self.server.deposit(request.account_id, amount)
            return banking_pb2.DepositResponse(
                balance=bank_msgpack_dumps(balance)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.DepositResponse()

    async def Withdraw(self, request, context):
        """Withdraw money from an account"""
        try:
            amount = bank_msgpack_loads(request.amount)
            balance = await self.server.withdraw(request.account_id, amount)
            return banking_pb2.WithdrawResponse(
                balance=bank_msgpack_dumps(balance)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.WithdrawResponse()

    async def Transfer(self, request, context):
        """Transfer money between accounts"""
        try:
            amount = bank_msgpack_loads(request.amount)
            result = await self.server.transfer(
                request.from_account_id,
                request.to_account_id,
                amount
            )
            return banking_pb2.TransferResponse(
                result=bank_msgpack_dumps(result)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.TransferResponse()

    async def CashCheck(self, request, context):
        """Cash a check"""
        try:
            amount = bank_msgpack_loads(request.amount)
            balance = await self.server.cash_check(request.account_id, amount)
            return banking_pb2.CashCheckResponse(
                balance=bank_msgpack_dumps(balance)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.CashCheckResponse()

    async def ListAccounts(self, request, context):
        """List all accounts"""
        try:
            accounts = await self.server.list_accounts()
            return banking_pb2.ListAccountsResponse(
                accounts=bank_msgpack_dumps(accounts)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.ListAccountsResponse()

    async def GetAccounts(self, request, context):
        """Get account IDs for a customer"""
        try:
            account_ids = await self.server.get_accounts(request.customer_id)
            return banking_pb2.GetAccountsResponse(
                account_ids=bank_msgpack_dumps(account_ids)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.GetAccountsResponse()

    async def ListStatements(self, request, context):
        """List statement dates for an account"""
        try:
            dates = await self.server.list_statements(request.account_id)
            return banking_pb2.ListStatementsResponse(
                dates=bank_msgpack_dumps(dates)
            )
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.ListStatementsResponse()

    async def AdvanceTime(self, request, context):
        """Advance the server time"""
        try:
            delta_time = bank_msgpack_loads(request.delta_time)
            await self.server.advance_time(delta_time)
            return banking_pb2.AdvanceTimeResponse()
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.AdvanceTimeResponse()

    async def RaftMessage(self, request, context):
        """Handle Raft message"""
        try:
            response = f"echo: {request.message}"
            return banking_pb2.RaftMessageResponse(response=response)
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return banking_pb2.RaftMessageResponse()


async def create_server(host: str, port: int, banking_server: Ops):
    """Create and start a gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    banking_service = BankingServiceImpl(banking_server)
    banking_pb2_grpc.add_BankingServiceServicer_to_server(banking_service, server)
    
    listen_addr = f'{host}:{port}'
    server.add_insecure_port(listen_addr)
    
    return server