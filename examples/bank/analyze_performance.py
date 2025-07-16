#!/usr/bin/env python3
"""
Performance Analysis Tool for Banking System Validators
Analyzes timing data from validator JSON outputs and generates comparison report.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional


def extract_loop_count_from_data(data: Dict[str, Any]) -> Optional[int]:
    """Extract loop count from JSON metadata"""
    if 'metadata' in data and 'loops' in data['metadata']:
        return data['metadata']['loops']
    return None

def find_json_files(directory: Path) -> Dict[str, Path]:
    """Find relevant JSON files in directory and classify them by type"""
    files = {}
    transports = ['astream', 'aiozmq', 'fastapi', 'grpc']
    
    for json_file in directory.glob("*.json"):
        filename = json_file.name.lower()
        
        if 'teller' in filename and 'loops' in filename:
            files['teller'] = json_file
        elif 'collector' in filename and 'loops' in filename:
            files['collector'] = json_file
        else:
            # Check for RPC files with transport types
            for transport in transports:
                if f'rpc_{transport}' in filename and 'loops' in filename:
                    files[f'rpc_{transport}'] = json_file
                    break
                elif f'raft_{transport}' in filename and 'loops' in filename:
                    files[f'raft_{transport}'] = json_file
                    break
    
    return files

def load_json_data(file_path: Path) -> Dict[str, Any]:
    """Load and return JSON data from file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {file_path} not found")
        return {}


def extract_key_metrics(data: Dict[str, Any]) -> Dict[str, float]:
    """Extract key performance metrics from timing data"""
    if not data or 'statistics' not in data:
        return {}
    
    statistics = data['statistics']
    metrics = {}
    
    # Get loop_total (most important metric)
    if 'loop_total' in statistics:
        loop_time = statistics['loop_total']
        metrics['loop_time_mean'] = loop_time['mean']
        metrics['loop_time_total'] = loop_time['total']
    
    # Get operation-specific metrics
    key_operations = [
        'create_customer', 'create_account', 'deposit', 
        'withdraw', 'transfer', 'cash_check'
    ]
    
    for op in key_operations:
        if op in statistics:
            metrics[f'{op}_mean'] = statistics[op]['mean']
    
    return metrics



def calculate_overhead(baseline: float, current: float) -> tuple:
    """Calculate overhead as percentage and multiplier"""
    if baseline == 0:
        return 0.0, 1.0
    
    overhead_pct = ((current - baseline) / baseline) * 100
    multiplier = current / baseline
    return overhead_pct, multiplier



def load_data(directory):

    json_files = find_json_files(directory)
    
    # Load all measurement data
    datasets = {}
    loop_count = None
    transports = ['astream', 'aiozmq', 'fastapi', 'grpc']

    metrics = {}
    # Load base layer data
    if 'teller' in json_files:
        data = load_json_data(json_files['teller'])
        datasets['teller'] = data
        metrics['teller'] = extract_key_metrics(data)
        if not loop_count:
            loop_count = extract_loop_count_from_data(data)
    if not loop_count:
        raise Exception('cannot determine loop count')
    
    if 'collector' in json_files:
        data = load_json_data(json_files['collector'])
        datasets['collector'] = data
        metrics['collector'] = extract_key_metrics(data)
            
    # Load RPC data for each transport
    datasets['rpc'] = data_rpc = {}
    metrics['rpc'] = metrics_rpc = {}
    for transport in transports:
        rpc_key = f'rpc_{transport}'
        if rpc_key in json_files:
            data = load_json_data(json_files[rpc_key])
            data_rpc[transport] = data
            metrics_rpc[transport] = extract_key_metrics(data)
            
    # Load Raft data for each transport
    datasets['raft'] = data_raft = {}
    metrics['raft'] = metrics_raft = {}
    for transport in transports:
        raft_key = f'raft_{transport}'
        if raft_key in json_files:
            data = load_json_data(json_files[raft_key])
            data_raft[transport] = data
            metrics_raft[transport] = extract_key_metrics(data)
    
    if not datasets:
        print(f"No timing data files found in {directory}")
        print("Expected files matching patterns: *teller*loops*.json, *collector*loops*.json, etc.")
        raise SystemExit(1)
    
    return datasets, metrics


def build_ordered(metrics):
    # get the methods
    methods = []
    for key in metrics['teller']:
        if not key.startswith('loop'):
            methods.append(key)

    xports = list(metrics['rpc'].keys())
    print(xports)
            
    method_times = {}
    for method in methods:
        method_times[method] = mdict = {}
        for layer in ['teller', 'collector']:
            mean = metrics[layer][method]
            mdict[layer] = mean=mean
        mdict['remotes'] = rems = {}
        for xport in xports:
            rems[xport] = modes = {}
            for mode in ['rpc', 'raft']:
                modes[mode] = metrics[mode][xport][method]
    loop_time_means = {}
    for layer in ['teller', 'collector']:
        loop_time_means[layer] = metrics[layer]['loop_time_mean']
        loop_time_means['remotes'] = rems = {}
        for xport in xports:
            rems[xport] = modes = {}
            for mode in ['rpc', 'raft']:
                modes[mode] = metrics[mode][xport]['loop_time_mean']
            
    loop_time_totals = {}
    for layer in ['teller', 'collector']:
        loop_time_totals[layer] = metrics[layer]['loop_time_total']
        loop_time_totals['remotes'] = rems = {}
        for xport in xports:
            rems[xport] = modes = {}
            for mode in ['rpc', 'raft']:
                modes[mode] = metrics[mode][xport]['loop_time_total']
            
    return dict(methods=method_times, loops=dict(mean=loop_time_means, total=loop_time_totals))

