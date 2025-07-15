from base.collector import Collector
from base.validate_teller import validate_teller
from base.demo_teller import demo_teller
from raft_stubs.stubs import CommandClient

async def validate(rpc_client, mode='demo', loops=1, use_random_data=False, 
                 print_timing=True, json_output=None, check_raft_message=False):
    """Common validation function for all stub clients
    
    Args:
        rpc_client: The RPC client instance
        mode: 'demo' or 'test' mode
        loops: Number of test iterations
        use_random_data: Use random data for testing
        print_timing: Print timing report (test mode only)
        json_output: Path to JSON output file
        check_raft_message: Test the raft_message stub
    """
    command_client = CommandClient(rpc_client)
    collector = Collector(command_client)
    
    # Prepare metadata for JSON export
    metadata = {
        'mode': mode,
        'transport': 'stub_client',
        'loops': loops,
        'random_data': use_random_data,
        'check_raft_message': check_raft_message
    }
    
    if mode == 'demo':
        if loops > 1:
            for i in range(loops):
                print(f"\n=== Demo Run {i+1}/{loops} ===")
                await demo_teller(collector, use_random_data=use_random_data)
        else:
            await demo_teller(collector, use_random_data=use_random_data)
    else:
        await validate_teller(collector, loops=loops, print_timing=print_timing, 
                            json_output=json_output, metadata=metadata)
        if loops > 1:
            print(f"✓ All {loops} test iterations passed successfully!")
        else:
            print("✓ Test passed successfully!")

    if check_raft_message:
        msg = "Howdy"
        result = await rpc_client.raft_message(msg)
        print(f"test of stub raft_message '{msg}' returned '{result}'")


def add_common_arguments(parser):
    """Add common arguments to argument parser"""
    parser.add_argument('mode', choices=['demo', 'test'], default='demo', nargs='?',
                        help='Choose between demo (user-friendly) or test (assertion-based) mode')
    parser.add_argument('--loops', type=int, default=1,
                        help='Number of test iterations to run (default: 1)')
    parser.add_argument('--random', action='store_true',
                        help='Use random data for names, addresses, and amounts')
    parser.add_argument('--no-timing', action='store_true',
                        help='Disable timing report (only for test mode)')
    parser.add_argument('--json-output', type=str, metavar='FILE',
                        help='Export timing statistics to JSON file')
    parser.add_argument('--check-raft', action='store_true',
                        help='Test the raft_message stub function')
