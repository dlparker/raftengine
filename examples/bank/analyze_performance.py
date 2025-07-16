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


def extract_loop_count_from_filename(filename: str) -> Optional[int]:
    """Extract loop count from filename like 'teller_50_loops.json'"""
    match = re.search(r'_(\d+)_loops\.json$', filename)
    return int(match.group(1)) if match else None

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
        loop_total = statistics['loop_total']
        metrics['loop_total_mean'] = loop_total['mean']
        metrics['loop_total_total'] = loop_total['total']
    
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
    
    json_files = find_json_files(directory)
    
    # Load all measurement data
    datasets = {}
    loop_count = None
    transports = ['astream', 'aiozmq', 'fastapi', 'grpc']
    
    # Load base layer data
    if 'teller' in json_files:
        data = load_json_data(json_files['teller'])
        datasets['Bare Teller'] = data
        if not loop_count:
            loop_count = extract_loop_count_from_data(data) or extract_loop_count_from_filename(json_files['teller'].name)
    
    if 'collector' in json_files:
        data = load_json_data(json_files['collector'])
        datasets['Collector+Dispatcher'] = data
        if not loop_count:
            loop_count = extract_loop_count_from_data(data) or extract_loop_count_from_filename(json_files['collector'].name)
    
    # Load RPC data for each transport
    for transport in transports:
        rpc_key = f'rpc_{transport}'
        if rpc_key in json_files:
            data = load_json_data(json_files[rpc_key])
            datasets[f'{transport.upper()} RPC Stubs'] = data
            if not loop_count:
                loop_count = extract_loop_count_from_data(data) or extract_loop_count_from_filename(json_files[rpc_key].name)
    
    # Load Raft data for each transport
    for transport in transports:
        raft_key = f'raft_{transport}'
        if raft_key in json_files:
            data = load_json_data(json_files[raft_key])
            datasets[f'{transport.upper()} Raft Cluster'] = data
            if not loop_count:
                loop_count = extract_loop_count_from_data(data) or extract_loop_count_from_filename(json_files[raft_key].name)
    
    if not datasets:
        print(f"No timing data files found in {directory}")
        print("Expected files matching patterns: *teller*loops*.json, *collector*loops*.json, etc.")
        return
    
    # Extract metrics for each layer
    all_metrics = {}
    for layer_name, data in datasets.items():
        metrics = extract_key_metrics(data)
        all_metrics[layer_name] = metrics
    
    print("=" * 80)
    print("BANKING SYSTEM PERFORMANCE ANALYSIS - LAYER COST COMPARISON")
    if loop_count:
        print(f"Analysis based on {loop_count} loop iterations")
    print("=" * 80)
    print()
    
    # Report metadata
    for layer_name, data in datasets.items():
        if data and 'metadata' in data:
            metadata = data['metadata']
            print(f"{layer_name}:")
            print(f"  Mode: {metadata.get('mode', 'N/A')}")
            print(f"  Loops: {metadata.get('loops', 'N/A')}")
            print(f"  Transport: {metadata.get('transport', 'N/A')}")
            print()
    
    print("=" * 80)
    print("LOOP TOTAL PERFORMANCE (Mean time per complete test iteration)")
    print("=" * 80)
    
    # Get baseline (bare teller)
    baseline_mean = all_metrics.get('Bare Teller', {}).get('loop_total_mean', 0)
    
    # Build dynamic layer list in logical order
    layers = []
    if 'Bare Teller' in datasets:
        layers.append('Bare Teller')
    if 'Collector+Dispatcher' in datasets:
        layers.append('Collector+Dispatcher')
    
    # Add RPC layers
    for transport in transports:
        rpc_layer = f'{transport.upper()} RPC Stubs'
        if rpc_layer in datasets:
            layers.append(rpc_layer)
    
    # Add Raft layers  
    for transport in transports:
        raft_layer = f'{transport.upper()} Raft Cluster'
        if raft_layer in datasets:
            layers.append(raft_layer)
    
    for layer in layers:
        metrics = all_metrics.get(layer, {})
        mean_time = metrics.get('loop_total_mean', 0)
        total_time = metrics.get('loop_total_total', 0)
        if layer == 'Bare Teller':
            print(f"{layer:25s}: {mean_time:8.6f}s  (baseline)")
        else:
            overhead_pct, multiplier = calculate_overhead(baseline_mean, mean_time)
            print(f"{layer:25s}: {mean_time:8.6f}s  (+{overhead_pct:6.1f}% / {multiplier:5.2f}x)")
    
    print()
    print("=" * 80)
    print("OPERATION-SPECIFIC PERFORMANCE COMPARISON")
    print("=" * 80)
    
    # Compare key operations
    key_operations = [
        ('create_customer_mean', 'CREATE_CUSTOMER'),
        ('create_account_mean', 'CREATE_ACCOUNT'), 
        ('deposit_mean', 'DEPOSIT'),
        ('withdraw_mean', 'WITHDRAW'),
        ('transfer_mean', 'TRANSFER'),
        ('cash_check_mean', 'CASH_CHECK')
    ]
    
    for metric_key, op_name in key_operations:
        print(f"\n{op_name}:")
        baseline = all_metrics.get('Bare Teller', {}).get(metric_key, 0)
        prev_time = None
        
        for layer in layers:
            metrics = all_metrics.get(layer, {})
            op_time = metrics.get(metric_key, 0)
            
            if layer == 'Bare Teller':
                print(f"  {layer:23s}: {op_time:8.6f}s")
                prev_time = op_time
            else:
                overhead_pct, multiplier = calculate_overhead(baseline, op_time)
                layer_pct, layer_mult = calculate_overhead(prev_time, op_time)
                print(f"  {layer:23s}: {op_time:8.6f}s  (+{overhead_pct:6.1f}% / {multiplier:5.2f}x)",
                      f"  relative (+{layer_pct:6.1f}% / {layer_mult:5.2f}x)")
                prev_time = op_time
    
    print()
    print("=" * 80)
    print("SUMMARY OF ARCHITECTURAL COSTS")
    print("=" * 80)
    
    if baseline_mean > 0:
        # Build dynamic layers with overhead (excluding baseline)
        layers_with_overhead = []
        for layer in layers[1:]:  # Skip baseline
            mean_time = all_metrics.get(layer, {}).get('loop_total_mean', 0)
            if mean_time > 0:
                layers_with_overhead.append((layer, mean_time))
        
        print(f"Baseline (Bare Teller): {baseline_mean:.6f}s per iteration")
        print()
        
        for layer_name, mean_time in layers_with_overhead:
            overhead_pct, multiplier = calculate_overhead(baseline_mean, mean_time)
            print(f"Cost of {layer_name:25s}: {overhead_pct:6.1f}% overhead ({multiplier:5.2f}x slower)")
        
        # Calculate incremental costs
        print()
        print("INCREMENTAL LAYER COSTS:")
        
        collector_mean = all_metrics.get('Collector+Dispatcher', {}).get('loop_total_mean', 0)
        if collector_mean > 0:
            collector_overhead, _ = calculate_overhead(baseline_mean, collector_mean)
            print(f"  Collector+Dispatcher layer adds: {collector_overhead:6.1f}% overhead")
        
        # Show incremental costs for transport layers
        for transport in transports:
            rpc_layer = f'{transport.upper()} RPC Stubs'
            raft_layer = f'{transport.upper()} Raft Cluster'
            
            rpc_mean = all_metrics.get(rpc_layer, {}).get('loop_total_mean', 0)
            raft_mean = all_metrics.get(raft_layer, {}).get('loop_total_mean', 0)
            
            if rpc_mean > 0 and collector_mean > 0:
                rpc_incremental, _ = calculate_overhead(collector_mean, rpc_mean)
                print(f"  {transport.upper()} transport layer adds:     {rpc_incremental:6.1f}% additional overhead")
            
            if raft_mean > 0 and rpc_mean > 0:
                raft_incremental, _ = calculate_overhead(rpc_mean, raft_mean)
                print(f"  {transport.upper()} Raft consensus adds:     {raft_incremental:6.1f}% additional overhead")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
