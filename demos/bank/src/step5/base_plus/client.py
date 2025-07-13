from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import AccountType, Customer, Account
from base.proxy_api import OpsProxyAPI
from base.client import Client as BaseClient


class Client(BaseClient):

    async def raft_message(self, message: str) -> str:
        return await self.server_proxy.raft_message(message)

    
