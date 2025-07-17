
TRANSPORT_CHOICES = ['astream', 'aiozmq', 'fastapi', 'grpc']

def nodes_and_helper(transport, base_port, node_count=3):
    # Validate combination
    if transport == "astream":
        from tx_astream.rpc_helper import RPCHelper
        base_port = base_port
    elif transport == "aiozmq":
        from tx_aiozmq.rpc_helper import RPCHelper
        base_port = base_port + 100
    elif transport == "fastapi":
        from tx_fastapi.rpc_helper import RPCHelper
        base_port = base_port + 200
    elif transport == "grpc":
        from tx_grpc.rpc_helper import RPCHelper
        base_port = base_port + 300
    else:
        raise Exception(f"invalid transport {transport}, try {valid_txs}")
    nodes = []
    for pnum in range(base_port, base_port + node_count):
        nodes.append(f"{transport}://127.0.0.1:{pnum}")

    return nodes, RPCHelper
