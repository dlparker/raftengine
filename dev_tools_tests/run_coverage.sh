#!/bin/bash
# Simple script to run dev_tools tests with HTML coverage
# 
# Usage:
#   ./run_coverage.sh           # Terminal coverage report
#   ./run_coverage.sh --html    # HTML coverage report

set -e

cd "$(dirname "$0")/.."

# Clean up any existing coverage data
rm -f .coverage*

echo "Running dev_tools tests with coverage..."

if [[ "$1" == "--html" ]]; then
    # Run with HTML coverage
    python -m pytest dev_tools_tests/ \
        --cov=dev_tools \
        --cov-report=html:dev_tools_tests/htmlcov \
        --cov-report=term-missing \
        -v
    
    echo ""
    echo "HTML coverage report generated at: dev_tools_tests/htmlcov/index.html"
    echo "Open with: file://$(pwd)/dev_tools_tests/htmlcov/index.html"
else
    # Run with terminal coverage only
    python -m pytest dev_tools_tests/ \
        --cov=dev_tools \
        --cov-report=term-missing \
        -v
fi

echo ""
echo "Coverage complete!"