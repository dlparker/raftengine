# Enhanced Interactive Banking CLI

A beautiful, interactive command-line interface for the banking system with support for both no_raft and raft_prep versions, using Click, Prompt Toolkit, and Rich.

## Features

- **Interactive Prompts**: Command history, auto-completion, and suggestions
- **Rich Output**: Beautiful tables, colored text, and formatted currency
- **Multiple Transport Support**: Direct, Async Streams, and gRPC connections
- **Dual Version Support**: Both no_raft and raft_prep transports
- **Raft Messaging**: Send Raft consensus messages when connected to raft_prep
- **Dynamic UI**: Prompt changes to show raft status (`bank>` vs `raft>`)
- **Full Banking Operations**: All banking operations available through simple commands

## Installation

Install the required dependencies:

```bash
pip install click prompt-toolkit rich
```

Or install from the requirements file:

```bash
pip install -r src/interactive/requirements.txt
```

## Usage

Start the enhanced interactive CLI:

```bash
python src/interactive/banking_cli.py
```

**Note**: This enhanced CLI uses async prompt handling to work properly with the async banking operations. The CLI will connect to a direct database by default.

Or with a custom database:

```bash
python src/interactive/banking_cli.py --database my_bank.db
```

## Available Commands

### Connection Management
- `connect direct <db_file>` - Connect to no_raft direct database
- `connect raft direct <db_file>` - Connect to raft_prep direct database (same as no_raft for direct)
- `connect async_streams <host> <port>` - Connect to no_raft async streams server
- `connect raft async_streams <host> <port>` - Connect to raft_prep async streams server
- `connect grpc <host> <port>` - Connect to no_raft gRPC server
- `connect raft grpc <host> <port>` - Connect to raft_prep gRPC server
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

### Raft Operations (raft_prep only)
- `raft-message <message_type> <message_data>` - Send Raft consensus message

### Other Commands
- `help` - Show available commands
- `exit` - Exit the program

## Enhanced Features

### Dual Transport Support

The enhanced CLI can connect to both no_raft and raft_prep implementations:

```bash
# Connect to no_raft version
bank> connect grpc localhost 50051

# Connect to raft_prep version  
bank> connect raft grpc localhost 50052
```

### Dynamic Prompt

The prompt changes to indicate the current mode:
- `bank>` - Connected to no_raft or disconnected
- `raft>` - Connected to raft_prep with Raft capabilities

### Raft Messaging

When connected to raft_prep transports, you can send Raft consensus messages:

```bash
raft> raft-message RequestVote {"term": 1, "candidate_id": "node1"}
✓ Raft message response:
  Type: RequestVote
  Data: {"term": 1, "candidate_id": "node1"}

raft> raft-message AppendEntries {"term": 1, "leader_id": "node1", "entries": []}
```

### Status Display

The status command shows enhanced information:

```bash
raft> status
Status: Connected (gRPC) - Raft-enabled - localhost:50052 (raft_prep)
```

## Example Session

```
Enhanced Banking CLI v2.0 - Interactive Banking Client with Raft Support
Connected to: Direct (banking_cli.db)

bank> create-customer Alice Smith 123 Main Street
✓ Created customer: Alice Smith (ID: 0)
Use customer key 'Smith,Alice' for account creation

bank> create-account Smith,Alice checking
✓ Created checking account: 0

bank> deposit 0 1000.00
✓ Deposited $1,000.00 to account 0
  New balance: $1,000.00

bank> connect raft grpc localhost 50052
✓ Connected to gRPC server: localhost:50052 (raft_prep)

raft> raft-message RequestVote {"term": 1, "candidate_id": "node1"}
Sending Raft message: RequestVote
✓ Raft message response:
  Type: RequestVote
  Data: {"term": 1, "candidate_id": "node1"}

raft> list-accounts
                    All Accounts                     
┏━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Account ID ┃ Type     ┃ Customer    ┃ Balance   ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 0          │ Checking │ Smith,Alice │ $1,000.00 │
└────────────┴──────────┴─────────────┴───────────┘

raft> help
Available Commands
...

raft> exit
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
- Raft-specific highlighting in help

### Transport Flexibility
Switch between different transport methods and versions during the same session:
- **Direct**: In-process connection with SQLite database
- **Async Streams**: Network connection using async socket streams (no_raft or raft_prep)
- **gRPC**: Network connection using gRPC protocol (no_raft or raft_prep)

### Error Handling
Comprehensive error handling with user-friendly messages for:
- Invalid command syntax
- Connection failures
- Banking operation errors
- Input validation errors
- Raft-specific operation errors

### Version Detection
The CLI automatically detects which version you're connected to and enables/disables features accordingly:
- Raft commands are only available when connected to raft_prep
- Help system highlights available vs unavailable commands
- Status display shows current capabilities

## Development Notes

### Adding New Transports

To add support for new transport types:

1. Import the client function at the top of `banking_cli.py`
2. Add connection methods (e.g., `connect_new_transport`)
3. Update the `cmd_connect` method to handle the new transport
4. Update help text and documentation

### Adding New Commands

To add new banking or raft commands:

1. Add the command to the `banking_commands` list for auto-completion
2. Add a handler method (e.g., `cmd_new_command`)
3. Add the command to the main command loop in `run()`
4. Update help text in `cmd_help()`

## Compatibility

This enhanced CLI is backward compatible with the original no_raft implementation while adding new capabilities for raft_prep. All existing banking operations work identically across both versions.