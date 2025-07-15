import argparse
import asyncio
from pathlib  import Path
from typing import List, Optional, Dict, Callable, Any
from datetime import timedelta, date
from decimal import Decimal
from functools import wraps
from base.datatypes import Customer, Account, AccountType
from base.proxy_api import TellerProxyAPI


def raft_command():
    """Decorator for raft commands that handles retry/redirect/error logic"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            import logging
            logger = logging.getLogger("ClientProxy")
            cmd_result = None
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                try:
                    logger.debug(f"Client calling {func.__name__} (attempt {retry_count + 1})")
                    
                    # Call the original rpc_proxy method with the same name
                    rpc_proxy_method = getattr(self.rpc_proxy, func.__name__)
                    cmd_result = await rpc_proxy_method(*args, **kwargs)
                    
                    # Validate CommandResult structure
                    if cmd_result is None:
                        raise Exception(f"Received null CommandResult from server for {func.__name__}")
                    
                    if not hasattr(cmd_result, 'error'):
                        raise Exception(f"Invalid CommandResult: missing 'error' field for {func.__name__}")
                    
                    logger.debug(f"Client got CommandResult: error={cmd_result.error}, committed={getattr(cmd_result, 'committed', 'unknown')}")
                    
                    # Check for error conditions
                    if cmd_result.error:
                        logger.error(f"Command {func.__name__} returned error: {cmd_result.error}")
                        raise Exception("Command execution returned an error: " + cmd_result.error)
                    
                    # Check for timeout - either explicit timeout_expired or implicit timeout condition
                    timeout_expired = getattr(cmd_result, 'timeout_expired', False)
                    implicit_timeout = (not getattr(cmd_result, 'committed', False) and 
                                       cmd_result.result is None and 
                                       cmd_result.error is None)
                    
                    if timeout_expired or implicit_timeout:
                        logger.warning(f"Command {func.__name__} timed out: explicit={timeout_expired}, implicit={implicit_timeout}")
                        raise Exception("Command execution timed out")
                    
                    # Check for redirect
                    if getattr(cmd_result, 'redirect', False):
                        redirect_addr = getattr(cmd_result, 'redirect_to', '') or getattr(cmd_result, 'redirect', '')
                        logger.info(f"Command {func.__name__} redirected to: {redirect_addr}")
                        if retry_count > 0:
                            raise Exception("Multiple redirects not supported")
                        # Update leader if method exists
                        if hasattr(self, 'set_leader_rpc_proxy'):
                            self.set_leader_rpc_proxy(redirect_addr)
                        retry_count += 1
                        continue
                    
                    # Check for retry
                    if getattr(cmd_result, 'retry', False):
                        logger.info(f"Command {func.__name__} requested retry")
                        retry_count += 1
                        if retry_count < max_retries:
                            await asyncio.sleep(0.1)
                            continue
                        else:
                            raise Exception("Maximum retry attempts exceeded")
                    
                    # Success case - extract the business object
                    if cmd_result.result is not None:
                        try:
                            logger.debug(f"Deserializing result for {func.__name__}")
                            result = bank_json_loads(cmd_result.result)
                            logger.debug(f"Successfully deserialized result: {type(result)}")
                            return result
                        except Exception as e:
                            logger.error(f"Failed to deserialize result for {func.__name__}: {e}")
                            logger.error(f"Raw result data: {cmd_result.result[:200]}..." if len(str(cmd_result.result)) > 200 else f"Raw result data: {cmd_result.result}")
                            raise Exception(f"Result deserialization failed: {str(e)}")
                    else:
                        logger.debug(f"Command {func.__name__} succeeded with no result data")
                        return None
                        
                except Exception as e:
                    # Log the exception details but only re-raise non-retry exceptions
                    logger.error(f"Client proxy exception in {func.__name__}: {e}")
                    logger.error(f"Args: {args}, Kwargs: {kwargs}")
                    
                    # Check if this is a retriable error
                    error_str = str(e).lower()
                    if any(retriable in error_str for retriable in ['timeout', 'connection', 'network', 'unavailable']):
                        logger.info(f"Retriable error detected, attempt {retry_count + 1}/{max_retries}")
                        retry_count += 1
                        if retry_count < max_retries:
                            await asyncio.sleep(0.1 * retry_count)  # Exponential backoff
                            continue
                    
                    # Non-retriable error or max retries exceeded
                    raise
                    
            # If we exit the loop without returning, we exceeded retries
            raise Exception("Maximum retry attempts exceeded")
                
        return wrapper
    return decorator


class ServerProxy(OpsProxyAPI):
    """
    """

    def __init__(self, rpc_proxy):
        self.rpc_proxy = rpc_proxy
        
    def set_leader_rpc_proxy(self, leader_address: str):
        """Update the RPC proxy to point to the leader address"""
        # This method should be implemented based on the specific RPC client
        # For now, we'll just log the redirect (the actual implementation 
        # would need to reconnect the rpc_proxy to the new address)
        import logging
        logger = logging.getLogger("ServerProxy")
        logger.info(f"Redirect to leader at {leader_address} - reconnection not implemented")
        
    @raft_command()
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        pass

    @raft_command()
    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        pass

    @raft_command()
    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        pass
    
    @raft_command()
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        pass
    
    @raft_command()
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        pass

    @raft_command()
    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        pass
    
    @raft_command()
    async def list_accounts(self, offset: int = 0, limit: int = 100) -> List[Account]:
        pass
    
    @raft_command()
    async def list_customers(self, offset: int = 0, limit: int = 100) -> List[Customer]:
        pass
    
    @raft_command()
    async def get_accounts(self, customer_id: str) -> List[int]:
        pass
    
    @raft_command()
    async def list_statements(self, account_id: int) -> List[date]:
        pass
    
    @raft_command()
    async def advance_time(self, delta_time: timedelta) -> None:
        pass
                
    async def raft_message(self, message: str) -> str:
        raise Exception('raft_message should never be called in client code')
        
