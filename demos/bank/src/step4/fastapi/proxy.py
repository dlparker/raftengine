import asyncio
import base64
import httpx
import json
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType
from step4.base_plus.proxy_api import OpsProxyAPI
from base.msgpack_helpers import bank_msgpack_dumps, bank_msgpack_loads


class ServerProxy(OpsProxyAPI):
    """
    HTTP client proxy for JSON-RPC banking operations with msgpack serialization
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.client = None
        self.request_id = 0

    async def connect(self):
        """Connect to the HTTP server"""
        print(f"connecting to JSON-RPC server at {self.base_url}")
        self.client = httpx.AsyncClient(base_url=self.base_url)
        print("connected to JSON-RPC server")

    async def _ensure_connected(self):
        """Ensure we're connected to the server"""
        if self.client is None:
            await self.connect()

    def _get_request_id(self) -> int:
        """Get next request ID"""
        self.request_id += 1
        return self.request_id

    async def _make_request(self, method: str, params: dict = None) -> any:
        """Make a JSON-RPC request"""
        await self._ensure_connected()
        
        request_data = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._get_request_id()
        }
        
        if params:
            request_data["params"] = params
            
        try:
            response = await self.client.post("/rpc", json=request_data)
            response.raise_for_status()
            
            result = response.json()
            
            if "error" in result:
                raise Exception(f"JSON-RPC error: {result['error']['message']}")
            
            return result.get("result")
            
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        result = await self._make_request("create_customer", {
            "first_name": first_name,
            "last_name": last_name,
            "address": address
        })
        # Decode base64 and deserialize Customer
        customer_data = base64.b64decode(result)
        return bank_msgpack_loads(customer_data)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        result = await self._make_request("create_account", {
            "customer_id": customer_id,
            "account_type": account_type.value
        })
        # Decode base64 and deserialize Account
        account_data = base64.b64decode(result)
        return bank_msgpack_loads(account_data)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        # Encode amount as base64 for JSON transport
        amount_data = base64.b64encode(bank_msgpack_dumps(amount)).decode('utf-8')
        result = await self._make_request("deposit", {
            "account_id": account_id,
            "amount_data": amount_data
        })
        # Decode base64 and deserialize Decimal
        balance_data = base64.b64decode(result)
        return bank_msgpack_loads(balance_data)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        # Encode amount as base64 for JSON transport
        amount_data = base64.b64encode(bank_msgpack_dumps(amount)).decode('utf-8')
        result = await self._make_request("withdraw", {
            "account_id": account_id,
            "amount_data": amount_data
        })
        # Decode base64 and deserialize Decimal
        balance_data = base64.b64decode(result)
        return bank_msgpack_loads(balance_data)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        # Encode amount as base64 for JSON transport
        amount_data = base64.b64encode(bank_msgpack_dumps(amount)).decode('utf-8')
        result = await self._make_request("transfer", {
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount_data": amount_data
        })
        # Decode base64 and deserialize result
        result_data = base64.b64decode(result)
        return bank_msgpack_loads(result_data)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        # Encode amount as base64 for JSON transport
        amount_data = base64.b64encode(bank_msgpack_dumps(amount)).decode('utf-8')
        result = await self._make_request("cash_check", {
            "account_id": account_id,
            "amount_data": amount_data
        })
        # Decode base64 and deserialize Decimal
        balance_data = base64.b64decode(result)
        return bank_msgpack_loads(balance_data)
    
    async def list_accounts(self) -> List[Account]:
        result = await self._make_request("list_accounts")
        # Decode base64 and deserialize List[Account]
        accounts_data = base64.b64decode(result)
        return bank_msgpack_loads(accounts_data)
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        result = await self._make_request("get_accounts", {
            "customer_id": customer_id
        })
        # Decode base64 and deserialize List[int]
        account_ids_data = base64.b64decode(result)
        return bank_msgpack_loads(account_ids_data)
    
    async def list_statements(self, account_id: int) -> List[date]:
        result = await self._make_request("list_statements", {
            "account_id": account_id
        })
        # Decode base64 and deserialize List[date]
        dates_data = base64.b64decode(result)
        return bank_msgpack_loads(dates_data)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        # Encode delta_time as base64 for JSON transport
        delta_time_data = base64.b64encode(bank_msgpack_dumps(delta_time)).decode('utf-8')
        await self._make_request("advance_time", {
            "delta_time_data": delta_time_data
        })
    
    async def raft_message(self, message: str) -> str:
        result = await self._make_request("raft_message", {
            "message": message
        })
        return result

    async def close(self):
        """Close the HTTP connection"""
        if self.client:
            await self.client.aclose()
