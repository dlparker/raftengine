import asyncio
import grpc
from concurrent import futures
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from . import banking_pb2
from . import banking_pb2_grpc
from ...base.datatypes import Customer, Account, AccountType


class BankingServiceImpl(banking_pb2_grpc.BankingServiceServicer):
    """gRPC service implementation that wraps the banking server"""
    
    def __init__(self, server):
        self.server = server
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def _run_async(self, coro):
        """Helper to run async methods in sync gRPC context"""
        return self.loop.run_until_complete(coro)
    
    def _customer_to_proto(self, customer: Customer) -> banking_pb2.Customer:
        """Convert Customer dataclass to protobuf message"""
        return banking_pb2.Customer(
            cust_id=customer.cust_id,
            first_name=customer.first_name,
            last_name=customer.last_name,
            address=customer.address,
            accounts=customer.accounts,
            create_time=self._datetime_to_timestamp(customer.create_time),
            update_time=self._datetime_to_timestamp(customer.update_time)
        )
    
    def _account_to_proto(self, account: Account) -> banking_pb2.Account:
        """Convert Account dataclass to protobuf message"""
        # Convert AccountType enum
        account_type_map = {
            AccountType.SAVINGS: banking_pb2.ACCOUNT_TYPE_SAVINGS,
            AccountType.CHECKING: banking_pb2.ACCOUNT_TYPE_CHECKING
        }
        
        return banking_pb2.Account(
            account_id=account.account_id,
            account_type=account_type_map[account.account_type],
            customer_id=account.customer_id,
            balance=str(account.balance),
            create_time=self._datetime_to_timestamp(account.create_time),
            update_time=self._datetime_to_timestamp(account.update_time)
        )
    
    def _datetime_to_timestamp(self, dt: datetime):
        """Convert datetime to protobuf timestamp"""
        from google.protobuf.timestamp_pb2 import Timestamp
        timestamp = Timestamp()
        timestamp.FromDatetime(dt)
        return timestamp
    
    def _proto_to_account_type(self, proto_type) -> AccountType:
        """Convert protobuf AccountType to our enum"""
        type_map = {
            banking_pb2.ACCOUNT_TYPE_SAVINGS: AccountType.SAVINGS,
            banking_pb2.ACCOUNT_TYPE_CHECKING: AccountType.CHECKING
        }
        return type_map.get(proto_type, AccountType.CHECKING)
    
    def CreateCustomer(self, request, context):
        """Create a new customer"""
        try:
            customer = self._run_async(
                self.server.create_customer(
                    request.first_name,
                    request.last_name,
                    request.address
                )
            )
            return banking_pb2.CreateCustomerResponse(
                customer=self._customer_to_proto(customer)
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.CreateCustomerResponse()
    
    def CreateAccount(self, request, context):
        """Create a new account"""
        try:
            account_type = self._proto_to_account_type(request.account_type)
            account = self._run_async(
                self.server.create_account(request.customer_id, account_type)
            )
            return banking_pb2.CreateAccountResponse(
                account=self._account_to_proto(account)
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.CreateAccountResponse()
    
    def Deposit(self, request, context):
        """Deposit money to an account"""
        try:
            balance = self._run_async(
                self.server.deposit(request.account_id, Decimal(request.amount))
            )
            return banking_pb2.DepositResponse(balance=str(balance))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.DepositResponse()
    
    def Withdraw(self, request, context):
        """Withdraw money from an account"""
        try:
            balance = self._run_async(
                self.server.withdraw(request.account_id, Decimal(request.amount))
            )
            return banking_pb2.WithdrawResponse(balance=str(balance))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.WithdrawResponse()
    
    def Transfer(self, request, context):
        """Transfer money between accounts"""
        try:
            result = self._run_async(
                self.server.transfer(
                    request.from_account_id,
                    request.to_account_id,
                    Decimal(request.amount)
                )
            )
            return banking_pb2.TransferResponse(
                from_balance=str(result['from_balance']),
                to_balance=str(result['to_balance'])
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.TransferResponse()
    
    def CashCheck(self, request, context):
        """Cash a check"""
        try:
            balance = self._run_async(
                self.server.cash_check(request.account_id, Decimal(request.amount))
            )
            return banking_pb2.CashCheckResponse(balance=str(balance))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.CashCheckResponse()
    
    def ListAccounts(self, request, context):
        """List all accounts"""
        try:
            accounts = self._run_async(self.server.list_accounts())
            proto_accounts = [self._account_to_proto(account) for account in accounts]
            return banking_pb2.ListAccountsResponse(accounts=proto_accounts)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.ListAccountsResponse()
    
    def GetAccounts(self, request, context):
        """Get accounts for a customer"""
        try:
            account_ids = self._run_async(
                self.server.get_accounts(request.customer_id)
            )
            return banking_pb2.GetAccountsResponse(account_ids=account_ids)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.GetAccountsResponse()
    
    def ListStatements(self, request, context):
        """List statements for an account"""
        try:
            statements = self._run_async(
                self.server.list_statements(request.account_id)
            )
            statement_dates = [date.isoformat() for date in statements]
            return banking_pb2.ListStatementsResponse(statement_dates=statement_dates)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.ListStatementsResponse()
    
    def AdvanceTime(self, request, context):
        """Advance simulation time"""
        try:
            delta = timedelta(seconds=request.delta_seconds)
            self._run_async(self.server.advance_time(delta))
            return banking_pb2.AdvanceTimeResponse()
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return banking_pb2.AdvanceTimeResponse()


def serve_banking_server(server, port=50051):
    """Start the gRPC server"""
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    banking_pb2_grpc.add_BankingServiceServicer_to_server(
        BankingServiceImpl(server), grpc_server
    )
    listen_addr = f'[::]:{port}'
    grpc_server.add_insecure_port(listen_addr)
    grpc_server.start()
    print(f"Banking gRPC server listening on {listen_addr}")
    return grpc_server