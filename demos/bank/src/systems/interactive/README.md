# Interactive Banking CLI

A beautiful, interactive command-line interface for the banking system using Click, Prompt Toolkit, and Rich.

## Features

- **Interactive Prompts**: Command history, auto-completion, and suggestions
- **Rich Output**: Beautiful tables, colored text, and formatted currency
- **Multiple Transports**: Support for Direct, Async Streams, and gRPC connections
- **Full Banking Operations**: All banking operations available through simple commands

## Installation

Install the required dependencies:

```bash
pip install click prompt-toolkit rich
```

## Usage

Start the interactive CLI:

```bash
python src/systems/interactive/banking_cli.py
```

**Note**: This CLI uses async prompt handling to work properly with the async banking operations. The CLI will connect to a direct database by default.

Or with a custom database:

```bash
python src/systems/interactive/banking_cli.py --database my_bank.db
```

## Available Commands

### Connection Management
- `connect direct <db_file>` - Connect to direct database
- `connect astream <host> <port>` - Connect to async streams server
- `connect grpc <host> <port>` - Connect to gRPC server
- `disconnect` - Disconnect from current transport
- `status` - Show connection status

### Banking Operations
- `create-customer <first_name> <last_name> <address>` - Create a new customer
- `create-account <customer_id> <checking|savings>` - Create an account
- `deposit <account_id> <amount>` - Deposit money
- `withdraw <account_id> <amount>` - Withdraw money
- `transfer <from_account> <to_account> <amount>` - Transfer money
- `cash-check <account_id> <amount>` - Cash a check
- `list-accounts` - List all accounts
- `balance <account_id>` - Check account balance
- `statements <account_id>` - List account statements

### Other Commands
- `help` - Show available commands
- `exit` - Exit the program

## Example Session

```
Banking CLI v1.0 - Interactive Banking Client
Connected to: Direct (banking_cli.db)

bank> create-customer Alice Smith 123 Main Street
✓ Created customer: Alice Smith (ID: 0)

bank> create-account Smith,Alice checking
✓ Created checking account: 0

bank> deposit 0 1000.00
✓ Deposited $1,000.00 to account 0
  New balance: $1,000.00

bank> list-accounts
                  All Accounts                   
┏━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Account ID ┃ Type     ┃ Customer    ┃ Balance   ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 0          │ Checking │ Smith,Alice │ $1,000.00 │
└────────────┴──────────┴─────────────┴───────────┘

bank> connect grpc localhost 50051
✓ Connected to gRPC server: localhost:50051

bank> help
Available Commands
...

bank> exit
Goodbye!
```

## Features

### Command History
All commands are saved to `.banking_history` file and can be accessed using up/down arrows.

### Auto-completion
Press Tab to auto-complete commands and get suggestions.

### Rich Formatting
- Colored output for success/error messages
- Beautiful tables for account listings
- Properly formatted currency values
- Status panels and information displays

### Transport Flexibility
Switch between different transport methods during the same session:
- **Direct**: In-process connection with SQLite database
- **Async Streams**: Network connection using async socket streams
- **gRPC**: Network connection using gRPC protocol

### Error Handling
Comprehensive error handling with user-friendly messages for:
- Invalid command syntax
- Connection failures
- Banking operation errors
- Input validation errors