from dataclasses import dataclass, asdict, field
from decimal import Decimal, ROUND_HALF_UP
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
    first_name: str
    last_name: str
    address: str
    cust_id: int  = field(default=None)
    accounts: List[int]  = field(default_factory=list)
    create_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    update_time: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_dict(self):
        new = asdict(self)
        new['accounts'] = []
        for account in self.accounts:
            new['accounts'].append(account.to_dict())
        new['create_time'] = self.create_time.isoformat()
        new['update_time'] = self.update_time.isoformat()
        return new
            
    @classmethod
    def from_dict(cls, data):
        kwargs = data
        accounts  = []
        for acct in data['accounts']:
            accounts.append(Account.from_dict(acct))
        kwargs['accounts'] = accounts
        kwargs['create_time'] = datetime.datetime.fromisoformat(data['create_time'])
        kwargs['update_time'] = datetime.datetime.fromisoformat(data['update_time'])
        return cls(**kwargs)

@dataclass
class Account:
    account_type: AccountType
    customer_id: int
    balance: Decimal
    account_id: int = field(default=None)
    create_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    update_time: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_dict(self):
        new = asdict(self)
        new['balance'] = float(self.balance)
        new['create_time'] = self.create_time.isoformat()
        new['update_time'] = self.update_time.isoformat()
        return new

    @classmethod
    def from_dict(cls, data):
        kwargs = data
        kwargs['account_type'] = AccountType(data['account_type'])
        kwargs['balance'] = Decimal(data['balance']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        kwargs['create_time'] = datetime.datetime.fromisoformat(data['create_time'])
        kwargs['update_time'] = datetime.datetime.fromisoformat(data['update_time'])
        return cls(**kwargs)
    
        

@dataclass
class Transaction:
    account_id: int
    starting_balance: Decimal
    ending_balance: Decimal
    change: Decimal
    transaction_time: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_dict(self):
        new = asdict(self)
        new['starting_balance'] = float(self.starting_balance)
        new['ending_balance'] = float(self.ending_balance)
        new['change'] = float(self.change)
        new['transaction_time'] = self.transaction_time.isoformat()
        return new

    @classmethod
    def from_dict(cls, data):
        kwargs = data
        for key in ['starting_balance', 'ending_balance', 'change']:
            kwargs[key] = Decimal(str(data[key])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        kwargs['transaction_time'] = datetime.datetime.fromisoformat(data['transaction_time'])
        return cls(**kwargs)
    
@dataclass
class Statement:
    account_id: int
    starting_balance: Decimal
    ending_balance: Decimal
    total_credits: Decimal
    total_debits: Decimal
    statement_date: datetime.date = field(default_factory=datetime.date.today)

    def to_dict(self):
        new = asdict(self)
        new['starting_balance'] = float(self.starting_balance)
        new['ending_balance'] = float(self.ending_balance)
        new['total_credits'] = float(self.total_credits)
        new['total_debits'] = float(self.total_debits)
        new['statement_date'] = self.statement_date.isoformat()
        return new

    @classmethod
    def from_dict(cls, data):
        kwargs = data
        kwargs['statement_date'] = datetime.datetime.fromisoformat(data['statement_date'])
        for key in ['starting_balance', 'ending_balance', 'total_credits', 'total_debits']:
            kwargs[key] = Decimal(str(data[key])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return cls(**kwargs)


