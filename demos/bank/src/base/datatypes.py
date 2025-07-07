from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, auto
from typing import List
import datetime


class AccountType(StrEnum):
    SAVINGS = auto()
    CHECKING = auto()


class CommandType(StrEnum):
    """Command types for remote procedure calls. 
    
    These values must exactly match the method names on the Server class
    that are to be executed as remote commands through the proxy layer.
    """
    CREATE_CUSTOMER = auto()
    CREATE_ACCOUNT = auto()
    DEPOSIT = auto()
    WITHDRAW = auto()
    TRANSFER = auto()
    CASH_CHECK = auto()
    LIST_ACCOUNTS = auto()
    GET_ACCOUNTS = auto()
    LIST_STATEMENTS = auto()
    ADVANCE_TIME = auto()

@dataclass
class Customer:
    cust_id: int
    first_name: str
    last_name: str
    address: str
    accounts: List[int]
    create_time: datetime.datetime
    update_time: datetime.datetime


@dataclass
class Account:
    account_id: int
    account_type: AccountType
    customer_id: str
    balance: Decimal
    create_time: datetime.datetime
    update_time: datetime.datetime


@dataclass
class Transaction:
    account_id: int
    starting_balance: Decimal
    ending_balance: Decimal
    change: Decimal
    transaction_time: datetime.datetime


@dataclass
class Statement:
    account_id: int
    statement_date: datetime.date
    starting_balance: Decimal
    ending_balance: Decimal
    total_credits: Decimal
    total_debits: Decimal
