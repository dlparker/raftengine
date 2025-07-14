import sqlite3
import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from base.datatypes import Customer, Account, AccountType, Transaction, Statement


class BankDatabase:
    def __init__(self, db_path: str = "/tmp/bank.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create customers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                cust_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                address TEXT NOT NULL,
                create_time TEXT NOT NULL,
                update_time TEXT NOT NULL
            )
        """)
        
        # Create accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY,
                account_type TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                balance TEXT NOT NULL,
                create_time TEXT NOT NULL,
                update_time TEXT NOT NULL
            )
        """)
        
        # Create transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                starting_balance TEXT NOT NULL,
                ending_balance TEXT NOT NULL,
                change TEXT NOT NULL,
                transaction_time TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts (account_id)
            )
        """)
        
        # Create customer_accounts junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_accounts (
                customer_id TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                PRIMARY KEY (customer_id, account_id),
                FOREIGN KEY (account_id) REFERENCES accounts (account_id)
            )
        """)
        
        # Create statements table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statements (
                statement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                statement_date TEXT NOT NULL,
                starting_balance TEXT NOT NULL,
                ending_balance TEXT NOT NULL,
                total_credits TEXT NOT NULL,
                total_debits TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts (account_id),
                UNIQUE(account_id, statement_date)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_customer(self, customer: Customer) -> None:
        """Insert a new customer into the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO customers (cust_id, first_name, last_name, address, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            customer.cust_id,
            customer.first_name,
            customer.last_name,
            customer.address,
            customer.create_time.isoformat(),
            customer.update_time.isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def create_account(self, account: Account, customer_key: str) -> None:
        """Insert a new account into the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO accounts (account_id, account_type, customer_id, balance, create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            account.account_id,
            account.account_type.value if hasattr(account.account_type, 'value') else account.account_type,
            account.customer_id,
            str(account.balance),
            account.create_time.isoformat(),
            account.update_time.isoformat()
        ))
        
        # Link account to customer
        cursor.execute("""
            INSERT INTO customer_accounts (customer_id, account_id)
            VALUES (?, ?)
        """, (customer_key, account.account_id))
        
        conn.commit()
        conn.close()
    
    def update_account_balance(self, account_id: int, new_balance: Decimal, update_time: datetime.datetime) -> None:
        """Update account balance and update_time"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE accounts 
            SET balance = ?, update_time = ?
            WHERE account_id = ?
        """, (str(new_balance), update_time.isoformat(), account_id))
        
        conn.commit()
        conn.close()
    
    def record_transaction(self, transaction: Transaction) -> None:
        """Record a transaction in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO transactions (account_id, starting_balance, ending_balance, change, transaction_time)
            VALUES (?, ?, ?, ?, ?)
        """, (
            transaction.account_id,
            str(transaction.starting_balance),
            str(transaction.ending_balance),
            str(transaction.change),
            transaction.transaction_time.isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_customer(self, customer_key: str) -> Optional[Customer]:
        """Retrieve a customer by key (last_name,first_name)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cust_id, first_name, last_name, address, create_time, update_time
            FROM customers
            WHERE (last_name || ',' || first_name) = ?
        """, (customer_key,))
        
        row = cursor.fetchone()
        if row:
            # Get customer's accounts
            cursor.execute("""
                SELECT account_id FROM customer_accounts
                WHERE customer_id = ?
            """, (customer_key,))
            accounts = [row[0] for row in cursor.fetchall()]
            
            customer = Customer(
                cust_id=row[0],
                first_name=row[1],
                last_name=row[2],
                address=row[3],
                accounts=accounts,
                create_time=datetime.datetime.fromisoformat(row[4]),
                update_time=datetime.datetime.fromisoformat(row[5])
            )
            conn.close()
            return customer
        
        conn.close()
        return None
    
    def get_account(self, account_id: int) -> Optional[Account]:
        """Retrieve an account by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT account_id, account_type, customer_id, balance, create_time, update_time
            FROM accounts
            WHERE account_id = ?
        """, (account_id,))
        
        row = cursor.fetchone()
        if row:
            account = Account(
                account_id=row[0],
                account_type=AccountType(row[1]),
                customer_id=row[2],
                balance=Decimal(row[3]),
                create_time=datetime.datetime.fromisoformat(row[4]),
                update_time=datetime.datetime.fromisoformat(row[5])
            )
            conn.close()
            return account
        
        conn.close()
        return None
    
    def get_all_accounts(self) -> List[Account]:
        """Retrieve all accounts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT account_id, account_type, customer_id, balance, create_time, update_time
            FROM accounts
        """)
        
        accounts = []
        for row in cursor.fetchall():
            account = Account(
                account_id=row[0],
                account_type=AccountType(row[1]),
                customer_id=row[2],
                balance=Decimal(row[3]),
                create_time=datetime.datetime.fromisoformat(row[4]),
                update_time=datetime.datetime.fromisoformat(row[5])
            )
            accounts.append(account)
        
        conn.close()
        return accounts
    
    def get_customer_count(self) -> int:
        """Get the total number of customers"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM customers")
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def get_account_count(self) -> int:
        """Get the total number of accounts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM accounts")
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def create_statement(self, statement: Statement) -> None:
        """Insert a new statement into the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO statements (account_id, statement_date, starting_balance, ending_balance, total_credits, total_debits)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            statement.account_id,
            statement.statement_date.isoformat(),
            str(statement.starting_balance),
            str(statement.ending_balance),
            str(statement.total_credits),
            str(statement.total_debits)
        ))
        
        conn.commit()
        conn.close()
    
    def get_statement_dates(self, account_id: int) -> List[datetime.date]:
        """Get all statement dates for an account"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT statement_date FROM statements
            WHERE account_id = ?
            ORDER BY statement_date
        """, (account_id,))
        
        dates = []
        for row in cursor.fetchall():
            dates.append(datetime.date.fromisoformat(row[0]))
        
        conn.close()
        return dates
    
    def get_transactions_for_period(self, account_id: int, start_date: datetime.date, end_date: datetime.date) -> List[Transaction]:
        """Get all transactions for an account within a date range"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT account_id, starting_balance, ending_balance, change, transaction_time
            FROM transactions
            WHERE account_id = ? AND date(transaction_time) >= ? AND date(transaction_time) <= ?
            ORDER BY transaction_time
        """, (account_id, start_date.isoformat(), end_date.isoformat()))
        
        transactions = []
        for row in cursor.fetchall():
            transaction = Transaction(
                account_id=row[0],
                starting_balance=Decimal(row[1]),
                ending_balance=Decimal(row[2]),
                change=Decimal(row[3]),
                transaction_time=datetime.datetime.fromisoformat(row[4])
            )
            transactions.append(transaction)
        
        conn.close()
        return transactions
    
    def get_all_transactions(self) -> List[Transaction]:
        """Get all transactions from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT account_id, starting_balance, ending_balance, change, transaction_time
            FROM transactions
            ORDER BY transaction_time
        """)
        
        transactions = []
        for row in cursor.fetchall():
            transaction = Transaction(
                account_id=row[0],
                starting_balance=Decimal(row[1]),
                ending_balance=Decimal(row[2]),
                change=Decimal(row[3]),
                transaction_time=datetime.datetime.fromisoformat(row[4])
            )
            transactions.append(transaction)
        
        conn.close()
        return transactions
    
    def get_all_statements(self) -> List[Statement]:
        """Get all statements from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT account_id, statement_date, starting_balance, ending_balance, total_credits, total_debits
            FROM statements
            ORDER BY statement_date
        """)
        
        statements = []
        for row in cursor.fetchall():
            statement = Statement(
                account_id=row[0],
                statement_date=datetime.date.fromisoformat(row[1]),
                starting_balance=Decimal(row[2]),
                ending_balance=Decimal(row[3]),
                total_credits=Decimal(row[4]),
                total_debits=Decimal(row[5])
            )
            statements.append(statement)
        
        conn.close()
        return statements
