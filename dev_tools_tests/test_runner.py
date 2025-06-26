#!/usr/bin/env python
"""Test runner for dev_tools_tests

Runs all tests in the dev_tools_tests directory and provides summary.
Can be used for quick validation of dev_tools functionality.

Usage:
    python test_runner.py           # Run tests without coverage
    python test_runner.py --cov     # Run tests with coverage report
    python test_runner.py --html    # Run tests with HTML coverage report
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_tests(coverage_mode=None):
    """Run all tests in dev_tools_tests directory
    
    Args:
        coverage_mode: None, 'report', or 'html' for coverage options
    """
    tests_dir = Path(__file__).parent
    
    # Set up environment
    env = os.environ.copy()
    env['PYTHONPATH'] = str(tests_dir.parent)
    env['PYTHONBREAKPOINT'] = 'ipdb.set_trace'
    
    # Find all test files (excluding test_runner.py itself)
    test_files = [f for f in tests_dir.glob('test_*.py') if f.name != 'test_runner.py']
    
    if not test_files:
        print("No test files found in dev_tools_tests directory")
        return 1
    
    print(f"Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"  - {test_file.name}")
    print()
    
    # Run tests
    all_passed = True
    results = {}
    
    for test_file in sorted(test_files):
        print(f"Running {test_file.name}...")
        
        try:
            # Build pytest command
            cmd = [sys.executable, '-m', 'pytest', str(test_file), '-v', '--tb=short']
            
            # Add coverage options if requested
            if coverage_mode:
                cmd.extend([
                    '--cov=dev_tools',
                    '--cov-config=dev_tools_tests/.coveragerc'
                ])
                # Only add append flag after first test
                if test_file != test_files[0]:
                    cmd.append('--cov-append')
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=tests_dir.parent)
            
            if result.returncode == 0:
                results[test_file.name] = "PASSED"
                print(f"  ✓ {test_file.name} - PASSED")
            else:
                results[test_file.name] = "FAILED"
                all_passed = False
                print(f"  ✗ {test_file.name} - FAILED")
                print(f"    STDOUT: {result.stdout}")
                print(f"    STDERR: {result.stderr}")
                
        except Exception as e:
            results[test_file.name] = f"ERROR: {e}"
            all_passed = False
            print(f"  ✗ {test_file.name} - ERROR: {e}")
        
        print()
    
    # Summary
    print("=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    passed_count = sum(1 for status in results.values() if status == "PASSED")
    total_count = len(results)
    
    for test_name, status in sorted(results.items()):
        status_symbol = "✓" if status == "PASSED" else "✗"
        print(f"{status_symbol} {test_name}: {status}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    # Generate coverage report if requested
    if coverage_mode and all_passed:
        print("\n" + "=" * 50)
        print("GENERATING COVERAGE REPORT")
        print("=" * 50)
        
        try:
            if coverage_mode == 'html':
                # Generate HTML coverage report
                result = subprocess.run([
                    sys.executable, '-m', 'coverage', 'html',
                    '--rcfile=dev_tools_tests/.coveragerc'
                ], env=env, capture_output=True, text=True, cwd=tests_dir.parent)
                
                if result.returncode == 0:
                    html_path = tests_dir / 'htmlcov' / 'index.html'
                    print(f"✓ HTML coverage report generated: {html_path}")
                    print(f"  Open in browser: file://{html_path.absolute()}")
                else:
                    print(f"❌ Failed to generate HTML coverage: {result.stderr}")
            else:
                # Generate terminal coverage report
                result = subprocess.run([
                    sys.executable, '-m', 'coverage', 'report',
                    '--rcfile=dev_tools_tests/.coveragerc'
                ], env=env, cwd=tests_dir.parent)
                
                if result.returncode != 0:
                    print("❌ Failed to generate coverage report")
                    
        except Exception as e:
            print(f"❌ Coverage report error: {e}")
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total_count - passed_count} tests failed")
        return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Run dev_tools tests with optional coverage')
    parser.add_argument('--cov', action='store_true', 
                       help='Generate coverage report')
    parser.add_argument('--html', action='store_true',
                       help='Generate HTML coverage report')
    
    args = parser.parse_args()
    
    # Determine coverage mode
    coverage_mode = None
    if args.html:
        coverage_mode = 'html'
    elif args.cov:
        coverage_mode = 'report'
    
    print("Dev Tools Test Suite")
    if coverage_mode:
        print(f"(with {coverage_mode} coverage)")
    print("=" * 50)
    
    # Check if we're in the right directory
    current_dir = Path.cwd()
    tests_dir = Path(__file__).parent
    
    if current_dir != tests_dir.parent:
        print(f"Warning: Running from {current_dir}")
        print(f"Expected to run from {tests_dir.parent}")
        print()
    
    # Run tests
    exit_code = run_tests(coverage_mode)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()