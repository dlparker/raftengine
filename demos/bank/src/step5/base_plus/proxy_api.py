from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType
from base.proxy_api import OpsProxyAPI as BaseProxyAPI


class OpsProxyAPI(BaseProxyAPI): 

    @abstractmethod
    async def raft_message(self, message: str) -> str: # pragma: no cover
        """Send a raft message and return response"""
        raise NotImplemented
