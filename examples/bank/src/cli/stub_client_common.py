from base.collector import Collector
from base.validate_teller import validate_teller
from raft_stubs.stubs import CommandClient

async def validate(rpc_client, check_raft_message=False):
    command_client = CommandClient(rpc_client)
    collector = Collector(command_client)
    await validate_teller(collector)

    if check_raft_message:
        msg = "Howdy"
        result = await rpc_client.raft_message(msg)
        print(f"test of stub raft_message '{msg}' returned '{result}'")
