#!/usr/bin/env python
"""
Multi-Dataset Performance Graph Generator
Reads multiple JSON output files from measure.py client scaling tests and generates 
comparative matplotlib charts showing response time and throughput vs number of clients
for up to 4 different datasets.
"""
import json
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

def load_scaling_data(json_file: str) -> Dict[str, Any]:
    """Load and validate scaling test data from JSON file."""
    try:
        with open(json_file, 'r') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{json_file}': {e}")
        sys.exit(1)
    
    # Validate data format
    if not isinstance(raw_data, dict):
        print(f"Error: Expected JSON object in '{json_file}', got {type(raw_data).__name__}")
        sys.exit(1)
    
    # Check for new format with individual_test_results
    if "individual_test_results" not in raw_data or not isinstance(raw_data["individual_test_results"], list):
        print(f"Error: JSON file '{json_file}' must contain 'individual_test_results' array")
        sys.exit(1)
    
    if len(raw_data["individual_test_results"]) == 0:
        print(f"Error: individual_test_results array is empty in '{json_file}'")
        sys.exit(1)
    
    # Transform new format to expected format
    results = []
    for test_result in raw_data["individual_test_results"]:
        if "result" not in test_result or "results" not in test_result["result"]:
            print(f"Error: Invalid test result structure in '{json_file}': {test_result}")
            sys.exit(1)
        
        # Each result.results should contain exactly one item
        result_data = test_result["result"]["results"]
        if len(result_data) != 1:
            print(f"Error: Expected exactly one result per test in '{json_file}', got {len(result_data)}")
            sys.exit(1)
        
        results.append(result_data[0])
    
    # Get client range from test_specification
    client_range = {"min": 1, "max": 20}  # Default values
    if "test_specification" in raw_data and "client_range" in raw_data["test_specification"]:
        client_range = raw_data["test_specification"]["client_range"]
    
    # Get transport type for labeling
    transport = "unknown"
    if "test_specification" in raw_data and "transport" in raw_data["test_specification"]:
        transport = raw_data["test_specification"]["transport"]
    
    # Create transformed data structure
    data = {
        "test_type": "client_scaling",
        "client_range": client_range,
        "results": results,
        "transport": transport,
        "source_file": Path(json_file).stem
    }
    
    return data

def extract_chart_data(data: Dict[str, Any]) -> Tuple[List[int], List[float], List[float]]:
    """Extract client counts, response times, and throughput from scaling data."""
    results = data["results"]
    
    client_counts = []
    response_times = []
    throughputs = []
    
    for result in results:
        if not all(key in result for key in ["total_clients", "avg_latency_ms", "throughput_per_second"]):
            print(f"Error: Missing required fields in result: {result}")
            sys.exit(1)
        
        client_counts.append(result["total_clients"])
        response_times.append(result["avg_latency_ms"])
        throughputs.append(result["throughput_per_second"])
    
    return client_counts, response_times, throughputs

