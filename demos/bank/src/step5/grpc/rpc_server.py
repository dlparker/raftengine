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
from . import step5_banking_pb2 as banking_pb2
from . import step5_banking_pb2_grpc as banking_pb2_grpc
from ..base_plus.proxy_api import OpsProxyAPI


class BankingServiceImpl(banking_pb2_grpc.BankingServiceServicer):
    """
    gRPC service implementation for banking operations with msgpack serialization
    """

    def __init__(self, server: OpsProxyAPI):
        self.server = server
        # Don't create a separate event loop - use the existing one from gRPC async server
    
    def _convert_command_result(self, cmd_result):
        """Convert raftengine CommandResult to protobuf CommandResult"""
        result_bytes = b""
        if cmd_result.result is not None:
            # cmd_result.result is a JSON string, convert to msgpack bytes
            from base.json_helpers import bank_json_loads
            obj = bank_json_loads(cmd_result.result)
            result_bytes = bank_msgpack_dumps(obj)
        
        # Handle redirect: CommandResult.redirect is string, protobuf needs boolean + string
        has_redirect = bool(cmd_result.redirect)
        redirect_addr = cmd_result.redirect or ""
        
        return banking_pb2.CommandResult(
            error=cmd_result.error or "",
            redirect=has_redirect,
            retry=cmd_result.retry or False,
            result=result_bytes,
            redirect_to=redirect_addr
        )

    async def CreateCustomer(self, request, context):
        """Create a new customer"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC CreateCustomer: {request.first_name}, {request.last_name}")
            
            cmd_result = await self.server.create_customer(
                request.first_name, request.last_name, request.address
            )
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC CreateCustomer exception: {e}")
            logger.error(f"Request: {request}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False, retry=False, result=b"", redirect_to=""
            )

    async def CreateAccount(self, request, context):
        """Create a new account"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC CreateAccount: customer_id={request.customer_id}, account_type={request.account_type}")
            
            account_type = AccountType(request.account_type)
            cmd_result = await self.server.create_account(
                request.customer_id,
                account_type
            )
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC CreateAccount exception: {e}")
            logger.error(f"Request: customer_id={request.customer_id}, account_type={request.account_type}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def Deposit(self, request, context):
        """Deposit money to an account"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC Deposit: account_id={request.account_id}")
            
            amount = bank_msgpack_loads(request.amount)
            logger.debug(f"Decoded amount: {amount}")
            
            cmd_result = await self.server.deposit(request.account_id, amount)
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC Deposit exception: {e}")
            logger.error(f"Request: account_id={request.account_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def Withdraw(self, request, context):
        """Withdraw money from an account"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC Withdraw: account_id={request.account_id}")
            
            amount = bank_msgpack_loads(request.amount)
            logger.debug(f"Decoded amount: {amount}")
            
            cmd_result = await self.server.withdraw(request.account_id, amount)
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC Withdraw exception: {e}")
            logger.error(f"Request: account_id={request.account_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def Transfer(self, request, context):
        """Transfer money between accounts"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC Transfer: from={request.from_account_id}, to={request.to_account_id}")
            
            amount = bank_msgpack_loads(request.amount)
            logger.debug(f"Decoded amount: {amount}")
            
            cmd_result = await self.server.transfer(
                request.from_account_id,
                request.to_account_id,
                amount
            )
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC Transfer exception: {e}")
            logger.error(f"Request: from={request.from_account_id}, to={request.to_account_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def CashCheck(self, request, context):
        """Cash a check"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC CashCheck: account_id={request.account_id}")
            
            amount = bank_msgpack_loads(request.amount)
            logger.debug(f"Decoded amount: {amount}")
            
            cmd_result = await self.server.cash_check(request.account_id, amount)
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC CashCheck exception: {e}")
            logger.error(f"Request: account_id={request.account_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def ListAccounts(self, request, context):
        """List all accounts"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC ListAccounts called")
            
            cmd_result = await self.server.list_accounts()
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC ListAccounts exception: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def GetAccounts(self, request, context):
        """Get account IDs for a customer"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC GetAccounts: customer_id={request.customer_id}")
            
            cmd_result = await self.server.get_accounts(request.customer_id)
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC GetAccounts exception: {e}")
            logger.error(f"Request: customer_id={request.customer_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def ListStatements(self, request, context):
        """List statement dates for an account"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC ListStatements: account_id={request.account_id}")
            
            cmd_result = await self.server.list_statements(request.account_id)
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC ListStatements exception: {e}")
            logger.error(f"Request: account_id={request.account_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def AdvanceTime(self, request, context):
        """Advance the server time"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC AdvanceTime called")
            
            delta_time = bank_msgpack_loads(request.delta_time)
            logger.debug(f"Decoded delta_time: {delta_time}")
            
            cmd_result = await self.server.advance_time(delta_time)
            
            if cmd_result.error:
                logger.error(f"gRPC got error from RaftServer: {cmd_result.error}")
            
            response = self._convert_command_result(cmd_result)
            logger.debug(f"gRPC returning response: error={response.error}, has_result={bool(response.result)}")
            return response
        except Exception as e:
            logger.error(f"gRPC AdvanceTime exception: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return banking_pb2.CommandResult(
                error=f"gRPC server exception: {str(e)}",
                redirect=False,
                retry=False,
                result=b"",
                redirect_to=""
            )

    async def RaftMessage(self, request, context):
        """Handle Raft message"""
        try:
            import logging
            logger = logging.getLogger("gRPC.server")
            logger.debug(f"gRPC RaftMessage called with message length: {len(request.message)}")
            
            response = await self.server.raft_message(request.message)
            logger.debug(f"Got raft response length: {len(response) if response else 0}")
            return banking_pb2.RaftMessageResponse(response=response)
        except Exception as e:
            logger.error(f"gRPC RaftMessage exception: {e}")
            logger.error(f"Message length: {len(request.message) if request.message else 0}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
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
