from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType

class TellerProxyAPI(ABC): 
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
    
class TellerWrapper(TellerProxyAPI):
    """
    A trivial implementation of the API, just to make a simple
    demo of indirect access.
    """

    def __init__(self, teller):
        self.teller = teller

    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        return await self.teller.create_customer(first_name, last_name, address)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        return await self.teller.create_account(customer_id, account_type)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.teller.deposit(account_id, amount)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.teller.withdraw(account_id, amount)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        return await self.teller.transfer(from_account_id, to_account_id, amount)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.teller.cash_check(account_id, amount)
    
    async def list_accounts(self) -> List[Account]:
        return await self.teller.list_accounts()
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        return await self.teller.get_accounts(customer_id)
    
    async def list_statements(self, account_id: int) -> List[date]:
        return await self.teller.list_statements(account_id)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        return await self.teller.advance_time(delta_time)
    
    
    