def print_report(ordered_metrics):
    od = ordered_metrics
    sample = od['methods']['deposit_mean']['remotes']
    if len(sample) > 1:
        multi_xport = True
    else:
        multi_xport = False
    for name,specs in od['methods'].items():
        m_name = "_".join(name.split('_')[:-1])
        section = m_name
        h_layer = "Layer"
        h_value = "Mean"
        h_d1 = "VS Teller"
        h_d2 = "VS Last Layer"
        print(f"{section:15s} {h_layer:<20s}  {h_value:>12s} {h_d1:^19s} {h_d2:^19s}")
        section = ""
        print(f"{section:15s}" + '-'*80)
        for layer in ['teller', 'collector']:
            mean = specs[layer]
            if layer == "teller":
                section = m_name
                teller = mean
                base_diff = ""
            else:
                section = ""
                o_v_base,m_v_base = calculate_overhead(teller, mean)
                collector = mean
                base_diff = f"(+{o_v_base:6.1f}% / {m_v_base:5.2f}x)"
            print(f"{section:15s} {layer.capitalize():20s}: {mean:12.8f} {base_diff}")
        for xport,rspecs in specs['remotes'].items():
            if multi_xport:
                print(f"{section:15s}" + '-'*80)
            for layer in ['rpc', 'raft']:
                mean = rspecs[layer]
                l_name = xport.upper() + "  " + layer.upper()
                o_v_base,m_v_base = calculate_overhead(teller, mean)
                if layer == "rpc":
                    o_v_prev,m_v_prev = calculate_overhead(collector, mean)
                    rpc = mean
                else:
                    o_v_prev,m_v_prev = calculate_overhead(rpc, mean)
                prev_diff = f"(+{o_v_prev:6.1f}% / {m_v_prev:5.2f}x)"
                base_diff = f"(+{o_v_base:6.1f}% / {m_v_base:5.2f}x)"
                print(f"{section:15s} {l_name:20s}: {mean:12.8f} {base_diff} {prev_diff}")
                    
        print('+'*95)

    for ltype,lspecs in od['loops'].items():
        section = f"loops {ltype}"
        h_layer = "Layer"
        if "mean" in ltype:
            h_value = "Mean"
        else:
            h_value = "Total"
        h_d1 = "VS Teller"
        h_d2 = "VS Last Layer"
        print(f"{section:15s} {h_layer:<20s}  {h_value:>12s} {h_d1:^19s} {h_d2:^19s}")
        section = ""
        print(f"{section:15s}" + '-'*80)
        for layer in ['teller', 'collector']:
            total = lspecs[layer]
            if layer == "teller":
                teller = total
                base_diff = ""
            else:
                collector = total
                o_v_base,m_v_base = calculate_overhead(teller, total)
                base_diff = f"(+{o_v_base:6.1f}% / {m_v_base:5.2f}x)"
            print(f"{section:15s} {layer.capitalize():20s}: {total:12.8f} {base_diff}")
        for xport,rspecs in lspecs['remotes'].items():
            if multi_xport:
                print(f"{section:15s}" + '-'*80)
            for layer in ['rpc', 'raft']:
                total = rspecs[layer]
                l_name = xport.upper() + "  " + layer.upper()
                o_v_base,m_v_base = calculate_overhead(teller, total)
                if layer == "rpc":
                    o_v_prev,m_v_prev = calculate_overhead(collector, total)
                    rpc = total
                else:
                    o_v_prev,m_v_prev = calculate_overhead(rpc, total)
                prev_diff = f"(+{o_v_prev:6.1f}% / {m_v_prev:5.2f}x)"
                base_diff = f"(+{o_v_base:6.1f}% / {m_v_base:5.2f}x)"
                print(f"{section:15s} {l_name:20s}: {total:12.8f} {base_diff} {prev_diff}")
        print('+'*95)
        
    
def main():
    parser = argparse.ArgumentParser(
        description="Analyze performance data from banking system validators"
    )
    parser.add_argument(
        "directory", 
        nargs="?", 
        default=".", 
        help="Directory containing JSON timing files (default: current directory)"
    )
    args = parser.parse_args()
    
    # Find JSON files in the specified directory
    directory = Path(args.directory)
    if not directory.exists():
        print(f"Error: Directory '{directory}' not found")
        return

    datasets,metrics = load_data(directory)
    from pprint import pprint
    #pprint(metrics)
    ordered = build_ordered(metrics)
    #pprint(ordered)
    print_report(ordered)


if __name__ == "__main__":
    main()
    
