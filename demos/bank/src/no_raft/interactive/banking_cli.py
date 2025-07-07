#!/usr/bin/env python
"""Interactive Banking CLI using Click, Prompt Toolkit, and Rich"""
import asyncio
import argparse
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from pathlib import Path
import sys

# Add the top-level directory to the path
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.no_raft.transports.grpc.client import get_grpc_client
from src.no_raft.direct.one_process import get_direct_client
from src.no_raft.transports.async_streams.proxy import get_astream_client
from src.base.datatypes import AccountType


class BankingCLI:
    """Interactive Banking CLI Application"""
    
    def __init__(self):
        self.console = Console()
        self.client = None
        self.cleanup_func = None
        self.transport_type = None
        self.connection_info = None
        
        # Define available commands for auto-completion
        banking_commands = [
            'create-customer', 'create-account', 'deposit', 'withdraw', 
            'transfer', 'cash-check', 'list-accounts', 'list-customers',
            'statements', 'balance', 'connect', 'disconnect', 'status', 
            'help', 'exit'
        ]
        
        self.commands = WordCompleter(banking_commands, ignore_case=True)
        
        # Create prompt session
        self.session = PromptSession(
            "bank> ",
            history=FileHistory('.banking_history'),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self.commands
        )
    
    def print_banner(self):
        """Display welcome banner"""
        banner = Panel.fit(
            "[bold blue]Banking CLI v1.0[/bold blue]\n"
            "[dim]Interactive Banking Client[/dim]\n"
            "Type 'help' for available commands",
            title="Welcome",
            border_style="blue"
        )
        self.console.print(banner)
    
    def print_status(self):
        """Display current connection status"""
        if self.client is None:
            status = "[red]Disconnected[/red]"
            info = "No active connection"
        else:
            status = f"[green]Connected[/green] ({self.transport_type})"
            info = self.connection_info
        
        self.console.print(f"Status: {status} - {info}")
    
    async def connect_direct(self, database_file: str):
        """Connect using direct transport"""
        try:
            await self.disconnect()
            self.client, self.cleanup_func = get_direct_client(database_file)
            self.transport_type = "Direct"
            self.connection_info = f"Database: {database_file}"
            self.console.print(f"[green]✓[/green] Connected to direct database: {database_file}")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to connect: {e}")
    
    async def connect_astream(self, host: str, port: int):
        """Connect using async streams transport"""
        try:
            await self.disconnect()
            self.client, self.cleanup_func = get_astream_client(host, port)
            self.transport_type = "Async Streams"
            self.connection_info = f"{host}:{port}"
            self.console.print(f"[green]✓[/green] Connected to async streams server: {host}:{port}")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to connect: {e}")
    
    async def connect_grpc(self, host: str, port: int):
        """Connect using gRPC transport"""
        try:
            await self.disconnect()
            self.client, self.cleanup_func = get_grpc_client(host, port)
            self.transport_type = "gRPC"
            self.connection_info = f"{host}:{port}"
            self.console.print(f"[green]✓[/green] Connected to gRPC server: {host}:{port}")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to connect: {e}")
    
    async def disconnect(self):
        """Disconnect from current transport"""
        if self.cleanup_func:
            try:
                if asyncio.iscoroutinefunction(self.cleanup_func):
                    await self.cleanup_func()
                else:
                    self.cleanup_func()
            except Exception as e:
                self.console.print(f"[yellow]Warning:[/yellow] Cleanup error: {e}")
        
        self.client = None
        self.cleanup_func = None
        self.transport_type = None
        self.connection_info = None
    
    def check_connection(self):
        """Check if client is connected"""
        if self.client is None:
            self.console.print("[red]✗[/red] Not connected. Use 'connect' command first.")
            return False
        return True
    
    def format_currency(self, amount):
        """Format currency for display"""
        return f"${amount:,.2f}"
    
    async def run(self):
        """Main CLI loop"""
        self.print_banner()
        
        # Default connection to direct transport
        await self.connect_direct("banking_cli.db")
        
        while True:
            try:
                # Get command from user - use async version
                command_line = await self.session.prompt_async()
                
                if not command_line.strip():
                    continue
                
                # Parse command and arguments
                parts = command_line.strip().split()
                cmd = parts[0].lower()
                args = parts[1:]
                
                # Handle commands
                if cmd == 'exit':
                    break
                elif cmd == 'help':
                    await self.cmd_help()
                elif cmd == 'status':
                    self.print_status()
                elif cmd == 'connect':
                    await self.cmd_connect(args)
                elif cmd == 'disconnect':
                    await self.disconnect()
                    self.console.print("[yellow]Disconnected[/yellow]")
                elif cmd == 'create-customer':
                    await self.cmd_create_customer(args)
                elif cmd == 'create-account':
                    await self.cmd_create_account(args)
                elif cmd == 'deposit':
                    await self.cmd_deposit(args)
                elif cmd == 'withdraw':
                    await self.cmd_withdraw(args)
                elif cmd == 'transfer':
                    await self.cmd_transfer(args)
                elif cmd == 'cash-check':
                    await self.cmd_cash_check(args)
                elif cmd == 'list-accounts':
                    await self.cmd_list_accounts()
                elif cmd == 'balance':
                    await self.cmd_balance(args)
                elif cmd == 'statements':
                    await self.cmd_statements(args)
                else:
                    self.console.print(f"[red]Unknown command:[/red] {cmd}. Type 'help' for available commands.")
            
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use 'exit' to quit[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error:[/red] {e}")
        
        # Cleanup on exit
        await self.disconnect()
        self.console.print("[blue]Goodbye![/blue]")
    
    async def cmd_help(self):
        """Display help information"""
        help_table = Table(title="Available Commands")
        help_table.add_column("Command", style="cyan", no_wrap=True)
        help_table.add_column("Description", style="white")
        help_table.add_column("Usage", style="dim")
        
        commands = [
            ("connect", "Connect to transport", "connect direct <db_file> | async_streams <host> <port> | grpc <host> <port>"),
            ("disconnect", "Disconnect from current transport", "disconnect"),
            ("status", "Show connection status", "status"),
            ("create-customer", "Create a new customer", "create-customer <first_name> <last_name> <address>"),
            ("create-account", "Create an account", "create-account <customer_id> <checking|savings>"),
            ("deposit", "Deposit money", "deposit <account_id> <amount>"),
            ("withdraw", "Withdraw money", "withdraw <account_id> <amount>"),
            ("transfer", "Transfer money", "transfer <from_account> <to_account> <amount>"),
            ("cash-check", "Cash a check", "cash-check <account_id> <amount>"),
            ("list-accounts", "List all accounts", "list-accounts"),
            ("balance", "Check account balance", "balance <account_id>"),
            ("statements", "List statements", "statements <account_id>"),
            ("help", "Show this help", "help"),
            ("exit", "Exit the program", "exit"),
        ]
        
        for cmd, desc, usage in commands:
            help_table.add_row(cmd, desc, usage)
        
        self.console.print(help_table)
    
    async def cmd_connect(self, args):
        """Handle connect command"""
        if not args:
            self.console.print("[red]Usage:[/red] connect direct <db_file> | async_streams <host> <port> | grpc <host> <port>")
            return
        
        transport = args[0].lower()
        
        if transport == "direct":
            if len(args) < 2:
                db_file = "banking_cli.db"
            else:
                db_file = args[1]
            await self.connect_direct(db_file)
        
        elif transport == "async_streams":
            if len(args) < 3:
                self.console.print("[red]Usage:[/red] connect async_streams <host> <port>")
                return
            host = args[1]
            try:
                port = int(args[2])
                await self.connect_astream(host, port)
            except ValueError:
                self.console.print("[red]Error:[/red] Port must be a number")
        
        elif transport == "grpc":
            if len(args) < 3:
                self.console.print("[red]Usage:[/red] connect grpc <host> <port>")
                return
            host = args[1]
            try:
                port = int(args[2])
                await self.connect_grpc(host, port)
            except ValueError:
                self.console.print("[red]Error:[/red] Port must be a number")
        
        else:
            self.console.print(f"[red]Unknown transport:[/red] {transport}")
    
    async def cmd_create_customer(self, args):
        """Handle create-customer command"""
        if not self.check_connection():
            return
        
        if len(args) < 3:
            self.console.print("[red]Usage:[/red] create-customer <first_name> <last_name> <address>")
            return
        
        first_name = args[0]
        last_name = args[1]
        address = " ".join(args[2:])  # Join remaining args as address
        
        try:
            customer = await self.client.create_customer(first_name, last_name, address)
            self.console.print(f"[green]✓[/green] Created customer: {customer.first_name} {customer.last_name} (ID: {customer.cust_id})")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to create customer: {e}")
    
    async def cmd_create_account(self, args):
        """Handle create-account command"""
        if not self.check_connection():
            return
        
        if len(args) < 2:
            self.console.print("[red]Usage:[/red] create-account <customer_id> <checking|savings>")
            return
        
        customer_id = args[0]
        account_type_str = args[1].lower()
        
        if account_type_str == "checking":
            account_type = AccountType.CHECKING
        elif account_type_str == "savings":
            account_type = AccountType.SAVINGS
        else:
            self.console.print("[red]Error:[/red] Account type must be 'checking' or 'savings'")
            return
        
        try:
            account = await self.client.create_account(customer_id, account_type)
            self.console.print(f"[green]✓[/green] Created {account_type.value} account: {account.account_id}")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to create account: {e}")
    
    async def cmd_deposit(self, args):
        """Handle deposit command"""
        if not self.check_connection():
            return
        
        if len(args) < 2:
            self.console.print("[red]Usage:[/red] deposit <account_id> <amount>")
            return
        
        try:
            account_id = int(args[0])
            amount = Decimal(args[1])
            
            if amount <= 0:
                self.console.print("[red]Error:[/red] Amount must be positive")
                return
            
            balance = await self.client.deposit(account_id, amount)
            self.console.print(f"[green]✓[/green] Deposited {self.format_currency(amount)} to account {account_id}")
            self.console.print(f"  New balance: {self.format_currency(balance)}")
        except ValueError:
            self.console.print("[red]Error:[/red] Invalid account ID or amount")
        except InvalidOperation:
            self.console.print("[red]Error:[/red] Invalid amount format")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to deposit: {e}")
    
    async def cmd_withdraw(self, args):
        """Handle withdraw command"""
        if not self.check_connection():
            return
        
        if len(args) < 2:
            self.console.print("[red]Usage:[/red] withdraw <account_id> <amount>")
            return
        
        try:
            account_id = int(args[0])
            amount = Decimal(args[1])
            
            if amount <= 0:
                self.console.print("[red]Error:[/red] Amount must be positive")
                return
            
            balance = await self.client.withdraw(account_id, amount)
            self.console.print(f"[green]✓[/green] Withdrew {self.format_currency(amount)} from account {account_id}")
            self.console.print(f"  New balance: {self.format_currency(balance)}")
        except ValueError:
            self.console.print("[red]Error:[/red] Invalid account ID or amount")
        except InvalidOperation:
            self.console.print("[red]Error:[/red] Invalid amount format")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to withdraw: {e}")
    
    async def cmd_transfer(self, args):
        """Handle transfer command"""
        if not self.check_connection():
            return
        
        if len(args) < 3:
            self.console.print("[red]Usage:[/red] transfer <from_account> <to_account> <amount>")
            return
        
        try:
            from_account = int(args[0])
            to_account = int(args[1])
            amount = Decimal(args[2])
            
            if amount <= 0:
                self.console.print("[red]Error:[/red] Amount must be positive")
                return
            
            result = await self.client.transfer(from_account, to_account, amount)
            self.console.print(f"[green]✓[/green] Transferred {self.format_currency(amount)}")
            self.console.print(f"  From account {from_account}: {self.format_currency(result['from_balance'])}")
            self.console.print(f"  To account {to_account}: {self.format_currency(result['to_balance'])}")
        except ValueError:
            self.console.print("[red]Error:[/red] Invalid account ID or amount")
        except InvalidOperation:
            self.console.print("[red]Error:[/red] Invalid amount format")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to transfer: {e}")
    
    async def cmd_cash_check(self, args):
        """Handle cash-check command"""
        if not self.check_connection():
            return
        
        if len(args) < 2:
            self.console.print("[red]Usage:[/red] cash-check <account_id> <amount>")
            return
        
        try:
            account_id = int(args[0])
            amount = Decimal(args[1])
            
            if amount <= 0:
                self.console.print("[red]Error:[/red] Amount must be positive")
                return
            
            balance = await self.client.cash_check(account_id, amount)
            self.console.print(f"[green]✓[/green] Cashed check for {self.format_currency(amount)}")
            self.console.print(f"  New balance: {self.format_currency(balance)}")
        except ValueError:
            self.console.print("[red]Error:[/red] Invalid account ID or amount")
        except InvalidOperation:
            self.console.print("[red]Error:[/red] Invalid amount format")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to cash check: {e}")
    
    async def cmd_list_accounts(self):
        """Handle list-accounts command"""
        if not self.check_connection():
            return
        
        try:
            accounts = await self.client.list_accounts()
            
            if not accounts:
                self.console.print("[yellow]No accounts found[/yellow]")
                return
            
            table = Table(title="All Accounts")
            table.add_column("Account ID", style="cyan", no_wrap=True)
            table.add_column("Type", style="magenta")
            table.add_column("Customer", style="green")
            table.add_column("Balance", style="yellow", justify="right")
            
            for account in accounts:
                table.add_row(
                    str(account.account_id),
                    account.account_type.value.title(),
                    account.customer_id,
                    self.format_currency(account.balance)
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to list accounts: {e}")
    
    async def cmd_balance(self, args):
        """Handle balance command"""
        if not self.check_connection():
            return
        
        if len(args) < 1:
            self.console.print("[red]Usage:[/red] balance <account_id>")
            return
        
        try:
            account_id = int(args[0])
            accounts = await self.client.list_accounts()
            
            account = next((acc for acc in accounts if acc.account_id == account_id), None)
            if account:
                self.console.print(f"Account {account_id} balance: {self.format_currency(account.balance)}")
            else:
                self.console.print(f"[red]Account {account_id} not found[/red]")
        except ValueError:
            self.console.print("[red]Error:[/red] Invalid account ID")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to get balance: {e}")
    
    async def cmd_statements(self, args):
        """Handle statements command"""
        if not self.check_connection():
            return
        
        if len(args) < 1:
            self.console.print("[red]Usage:[/red] statements <account_id>")
            return
        
        try:
            account_id = int(args[0])
            statements = await self.client.list_statements(account_id)
            
            if not statements:
                self.console.print(f"[yellow]No statements found for account {account_id}[/yellow]")
                return
            
            self.console.print(f"Statements for account {account_id}:")
            for stmt_date in statements:
                self.console.print(f"  • {stmt_date}")
        except ValueError:
            self.console.print("[red]Error:[/red] Invalid account ID")
        except Exception as e:
            self.console.print(f"[red]✗[/red] Failed to get statements: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Interactive Banking CLI')
    parser.add_argument('--database', '-d', 
                       default='banking_cli.db',
                       help='Default database file for direct connection')
    
    args = parser.parse_args()
    
    cli = BankingCLI()
    
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()