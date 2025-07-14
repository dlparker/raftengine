from base.collector import Collector
from base.validate_teller import validate_teller

async def validate(rpc_client):
    collector = Collector(rpc_client)
    await validate_teller(collector)

    msg = "Howdy"
    result = await rpc_client.raft_message(msg)
    print(f"test of stub raft_message '{msg}' returned '{result}'")
