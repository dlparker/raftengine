#!/usr/bin/env python
import asyncio
import argparse
import json
from pathlib import Path
import sys
from raftengine.api.deck_config import ClusterInitConfig
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

async def main():
    
    parser = argparse.ArgumentParser(description="Counters Raft Server Local Cluster starter")
    parser.add_argument('config_file', 
                        help='JSON file containing cluster config captured from running cluster, or intitial config (see -i)')
    parser.add_argument('-i', '--initial', action="store_true", help="file contains initial config, not captured config")
    args = parser.parse_args()

    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{config_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{config_file}': {e}")
        sys.exit(1)

    if args.initial:
        config = ClusterInitialConfig(**config_data)
    else:
        settings = ClusterSettings(**config_data['settings'])
        nodes = []
        for nr in config_data['nodes']:
            nodes.append(NodeRec(**nr))
        config = ClusterConfig(nodes, settings=settings)

if __name__=="__main__":
    asyncio.run(main())
