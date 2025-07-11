from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType


class OpsProxyAPI(ABC): 
    """Abstract base class defining the interface for banking proxy implementations"""
    
    @abstractmethod
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer: # pragma: no cover
        """Create a new customer with the given details"""
        raise NotImplemented

    
    @abstractmethod
    async def create_account(self, customer_id: str, account_type: AccountType) -> Account: # pragma: no cover
        """Create a new account for an existing customer"""
        raise NotImplemented
    
    @abstractmethod
    async def deposit(self, account_id: int, amount: Decimal) -> Decimal: # pragma: no cover
        """Deposit money into an account and return the new balance"""
        raise NotImplemented
    
    @abstractmethod
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal: # pragma: no cover
        """Withdraw money from an account and return the new balance"""
        raise NotImplemented
    
    @abstractmethod
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]: # pragma: no cover
        """Transfer money between accounts. Returns dict with balances or None if insufficient funds"""
        raise NotImplemented
    
    @abstractmethod
    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal: # pragma: no cover
        """Cash a check (withdraw) from an account and return the new balance"""
        raise NotImplemented
    
    @abstractmethod
    async def list_accounts(self) -> List[Account]: # pragma: no cover
        """List all accounts in the system"""
        raise NotImplemented
    
    @abstractmethod
    async def get_accounts(self, customer_id: str) -> List[int]: # pragma: no cover
        """Get all account IDs for a specific customer"""
        raise NotImplemented
    
    @abstractmethod
    async def list_statements(self, account_id: int) -> List[date]: # pragma: no cover
        """List all statement dates for an account"""
        raise NotImplemented
    
    @abstractmethod
    async def advance_time(self, delta_time: timedelta) -> None: # pragma: no cover
        """Advance the simulation time by the given delta"""
        raise NotImplemented
    
