#!/usr/bin/env python3
"""
Performance Analysis Tool for Banking System Validators
Analyzes timing data from validator JSON outputs and generates comparison report.
"""

import json
from pathlib import Path
from typing import Dict, Any


def load_json_data(file_path: str) -> Dict[str, Any]:
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
    # Load all measurement data
    datasets = {
        'Bare Teller': load_json_data('teller_200_loops.json'),
        'Collector+Dispatcher': load_json_data('collector_200_loops.json'),
        'gRPC RPC Stubs': load_json_data('rpc_grpc_200_loops.json'),
        'gRPC Raft Cluster': load_json_data('raft_grpc_200_loops.json')
    }
    
    # Extract metrics for each layer
    all_metrics = {}
    for layer_name, data in datasets.items():
        all_metrics[layer_name] = extract_key_metrics(data)
    
    print("=" * 80)
    print("BANKING SYSTEM PERFORMANCE ANALYSIS - LAYER COST COMPARISON")
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
    
    layers = ['Bare Teller', 'Collector+Dispatcher', 'gRPC RPC Stubs', 'gRPC Raft Cluster']
    
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
        
        for layer in layers:
            metrics = all_metrics.get(layer, {})
            op_time = metrics.get(metric_key, 0)
            
            if layer == 'Bare Teller':
                print(f"  {layer:23s}: {op_time:8.6f}s")
            else:
                overhead_pct, multiplier = calculate_overhead(baseline, op_time)
                print(f"  {layer:23s}: {op_time:8.6f}s  (+{overhead_pct:6.1f}% / {multiplier:5.2f}x)")
    
    print()
    print("=" * 80)
    print("SUMMARY OF ARCHITECTURAL COSTS")
    print("=" * 80)
    
    if baseline_mean > 0:
        layers_with_overhead = [
            ('Collector+Dispatcher', all_metrics.get('Collector+Dispatcher', {}).get('loop_total_mean', 0)),
            ('gRPC RPC Stubs', all_metrics.get('gRPC RPC Stubs', {}).get('loop_total_mean', 0)),
            ('gRPC Raft Cluster', all_metrics.get('gRPC Raft Cluster', {}).get('loop_total_mean', 0))
        ]
        
        print(f"Baseline (Bare Teller): {baseline_mean:.6f}s per iteration")
        print()
        
        for layer_name, mean_time in layers_with_overhead:
            if mean_time > 0:
                overhead_pct, multiplier = calculate_overhead(baseline_mean, mean_time)
                print(f"Cost of {layer_name:20s}: {overhead_pct:6.1f}% overhead ({multiplier:5.2f}x slower)")
        
        # Calculate incremental costs
        print()
        print("INCREMENTAL LAYER COSTS:")
        collector_mean = all_metrics.get('Collector+Dispatcher', {}).get('loop_total_mean', 0)
        rpc_mean = all_metrics.get('gRPC RPC Stubs', {}).get('loop_total_mean', 0)
        raft_mean = all_metrics.get('gRPC Raft Cluster', {}).get('loop_total_mean', 0)
        
        if collector_mean > 0:
            collector_overhead, _ = calculate_overhead(baseline_mean, collector_mean)
            print(f"  Collector+Dispatcher layer adds: {collector_overhead:6.1f}% overhead")
        
        if rpc_mean > 0 and collector_mean > 0:
            rpc_incremental, _ = calculate_overhead(collector_mean, rpc_mean)
            print(f"  gRPC transport layer adds:     {rpc_incremental:6.1f}% additional overhead")
        
        if raft_mean > 0 and rpc_mean > 0:
            raft_incremental, _ = calculate_overhead(rpc_mean, raft_mean)
            print(f"  Raft consensus layer adds:     {raft_incremental:6.1f}% additional overhead")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()