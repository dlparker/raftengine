import logging
import time
import asyncio
from pathlib import Path
from typing import Dict, Any
from datetime import timedelta, date
from decimal import Decimal
from collections import defaultdict
from raftengine.deck.deck import Deck
from raftengine.api.deck_api import CommandResult
from base.operations import Ops
from base.datatypes import Customer, Account, AccountType, CommandType
from step5.base_plus.proxy_api import OpsProxyAPI
from step5.raft_ops.collector import Collector
from step5.raft_ops.dispatcher import Dispatcher
from step5.raft_ops.sqlite_log import SqliteLog
from step5.raft_ops.pilot import Pilot

logger = logging.getLogger("RaftServer")

class RaftServer(OpsProxyAPI):

    def __init__(self, initial_cluster_config, local_config, setup_helper):
        self.initial_config = initial_cluster_config
        self.local_config = local_config
        self.working_dir = Path(local_config.working_dir)
        self.setup_helper = setup_helper
        app_db_file = Path(self.working_dir, "bank.db")
        self.operations = Ops(app_db_file)
        raft_log_file = Path(self.working_dir, "raftlog.db")
        self.log = SqliteLog(raft_log_file)
        self.log.start()
        self.collector = Collector()
        self.dispatcher = Dispatcher(self.operations)
        self.pilot = Pilot(self.log, self.setup_helper, self.dispatcher, self.reply_ready)
        self.deck = Deck(self.initial_config, self.local_config, self.pilot)
        self.pilot.set_deck(self.deck)
        self.stopped = False
        self.replies = defaultdict(list)

    async def start(self):
        logger.info("calling deck start")
        await self.deck.start()
        self.stopped = False
    
    async def stop(self):
        await self.deck.stop()
        self.stopped = True
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> CommandResult:
        try:
            logger.debug(f"RaftServer.create_customer called: {first_name}, {last_name}, {address}")
            command = await self.collector.create_customer(first_name, last_name, address)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command, timeout=111111)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.create_customer exception: {e}")
            logger.error(f"Args: {first_name}, {last_name}, {address}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def create_account(self, customer_id: str, account_type: AccountType) -> CommandResult:
        try:
            logger.debug(f"RaftServer.create_account called: {customer_id}, {account_type}")
            command = await self.collector.create_account(customer_id, account_type)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.create_account exception: {e}")
            logger.error(f"Args: {customer_id}, {account_type}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def deposit(self, account_id: int, amount: Decimal) -> CommandResult:
        try:
            logger.debug(f"RaftServer.deposit called: {account_id}, {amount}")
            command = await self.collector.deposit(account_id, amount)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.deposit exception: {e}")
            logger.error(f"Args: {account_id}, {amount}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def withdraw(self, account_id: int, amount: Decimal) -> CommandResult:
        try:
            logger.debug(f"RaftServer.withdraw called: {account_id}, {amount}")
            command = await self.collector.withdraw(account_id, amount)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.withdraw exception: {e}")
            logger.error(f"Args: {account_id}, {amount}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> CommandResult:
        try:
            logger.debug(f"RaftServer.transfer called: {from_account_id} -> {to_account_id}, {amount}")
            command = await self.collector.transfer(from_account_id, to_account_id, amount)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.transfer exception: {e}")
            logger.error(f"Args: {from_account_id}, {to_account_id}, {amount}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def cash_check(self, account_id: int, amount: Decimal)  -> CommandResult:
        try:
            logger.debug(f"RaftServer.cash_check called: {account_id}, {amount}")
            command = await self.collector.cash_check(account_id, amount)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.cash_check exception: {e}")
            logger.error(f"Args: {account_id}, {amount}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def list_accounts(self)  -> CommandResult:
        try:
            logger.debug(f"RaftServer.list_accounts called")
            command = await self.collector.list_accounts()
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.list_accounts exception: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def get_accounts(self, customer_id: str)  -> CommandResult:
        try:
            logger.debug(f"RaftServer.get_accounts called: {customer_id}")
            command = await self.collector.get_accounts(customer_id)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.get_accounts exception: {e}")
            logger.error(f"Args: {customer_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def list_statements(self, account_id: int)  -> CommandResult:
        try:
            logger.debug(f"RaftServer.list_statements called: {account_id}")
            command = await self.collector.list_statements(account_id)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.list_statements exception: {e}")
            logger.error(f"Args: {account_id}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def advance_time(self, delta_time: timedelta)  -> CommandResult:
        try:
            logger.debug(f"RaftServer.advance_time called: {delta_time}")
            command = await self.collector.advance_time(delta_time)
            logger.debug(f"Generated command: {command}")
            
            result = await self.deck.run_command(command)
            logger.debug(f"Deck returned: error={result.error}, committed={result.committed}, result_type={type(result.result)}")
            
            if result.error:
                logger.error(f"Command failed with error: {result.error}")
            elif not result.committed:
                logger.warning(f"Command not committed: {result}")
            elif result.result is None:
                logger.warning(f"Command committed but no result: {result}")
            else:
                logger.debug(f"Command completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"RaftServer.advance_time exception: {e}")
            logger.error(f"Args: {delta_time}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def raft_message(self, message: str) -> str: # pragma: no cover
        #logger.info("Got raft message {message['code']}")
        msg = self.deck.decode_message(message)
        logger.info(f"Got raft message {msg.code} from {msg.sender}")
        await self.deck.on_message(message)
        sender = msg.sender
        start_time = time.time()
        reply = None
        while time.time() - start_time < 1.0:
            for omsg,res in self.replies[sender]:
                if omsg == message:
                    reply = res 
                    break
            if reply:
                break
            await asyncio.sleep(0.0001)
        if reply is None:
            logger.error(f'could not get reply for {sender}')
            print('*'*80)
            print('reviewing')
            for omsg,res in self.replies[sender]:
                print(f'checking\n {omsg} \nvs\n{message}')
            return ""
        new_list = []
        for m,res in self.replies[sender]:
            if m != message:
                new_list.append((m, res))
        self.replies[sender] = new_list
        logger.info(f"Collected reply from pilot and returning to {sender}")
        return reply

    async def reply_ready(self, target_uri, orig_msg, reply):
        self.replies[target_uri].append((orig_msg.decode(), reply))
        logger.info(f"Enqueing reply to  {target_uri}")
