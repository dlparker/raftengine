import grpc
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Optional, Dict, Any

from src.base.client import Client
from . import raft_banking_pb2 as banking_pb2
from . import raft_banking_pb2_grpc as banking_pb2_grpc
from src.base.datatypes import Customer, Account, AccountType
from src.base.proxy_api import ProxyAPI


class RaftGrpcServerProxy(ProxyAPI):
    """gRPC client proxy that implements ProxyAPI with raft_banking package"""
    
    def __init__(self, server_address: str = 'localhost:50051'):
        self.server_address = server_address
        self.channel = None
        self.stub = None
    
    def _ensure_connected(self):
        """Ensure gRPC connection is established"""
        if self.channel is None:
            self.channel = grpc.insecure_channel(self.server_address)
            self.stub = banking_pb2_grpc.BankingServiceStub(self.channel)
    
    def _timestamp_to_datetime(self, timestamp) -> datetime:
        """Convert protobuf timestamp to datetime"""
        return timestamp.ToDatetime()
    
    def _proto_to_customer(self, proto_customer) -> Customer:
        """Convert protobuf Customer to dataclass"""
        return Customer(
            cust_id=proto_customer.cust_id,
            first_name=proto_customer.first_name,
            last_name=proto_customer.last_name,
            address=proto_customer.address,
            accounts=list(proto_customer.accounts),
            create_time=self._timestamp_to_datetime(proto_customer.create_time),
            update_time=self._timestamp_to_datetime(proto_customer.update_time)
        )
    
    def _proto_to_account(self, proto_account) -> Account:
        """Convert protobuf Account to dataclass"""
        # Convert protobuf AccountType to our enum
        type_map = {
            banking_pb2.ACCOUNT_TYPE_SAVINGS: AccountType.SAVINGS,
            banking_pb2.ACCOUNT_TYPE_CHECKING: AccountType.CHECKING
        }
        account_type = type_map.get(proto_account.account_type, AccountType.CHECKING)
        
        return Account(
            account_id=proto_account.account_id,
            account_type=account_type,
            customer_id=proto_account.customer_id,
            balance=Decimal(proto_account.balance),
            create_time=self._timestamp_to_datetime(proto_account.create_time),
            update_time=self._timestamp_to_datetime(proto_account.update_time)
        )
    
    def _account_type_to_proto(self, account_type: AccountType):
        """Convert AccountType enum to protobuf"""
        type_map = {
            AccountType.SAVINGS: banking_pb2.ACCOUNT_TYPE_SAVINGS,
            AccountType.CHECKING: banking_pb2.ACCOUNT_TYPE_CHECKING
        }
        return type_map[account_type]
    
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        """Create a new customer via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.CreateCustomerRequest(
            first_name=first_name,
            last_name=last_name,
            address=address
        )
        
        try:
            response = self.stub.CreateCustomer(request)
            return self._proto_to_customer(response.customer)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        """Create a new account via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.CreateAccountRequest(
            customer_id=str(customer_id),
            account_type=self._account_type_to_proto(account_type)
        )
        
        try:
            response = self.stub.CreateAccount(request)
            return self._proto_to_account(response.account)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        """Deposit money via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.DepositRequest(
            account_id=account_id,
            amount=str(amount)
        )
        
        try:
            response = self.stub.Deposit(request)
            return Decimal(response.balance)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        """Withdraw money via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.WithdrawRequest(
            account_id=account_id,
            amount=str(amount)
        )
        
        try:
            response = self.stub.Withdraw(request)
            return Decimal(response.balance)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        """Transfer money via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.TransferRequest(
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=str(amount)
        )
        
        try:
            response = self.stub.Transfer(request)
            return {
                'from_balance': Decimal(response.from_balance),
                'to_balance': Decimal(response.to_balance)
            }
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        """Cash a check via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.CashCheckRequest(
            account_id=account_id,
            amount=str(amount)
        )
        
        try:
            response = self.stub.CashCheck(request)
            return Decimal(response.balance)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def list_accounts(self) -> List[Account]:
        """List all accounts via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.ListAccountsRequest()
        
        try:
            response = self.stub.ListAccounts(request)
            return [self._proto_to_account(account) for account in response.accounts]
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        """Get customer accounts via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.GetAccountsRequest(customer_id=str(customer_id))
        
        try:
            response = self.stub.GetAccounts(request)
            return list(response.account_ids)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def list_statements(self, account_id: int) -> List[date]:
        """List statements via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.ListStatementsRequest(account_id=account_id)
        
        try:
            response = self.stub.ListStatements(request)
            return [date.fromisoformat(date_str) for date_str in response.statement_dates]
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    async def advance_time(self, delta_time: timedelta) -> None:
        """Advance time via gRPC"""
        self._ensure_connected()
        
        request = banking_pb2.AdvanceTimeRequest(
            delta_seconds=int(delta_time.total_seconds())
        )
        
        try:
            self.stub.AdvanceTime(request)
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")
    
    def close(self):
        """Close the gRPC channel"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
    
    async def raft_message(self, in_message: str) -> str:
        """Send Raft message via gRPC"""
        self._ensure_connected()
        
        # Send simple string message
        request = banking_pb2.RaftMessageRequest(in_message=in_message)
        
        try:
            response = self.stub.RaftMessage(request)
            
            # Return simple string response
            return response.out_message
        except grpc.RpcError as e:
            raise Exception(f"gRPC error: {e.details()}")


class RaftClient(Client):
    """Banking client extended with Raft messaging capability"""
    
    async def raft_message(self, in_message: str) -> str:
        """Send Raft message through the proxy"""
        return await self.server_proxy.raft_message(in_message)


def get_grpc_client(host: str, port: int):
    """Create a Raft-enabled gRPC client"""
    server_address = f"{host}:{port}"
    proxy = RaftGrpcServerProxy(server_address)
    client = RaftClient(proxy)

    def cleanup():
        proxy.close()

    return client, cleanup