def generate_comparative_chart(datasets: List[Dict[str, Any]], output_file: str) -> None:
    """Generate comparative matplotlib chart showing multiple datasets."""
    if len(datasets) > 4:
        print("Error: Maximum of 4 datasets supported")
        sys.exit(1)
    
    # Color schemes for up to 4 datasets
    colors = [
        {'response': '#d62728', 'throughput': '#1f77b4'},  # red/blue
        {'response': '#ff7f0e', 'throughput': '#2ca02c'},  # orange/green  
        {'response': '#9467bd', 'throughput': '#8c564b'},  # purple/brown
        {'response': '#e377c2', 'throughput': '#7f7f7f'}   # pink/gray
    ]
    
    # Line styles for differentiation
    line_styles = ['-', '--', '-.', ':']
    markers = ['o', 's', '^', 'D']
    
    # Create figure with larger size for multiple datasets
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))
    
    # Get overall client range for consistent x-axis
    all_client_ranges = []
    for data in datasets:
        client_counts, _, _ = extract_chart_data(data)
        all_client_ranges.extend(client_counts)
    
    min_clients = min(all_client_ranges)
    max_clients = max(all_client_ranges)
    
    # Set up figure title
    transport_names = [data['transport'] for data in datasets]
    fig.suptitle(f'Performance Comparison: {", ".join(transport_names)} ({min_clients}-{max_clients} Clients)', 
                 fontsize=16, fontweight='bold')
    
    # Plot Response Time (left subplot)
    ax1.set_xlabel('Number of Clients', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Response Time (ms)', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    
    response_lines = []
    for i, data in enumerate(datasets):
        client_counts, response_times, _ = extract_chart_data(data)
        color = colors[i]['response']
        line = ax1.plot(client_counts, response_times, 
                       color=color, marker=markers[i], linewidth=2, markersize=6,
                       linestyle=line_styles[i], 
                       label=f'{data["transport"]} Response Time')
        response_lines.extend(line)
    
    # Plot Throughput (right subplot)  
    ax2.set_xlabel('Number of Clients', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Throughput (requests/sec)', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    throughput_lines = []
    for i, data in enumerate(datasets):
        client_counts, _, throughputs = extract_chart_data(data)
        color = colors[i]['throughput']
        line = ax2.plot(client_counts, throughputs,
                       color=color, marker=markers[i], linewidth=2, markersize=6,
                       linestyle=line_styles[i],
                       label=f'{data["transport"]} Throughput')
        throughput_lines.extend(line)
    
    # Set consistent x-axis limits and integer ticks
    for ax in [ax1, ax2]:
        ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.set_xlim(min_clients - 0.5, max_clients + 0.5)
    
    # Add legends
    ax1.legend(loc='upper left', fontsize=10)
    ax2.legend(loc='upper left', fontsize=10)
    
    # Calculate and display comparative statistics
    stats_text = "Performance Summary:\\n"
    for i, data in enumerate(datasets):
        client_counts, response_times, throughputs = extract_chart_data(data)
        
        avg_response_time = sum(response_times) / len(response_times)
        avg_throughput = sum(throughputs) / len(throughputs)
        max_throughput = max(throughputs)
        max_throughput_clients = client_counts[throughputs.index(max_throughput)]
        min_response_time = min(response_times)
        min_response_time_clients = client_counts[response_times.index(min_response_time)]
        
        stats_text += f"{data['transport']}: "
        stats_text += f"Avg RT: {avg_response_time:.2f}ms, "
        stats_text += f"Avg TP: {avg_throughput:.1f} req/sec, "
        stats_text += f"Peak TP: {max_throughput:.1f} req/sec @ {max_throughput_clients} clients\\n"
    
    # Position the stats text box at the bottom
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    fig.text(0.5, 0.02, stats_text, transform=fig.transFigure, fontsize=9,
             verticalalignment='bottom', horizontalalignment='center', bbox=props)
    
    # Adjust layout to prevent clipping and make room for stats
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)
    
    # Save the figure
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    
    print(f"Comparative chart generated: {output_file}")
    print(f"Datasets compared: {len(datasets)}")
    for data in datasets:
        client_counts, response_times, throughputs = extract_chart_data(data)
        max_throughput = max(throughputs)
        max_throughput_clients = client_counts[throughputs.index(max_throughput)]
        min_response_time = min(response_times)
        min_response_time_clients = client_counts[response_times.index(min_response_time)]
        print(f"  {data['transport']}: Peak throughput {max_throughput:.1f} req/sec @ {max_throughput_clients} clients, "
              f"Best response time {min_response_time:.2f}ms @ {min_response_time_clients} clients")
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate comparative performance charts from multiple measure.py scaling test results')
    
    parser.add_argument('json_files', nargs='+', 
                        help='JSON files containing client scaling test results (max 4 files)')
    parser.add_argument('--output', '-o', 
                        help='Output image file (default: comparison.png)')
    
    args = parser.parse_args()
    
    if len(args.json_files) > 4:
        print("Error: Maximum of 4 datasets supported")
        sys.exit(1)
    
    if len(args.json_files) < 2:
        print("Error: At least 2 datasets required for comparison")
        sys.exit(1)
    
    # Determine output filename
    if args.output:
        output_file = args.output
    else:
        output_file = "comparison.png"
    
    # Load and process all datasets
    datasets = []
    for json_file in args.json_files:
        print(f"Loading scaling data from {json_file}...")
        data = load_scaling_data(json_file)
        print(f"  Found {len(data['results'])} test results for {data['transport']}")
        datasets.append(data)
    
    # Generate comparative chart
    generate_comparative_chart(datasets, output_file)

if __name__ == "__main__":
    main()