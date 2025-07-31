#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
import subprocess 
async def main():
    parser = argparse.ArgumentParser()
    
    parser.add_argument("-x", "--min-clients", type=int, required=True, help="Minimum number of clients for range testing")
    parser.add_argument("-y", "--max-clients", type=int, required=True,
                        help="Maximum number of clients for range testing ")
    parser.add_argument("-s", "--clients-step", type=int,
                        help="Increase in client count per step (requires --min-clients and requires --max-clients)", default=1)
    parser.add_argument("-l", "--loops", type=int, default=1, help="Total loops for each run, all clients summed")
    parser.add_argument("-w","--warmup", type=int, default=10, help="Number of warmup loops per client (default: 10)")
    parser.add_argument("-j", "--json-output", type=str, help="Export results to JSON file (appends if exists)", required=True)
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi',],
                        default='aiozmq',
                        help='Transport mechanism to use')
    
    args = parser.parse_args()

    print(f"Running {args.loops} for {args.transport} clients {args.min_clients} to {args.max_clients} step {args.clients_step}")
    for cc in range(args.min_clients, args.max_clients + 1):
        lcount = int(args.loops / cc)
        cmd = ["./measure2.py", "-l", f"{lcount}", "--clients", f"{cc}", "-t", args.transport, "--json-output", args.json_output]
        print(" ".join(cmd))
        p = subprocess.Popen(cmd)
        p.wait()
        await asyncio.sleep(1.0)
        
    
if __name__=="__main__":
    asyncio.run(main())
    
