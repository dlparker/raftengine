#!/usr/bin/env python
import asyncio
import shutil
import argparse
import json
from pathlib import Path
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig

class Config:

    def __init__(self, base_port=50090, all_local=True, hosts=None, slow_timeouts=False):
        self.base_port = base_port
        self.all_local = all_local
        self.hosts = hosts
        self.slow_timeouts = slow_timeouts
        self.initial_cluster_config = None
        
        if not all_local and (hosts is None or len(hosts) < 3):
            raise Exception('if all_local is not true, a list of at least three hosts must be provided')
        if all_local and hosts is not None:
            raise Exception('if all_local is true, a list of hosts is not allowed')

        self.node_uris = []
        if all_local:
            for port in range(base_port, base_port + 3):
                uri = f"as_raft://127.0.0.1:{port}"
                self.node_uris.append(uri)
        else:
            used_hosts = set()
            for host in hosts:
                port = base_port
                if host in ("127.0.0.1", "localhost"):
                    raise Exception("Can't use loopback address in real host list")
                uri = f"as_raft://{host}:{port}"
                while uri in self.node_uris:
                    port += 1
                    uri = f"as_raft://{host}:{port}"
                self.node_uris.append(uri)
        
    
    def build_config(self, work_dir_base="/tmp"):
        if self.slow_timeouts:
            heartbeat_period=10000
            election_timeout_min=10000
            election_timeout_max=10000
        else:
            heartbeat_period=0.01
            election_timeout_min=0.25
            election_timeout_max=0.35
        self.initial_cluster_config = ClusterInitConfig(node_uris=self.node_uris,
                                                        heartbeat_period=heartbeat_period,
                                                        election_timeout_min=election_timeout_min,
                                                        election_timeout_max=election_timeout_max,
                                                        use_pre_vote=False,
                                                        use_check_quorum=True,
                                                        max_entries_per_message=10,
                                                        use_dynamic_config=False)
        for index,uri in enumerate(self.node_uris):
            work_dir = Path(work_dir_base, f"simple_raft_server.{index}")
            if not work_dir.exists():
                work_dir.mkdir()
        return self.initial_cluster_config
            
        
async def main():

    parser = argparse.ArgumentParser(description="Create Counters Raft Server Cluster")
    
    parser.add_argument('-b', '--base_port', type=int, default=50090,
                        help='Port number for first node on each host')
    parser.add_argument('-s', '--slow_timeouts', action='store_true',  help='Very long timeout values easing debug logging load')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-n', '--nodes', nargs='+', type=str, help='List of host names to run nodes')    
    group.add_argument('-a', '--all_local', action='store_true',  help='All servers on this host')
    args = parser.parse_args()

    config = Config(args.base_port, args.all_local, args.nodes, args.slow_timeouts)

    print(json.dumps(config.build_config(), indent=2, default=lambda o:o.__dict__))
    
if __name__=="__main__":
    asyncio.run(main())
