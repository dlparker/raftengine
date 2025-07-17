from decimal import Decimal
import datetime
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from base.datatypes import Customer, Account, AccountType, Transaction, Statement
from base.database import BankDatabase

class Teller:

    def __init__(self, db_file="/tmp/bank.db") -> None:
        self.db = BankDatabase(db_path=db_file)
        self.sim_datetime = datetime.now()

        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        crec = Customer(cust_id=self.db.get_customer_count(),
                       first_name=first_name,
                       last_name=last_name,
                       address=address,
                       accounts=[],
                       create_time=self.sim_datetime,
                       update_time=self.sim_datetime)
        self.db.create_customer(crec)
        return crec

    async def create_account(self, customer_id: int, account_type: AccountType) -> Account:
        cust_rec = self.db.get_customer(customer_id)
        if not cust_rec:
            raise ValueError(f"Customer {customer_id} not found")
        
        arec = Account(account_id=self.db.get_account_count(),
                      account_type=account_type,
                      customer_id=customer_id,
                      balance=Decimal('0.00'),
                      create_time=self.sim_datetime,
                      update_time=self.sim_datetime)
        self.db.create_account(arec, customer_id)
        return arec

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        arec = self.db.get_account(account_id)
        if not arec:
            raise ValueError(f"Account {account_id} not found")
        
        starting_balance = arec.balance
        arec.balance += amount
        
        # Update database
        self.db.update_account_balance(account_id, arec.balance, self.sim_datetime)
        
        # Record transaction
        transaction = Transaction(
            account_id=account_id,
            starting_balance=starting_balance,
            ending_balance=arec.balance,
            change=amount,
            transaction_time=self.sim_datetime
        )
        self.db.record_transaction(transaction)
        
        return arec.balance 
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        arec = self.db.get_account(account_id)
        if not arec:
            raise ValueError(f"Account {account_id} not found")
        
        starting_balance = arec.balance
        arec.balance -= amount
        
        # Update database
        self.db.update_account_balance(account_id, arec.balance, self.sim_datetime)
        
        # Record transaction
        transaction = Transaction(
            account_id=account_id,
            starting_balance=starting_balance,
            ending_balance=arec.balance,
            change=-amount,
            transaction_time=self.sim_datetime
        )
        self.db.record_transaction(transaction)
        
        return arec.balance 
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        from_rec = self.db.get_account(from_account_id)
        to_rec = self.db.get_account(to_account_id)
        
        if not from_rec:
            raise ValueError(f"From account {from_account_id} not found")
        if not to_rec:
            raise ValueError(f"To account {to_account_id} not found")
        
        if from_rec.balance < amount:
            return None
        
        from_starting_balance = from_rec.balance
        to_starting_balance = to_rec.balance
        
        from_rec.balance -= amount
        to_rec.balance += amount
        
        # Update both accounts in database
        self.db.update_account_balance(from_account_id, from_rec.balance, self.sim_datetime)
        self.db.update_account_balance(to_account_id, to_rec.balance, self.sim_datetime)
        
        # Record transactions for both accounts
        from_transaction = Transaction(
            account_id=from_account_id,
            starting_balance=from_starting_balance,
            ending_balance=from_rec.balance,
            change=-amount,
            transaction_time=self.sim_datetime
        )
        to_transaction = Transaction(
            account_id=to_account_id,
            starting_balance=to_starting_balance,
            ending_balance=to_rec.balance,
            change=amount,
            transaction_time=self.sim_datetime
        )
        
        self.db.record_transaction(from_transaction)
        self.db.record_transaction(to_transaction)
        
        return dict(from_balance=from_rec.balance,
                    to_balance=to_rec.balance)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.withdraw(account_id, amount)
    
    async def list_accounts(self, offset: int = 0, limit: int = 100) -> List[Account]:
        return self.db.get_all_accounts(offset, limit)
    
    async def list_customers(self, offset: int = 0, limit: int = 100) -> List[Customer]:
        return self.db.get_all_customers(offset, limit)

    async def get_customer_count(self) -> int:
        return self.db.get_customer_count()
    
    async def get_account_count(self) -> int:
        return self.db.get_account_count()
    
    async def get_accounts(self, customer_id: int) -> List[int]:
        cust_rec = self.db.get_customer(customer_id)
        if not cust_rec:
            raise ValueError(f"Customer {customer_id} not found")
        return cust_rec.accounts
    
    async def list_statements(self, account_id: int) -> List[date]:
        return self.db.get_statement_dates(account_id)
    
    async def advance_time(self, delta_time: timedelta):
        old_datetime = self.sim_datetime
        new_datetime = self.sim_datetime + delta_time
        
        # Check if we're crossing a month boundary
        if self._crosses_month_boundary(old_datetime, new_datetime):
            await self._generate_monthly_statements(old_datetime, new_datetime)
        
        self.sim_datetime = new_datetime
    
    def _crosses_month_boundary(self, old_dt: datetime, new_dt: datetime) -> bool:
        """Check if the time advance crosses from end of month to beginning of next month"""
        # Get the last day of old_dt's month
        if old_dt.month == 12:
            next_month = old_dt.replace(year=old_dt.year + 1, month=1, day=1)
        else:
            next_month = old_dt.replace(month=old_dt.month + 1, day=1)
        
        last_day_of_month = next_month - timedelta(days=1)
        
        # Check if we go from before midnight on last day to after midnight on first day
        old_is_before_month_end = old_dt.date() <= last_day_of_month.date()
        new_is_after_month_end = new_dt.date() >= next_month.date()
        
        return old_is_before_month_end and new_is_after_month_end
    
    async def _generate_monthly_statements(self, old_dt: datetime, new_dt: datetime) -> None:
        """Generate monthly statements for all accounts when crossing month boundary"""
        # Get the end of the month we're crossing
        if old_dt.month == 12:
            next_month = old_dt.replace(year=old_dt.year + 1, month=1, day=1)
        else:
            next_month = old_dt.replace(month=old_dt.month + 1, day=1)
        
        end_of_month = next_month - timedelta(days=1)
        
        # Get the start of the month
        start_of_month = old_dt.replace(day=1)
        
        # Generate statements for all accounts
        accounts = self.db.get_all_accounts()
        for account in accounts:
            await self._generate_account_statement(account, start_of_month.date(), end_of_month.date())
    
    async def _generate_account_statement(self, account: Account, start_date: date, end_date: date) -> None:
        """Generate a monthly statement for a specific account"""
        # Get all transactions for this account in the period
        transactions = self.db.get_transactions_for_period(account.account_id, start_date, end_date)
        
        if not transactions:
            # No transactions, use current account balance for both start and end
            starting_balance = account.balance
            ending_balance = account.balance
            total_credits = Decimal('0.00')
            total_debits = Decimal('0.00')
        else:
            # Calculate starting balance (ending balance - all changes)
            total_change = sum(t.change for t in transactions)
            ending_balance = account.balance
            starting_balance = ending_balance - total_change
            
            # Calculate credits and debits
            total_credits = sum(t.change for t in transactions if t.change > 0)
            total_debits = sum(abs(t.change) for t in transactions if t.change < 0)
        
        # Create and store the statement
        statement = Statement(
            account_id=account.account_id,
            statement_date=end_date,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            total_credits=total_credits,
            total_debits=total_debits
        )
        
        self.db.create_statement(statement)

    

