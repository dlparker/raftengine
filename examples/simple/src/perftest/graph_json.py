#!/usr/bin/env python
"""
Performance Graph Generator
Reads JSON output from time_raft.py client scaling tests and generates matplotlib charts
showing response time and throughput vs number of clients.
"""
import json
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any
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
        print(f"Error: Expected JSON object, got {type(raw_data).__name__}")
        sys.exit(1)
    
    # Check for new format with individual_test_results
    if "individual_test_results" not in raw_data or not isinstance(raw_data["individual_test_results"], list):
        print("Error: JSON file must contain 'individual_test_results' array")
        sys.exit(1)
    
    if len(raw_data["individual_test_results"]) == 0:
        print("Error: individual_test_results array is empty")
        sys.exit(1)
    
    # Transform new format to expected format
    results = []
    for test_result in raw_data["individual_test_results"]:
        if "result" not in test_result or "results" not in test_result["result"]:
            print(f"Error: Invalid test result structure: {test_result}")
            sys.exit(1)
        
        # Each result.results should contain exactly one item
        result_data = test_result["result"]["results"]
        if len(result_data) != 1:
            print(f"Error: Expected exactly one result per test, got {len(result_data)}")
            sys.exit(1)
        
        results.append(result_data[0])
    
    # Get client range from test_specification
    client_range = {"min": 1, "max": 20}  # Default values
    if "test_specification" in raw_data and "client_range" in raw_data["test_specification"]:
        client_range = raw_data["test_specification"]["client_range"]
    
    # Create transformed data structure
    data = {
        "test_type": "client_scaling",
        "client_range": client_range,
        "results": results
    }
    
    return data

def extract_chart_data(data: Dict[str, Any]) -> tuple:
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

def generate_matplotlib_chart(data: Dict[str, Any], output_file: str) -> None:
    """Generate matplotlib chart showing response time and throughput vs client count."""
    client_counts, response_times, throughputs = extract_chart_data(data)
    
    # Get metadata
    client_range = data.get("client_range", {})
    min_clients = client_range.get("min", min(client_counts))
    max_clients = client_range.get("max", max(client_counts))
    
    # Create figure and primary axis
    fig, ax1 = plt.subplots(figsize=(12, 8))
    
    # Set up the figure title and styling
    fig.suptitle(f'Performance Scaling:({min_clients}-{max_clients} Clients)', 
                 fontsize=16, fontweight='bold')
    
    # Primary y-axis (Response Time)
    color1 = 'red'
    ax1.set_xlabel('Number of Clients', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Response Time (ms)', color=color1, fontsize=12, fontweight='bold')
    line1 = ax1.plot(client_counts, response_times, color=color1, marker='o', linewidth=2, 
                     markersize=6, label='Response Time')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, alpha=0.3)
    
    # Secondary y-axis (Throughput)
    ax2 = ax1.twinx()
    color2 = 'blue'
    ax2.set_ylabel('Throughput (requests/sec)', color=color2, fontsize=12, fontweight='bold')
    line2 = ax2.plot(client_counts, throughputs, color=color2, marker='s', linewidth=2, 
                     markersize=6, label='Throughput')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # Set reasonable y-axis limits for throughput to avoid misleading visual scaling
    min_throughput = min(throughputs)
    max_throughput = max(throughputs)
    throughput_range = max_throughput - min_throughput
    # Use either 20% padding or start from 0 if the minimum is close to 0
    if min_throughput < throughput_range * 0.5:
        y_min = 0
    else:
        y_min = max(0, min_throughput - throughput_range * 0.2)
    y_max = max_throughput + throughput_range * 0.1
    ax2.set_ylim(y_min, y_max)
    
    # Set x-axis to show integer ticks only
    ax1.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax1.set_xlim(min(client_counts) - 0.5, max(client_counts) + 0.5)
    
    # Add legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', fontsize=10)
    
    # Calculate and display key statistics
    avg_response_time = sum(response_times) / len(response_times)
    avg_throughput = sum(throughputs) / len(throughputs)
    max_throughput = max(throughputs)
    max_throughput_clients = client_counts[throughputs.index(max_throughput)]
    min_response_time = min(response_times)
    min_response_time_clients = client_counts[response_times.index(min_response_time)]
    
    # Add annotations for peak values
    # Peak throughput annotation
    peak_idx = throughputs.index(max_throughput)
    ax2.annotate(f'Peak: {max_throughput:.1f} req/sec\nat {max_throughput_clients} clients',
                xy=(max_throughput_clients, max_throughput),
                xytext=(max_throughput_clients + 0.5, max_throughput + 10),
                arrowprops=dict(arrowstyle='->', color=color2, alpha=0.7),
                fontsize=9, color=color2, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='lightblue', alpha=0.7))
    
    # Best response time annotation
    best_idx = response_times.index(min_response_time)
    ax1.annotate(f'Best: {min_response_time:.1f}ms\nat {min_response_time_clients} clients',
                xy=(min_response_time_clients, min_response_time),
                xytext=(min_response_time_clients + 0.5, min_response_time + 2),
                arrowprops=dict(arrowstyle='->', color=color1, alpha=0.7),
                fontsize=9, color=color1, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='lightcoral', alpha=0.7))
    
    # Add statistics text box
    stats_text =   "Performance Summary: "
    stats_text += f"Clients: {min_clients}-{max_clients} "
    stats_text += f"Avg Response Time: {avg_response_time:.2f} ms "
    stats_text += f"Avg Throughput: {avg_throughput:.1f} req/sec "
    stats_text += f"Peak Throughput: {max_throughput:.1f} req/sec at {max_throughput_clients} clients "
    stats_text += f"Best Response Time: {min_response_time:.2f} ms at {min_response_time_clients} clients"
    
    # Position the text box in the lower right
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax1.text(0.98, 0.02, stats_text, transform=ax1.transAxes, fontsize=9,
            verticalalignment='bottom', horizontalalignment='right', bbox=props)
    
    # Adjust layout to prevent clipping
    plt.tight_layout()
    
    # Save the figure
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    
    print(f"Matplotlib chart generated: {output_file}")
    print(f"Client range: {min_clients}-{max_clients}")
    print(f"Peak throughput: {max_throughput:.2f} req/sec at {max_throughput_clients} clients")
    print(f"Best response time: {min_response_time:.2f} ms at {min_response_time_clients} clients")
    
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate matplotlib performance charts from measure.py scaling test results')
    
    parser.add_argument('input_file', 
                        help='JSON file containing client scaling test results')
    parser.add_argument('--output', '-o', 
                        help='Output image file (default: input_file.png)')
    
    args = parser.parse_args()
    
    # Determine output filename
    if args.output:
        output_file = args.output
    else:
        input_path = Path(args.input_file)
        output_file = str(input_path.with_suffix('.png'))
    
    # Load and process data
    print(f"Loading scaling data from {args.input_file}...")
    data = load_scaling_data(args.input_file)
    
    print(f"Found {len(data['results'])} test results")
    
    # Generate chart
    generate_matplotlib_chart(data, output_file)

if __name__ == "__main__":
    main()
