from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from .datatypes import Customer, Account, AccountType


class ProxyAPI(ABC):
    """Abstract base class defining the interface for banking proxy implementations"""
    
    @abstractmethod
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        """Create a new customer with the given details"""
        pass
    
    @abstractmethod
    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        """Create a new account for an existing customer"""
        pass
    
    @abstractmethod
    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        """Deposit money into an account and return the new balance"""
        pass
    
    @abstractmethod
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        """Withdraw money from an account and return the new balance"""
        pass
    
    @abstractmethod
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        """Transfer money between accounts. Returns dict with balances or None if insufficient funds"""
        pass
    
    @abstractmethod
    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        """Cash a check (withdraw) from an account and return the new balance"""
        pass
    
    @abstractmethod
    async def list_accounts(self) -> List[Account]:
        """List all accounts in the system"""
        pass
    
    @abstractmethod
    async def get_accounts(self, customer_id: str) -> List[int]:
        """Get all account IDs for a specific customer"""
        pass
    
    @abstractmethod
    async def list_statements(self, account_id: int) -> List[date]:
        """List all statement dates for an account"""
        pass
    
    @abstractmethod
    async def advance_time(self, delta_time: timedelta) -> None:
        """Advance the simulation time by the given delta"""
        pass