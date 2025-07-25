#!/usr/bin/env python
"""
Interactive logging administration tool for Raft servers using aiocmd.
Allows setting logger levels with autocompletion and discovery.
"""
# Check if aiocmd is available
try:
    from aiocmd import aiocmd
    AIOCMD_AVAILABLE = True
except ImportError:
    AIOCMD_AVAILABLE = False
    print("aiocmd not available. Please install with: pip install aiocmd")
    sys.exit(1)

class LoggingAdminShell(aiocmd.PromptToolkitCmd):
    intro = 'Logging Administration Tool (aiocmd version). Type help or ? to list commands.\n'
    prompt = 'logging_admin> '
    
    def __init__(self, rpc_client, server_uri):
        super().__init__()
        self.rpc_client = rpc_client
        self.server_uri = server_uri
        self.server_local_commands = LocalCollector(rpc_client)
        self.current_loggers = {}
        self.valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        
    async def setup(self):
        try:
            await self._refresh_loggers()
            print(f"Connected to server: {self.server_uri}")
            print(f"Found {len(self.current_loggers)} configured loggers")
        except Exception as e:
            print(f"Warning: Could not fetch initial logger config: {e}")

    async def _refresh_loggers(self):
        config = await self.server_local_commands.get_logging_dict()
        self.current_loggers = config.get('loggers', {})
        
    async def do_list(self, arg=""):
        """Show current logger levels"""
        try:
            await self._refresh_loggers()
            print("\nCurrent logger levels:")
            print("-" * 40)
            
            # Show global/root logger first
            if "" in self.current_loggers:
                level = self.current_loggers[""].get("level", "NOT SET")
                print(f"  (global): {level}")
                
            # Show other loggers alphabetically
            other_loggers = {k: v for k, v in self.current_loggers.items() if k != ""}
            for logger_name in sorted(other_loggers.keys()):
                level = other_loggers[logger_name].get("level", "NOT SET")
                print(f"  {logger_name}: {level}")
            print()
        except Exception as e:
            print(f"Error fetching logger config: {e}")

    async def do_set(self, logger_name, level):
        """Set specific logger level: set <logger_name> <level>"""
        level = level.upper()
        
        # Handle special case for global logger
        if logger_name == "(global)" or logger_name == "":
            logger_names = None
        else:
            logger_names = [logger_name,]
        if level not in self.valid_levels:
            print(f"Invalid level '{level}'. Valid levels: {', '.join(self.valid_levels)}")
            return
            
        try:
            result = await self.server_local_commands.set_logging_level(level, logger_names)
            if isinstance(result, dict) and logger_name in result:
                print(f"Result: {result[logger_name]}")
            else:
                print(f"Set {logger_name or '(global)'} to {level}")
        except Exception as e:
            print(f"Error setting logger level: {e}")

    async def do_global(self, level):
        """Set global/default logger level: global <level>"""
        level = level.upper()
        
        if level not in self.valid_levels:
            print(f"Invalid level '{level}'. Valid levels: {', '.join(self.valid_levels)}")
            return
            
        try:
            await self.server_local_commands.set_logging_level(level, [])
            print(f"Set global logging level to {level}")
        except Exception as e:
            print(f"Error setting global level: {e}")

    async def do_refresh(self, arg=""):
        """Refresh logger configuration from server"""
        try:
            await self._refresh_loggers()
            print(f"Refreshed logger configuration ({len(self.current_loggers)} loggers)")
        except Exception as e:
            print(f"Error refreshing logger config: {e}")

    def do_quit(self, arg=""):
        """Exit the logging admin tool"""
        print("Goodbye!")
        return True

    def do_exit(self, arg=""):
        """Exit the logging admin tool"""
        return self.do_quit(arg)

    def do_EOF(self, arg=""):
        """Exit on Ctrl+D"""
        print()
        return self.do_quit(arg)

    async def complete_set(self, text, line, begidx, endidx):
        """Autocompletion for set command"""
        try:
            # Refresh loggers for current completion
            await self._refresh_loggers()
            
            args = line.split()
            
            # If we're completing the first argument (logger name)
            if len(args) == 2 and not line.endswith(' '):
                # Complete logger names, including special handling for global logger
                logger_names = []
                for name in self.current_loggers.keys():
                    if name == "":
                        # Show global logger as "(global)" for easier selection
                        if "(global)".startswith(text):
                            logger_names.append("(global)")
                    elif name.startswith(text):
                        logger_names.append(name)
                return sorted(logger_names)
            elif len(args) >= 2:
                # If we're completing the second argument (level)
                return [level for level in self.valid_levels if level.startswith(text.upper())]
            
            return []
        except Exception:
            # If completion fails, return empty list
            return []

    async def complete_global(self, text, line, begidx, endidx):
        """Autocompletion for global command"""
        return [level for level in self.valid_levels if level.startswith(text.upper())]

async def run_logging_admin(target_node, RPCHelper):
    try:
        rpc_client = await RPCHelper().rpc_client_maker(target_node)
        
        # Test connection
        server_local_commands = LocalCollector(rpc_client)
        try:
            pid = await server_local_commands.get_pid()
        except Exception as e:
            print(f'Server {target_node} not reachable: {e}')
            await rpc_client.close()
            return
            
        # Create and setup the shell
        shell = LoggingAdminShell(rpc_client, target_node)
        await shell.setup()
        
        # Run the interactive loop
        await shell.run()
        
        await rpc_client.close()
        
    except Exception as e:
        print(f'Error connecting to {target_node}: {e}')
        traceback.print_exc()

async def main():
    parser = argparse.ArgumentParser(description="Interactive Logging Administration Tool (aiocmd)")
    
    parser.add_argument('--transport', '-t', 
                        required=True,
                        choices=TRANSPORT_CHOICES,
                        help='Transport mechanism to use')
    parser.add_argument('--index', '-i', type=int,
                        required=True,
                        help='Cluster node index to target') 
    
    args = parser.parse_args()

    nodes, RPCHelper = nodes_and_helper(args.transport, base_port=50050, node_count=3)
    target_node = nodes[args.index]

    await run_logging_admin(target_node, RPCHelper)

if __name__ == "__main__":
    import asyncio
    import argparse
    import traceback
    import json
    import sys
    from pathlib import Path
    from pprint import pprint


    this_dir = Path(__file__).resolve().parent
    for parent in this_dir.parents:
        if parent.name == 'src':
            if parent not in sys.path:
                sys.path.insert(0, str(parent))
                break
    else:
        raise ImportError("Could not find 'src' directory in the path hierarchy")

    from raftengine.deck.log_control import LogController
    # setup LogControl before importing any modules that might initialize it first
    LogController.controller = None
    log_control = LogController.make_controller()

    from cli.raft_admin_ops import (TRANSPORT_CHOICES, nodes_and_helper)
    from raft_ops.local_ops import LocalCollector 
    if not AIOCMD_AVAILABLE:
        print("This tool requires aiocmd. Please install with: pip install aiocmd")
        sys.exit(1)
    asyncio.run(main())
