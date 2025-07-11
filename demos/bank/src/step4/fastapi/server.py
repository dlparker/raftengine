import asyncio
import base64
import json
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal

from base.datatypes import Customer, Account, AccountType
from base.operations import Ops
from base.msgpack_helpers import bank_msgpack_dumps, bank_msgpack_loads

# Global server instance - will be set by setup_helper
banking_server: Optional[Ops] = None

def set_banking_server(server: Ops):
    """Set the global banking server instance"""
    global banking_server
    banking_server = server


async def handle_create_customer(first_name: str, last_name: str, address: str):
    """Create a new customer"""
    customer = await banking_server.create_customer(first_name, last_name, address)
    # Encode as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(customer)).decode('utf-8')


async def handle_create_account(customer_id: str, account_type: str):
    """Create a new account"""
    account_type_enum = AccountType(account_type)
    account = await banking_server.create_account(customer_id, account_type_enum)
    # Encode as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(account)).decode('utf-8')


async def handle_deposit(account_id: int, amount_data: str):
    """Deposit money to an account"""
    # Decode base64 and deserialize amount
    amount = bank_msgpack_loads(base64.b64decode(amount_data))
    balance = await banking_server.deposit(account_id, amount)
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(balance)).decode('utf-8')


async def handle_withdraw(account_id: int, amount_data: str):
    """Withdraw money from an account"""
    # Decode base64 and deserialize amount
    amount = bank_msgpack_loads(base64.b64decode(amount_data))
    balance = await banking_server.withdraw(account_id, amount)
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(balance)).decode('utf-8')


async def handle_transfer(from_account_id: int, to_account_id: int, amount_data: str):
    """Transfer money between accounts"""
    # Decode base64 and deserialize amount
    amount = bank_msgpack_loads(base64.b64decode(amount_data))
    result = await banking_server.transfer(from_account_id, to_account_id, amount)
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(result)).decode('utf-8')


async def handle_cash_check(account_id: int, amount_data: str):
    """Cash a check"""
    # Decode base64 and deserialize amount
    amount = bank_msgpack_loads(base64.b64decode(amount_data))
    balance = await banking_server.cash_check(account_id, amount)
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(balance)).decode('utf-8')


async def handle_list_accounts():
    """List all accounts"""
    accounts = await banking_server.list_accounts()
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(accounts)).decode('utf-8')


async def handle_get_accounts(customer_id: str):
    """Get account IDs for a customer"""
    account_ids = await banking_server.get_accounts(customer_id)
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(account_ids)).decode('utf-8')


async def handle_list_statements(account_id: int):
    """List statement dates for an account"""
    dates = await banking_server.list_statements(account_id)
    # Encode result as base64 for JSON transport
    return base64.b64encode(bank_msgpack_dumps(dates)).decode('utf-8')


async def handle_advance_time(delta_time_data: str):
    """Advance the server time"""
    # Decode base64 and deserialize delta_time
    delta_time = bank_msgpack_loads(base64.b64decode(delta_time_data))
    await banking_server.advance_time(delta_time)
    return None


# Method registry
METHOD_HANDLERS = {
    "create_customer": handle_create_customer,
    "create_account": handle_create_account,
    "deposit": handle_deposit,
    "withdraw": handle_withdraw,
    "transfer": handle_transfer,
    "cash_check": handle_cash_check,
    "list_accounts": handle_list_accounts,
    "get_accounts": handle_get_accounts,
    "list_statements": handle_list_statements,
    "advance_time": handle_advance_time,
}


# Create FastAPI app
app = FastAPI(title="Banking JSON-RPC API", version="1.0.0")


async def handle_jsonrpc_request(request_data: dict) -> dict:
    """Handle a single JSON-RPC request"""
    try:
        method_name = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")
        
        if method_name not in METHOD_HANDLERS:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method '{method_name}' not found"},
                "id": request_id
            }
        
        handler = METHOD_HANDLERS[method_name]
        
        # Call the handler with parameters
        if isinstance(params, dict):
            result = await handler(**params)
        elif isinstance(params, list):
            result = await handler(*params)
        else:
            result = await handler()
        
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        }
        
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e)},
            "id": request_data.get("id")
        }


@app.post("/rpc")
async def rpc_endpoint(request: Request):
    """JSON-RPC endpoint"""
    try:
        body = await request.body()
        request_data = json.loads(body.decode('utf-8'))
        
        # Handle single request
        if isinstance(request_data, dict):
            response = await handle_jsonrpc_request(request_data)
        # Handle batch requests
        elif isinstance(request_data, list):
            responses = []
            for req in request_data:
                resp = await handle_jsonrpc_request(req)
                responses.append(resp)
            response = responses
        else:
            response = {"error": {"code": -32700, "message": "Parse error"}}
            
        return JSONResponse(content=response, media_type="application/json")
        
    except json.JSONDecodeError:
        return JSONResponse(
            content={"error": {"code": -32700, "message": "Parse error"}},
            status_code=400
        )
    except Exception as e:
        return JSONResponse(
            content={"error": {"code": -32603, "message": "Internal error"}},
            status_code=500
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "banking-jsonrpc"}


async def create_server(host: str, port: int, server: Ops):
    """Create and configure the FastAPI server"""
    set_banking_server(server)
    return app