"""
Validation utilities for the Raft operations system.

This module provides utilities to validate operations and detect common integration issues.
"""
import asyncio
import logging
from typing import List, Set, Any
from base.datatypes import CommandType
from base.operations import Ops

logger = logging.getLogger(__name__)

def validate_operations_methods(operations: Ops) -> List[str]:
    """
    Validate that all CommandType enum values have corresponding Operations methods.
    
    Returns a list of validation errors, empty if all validations pass.
    """
    errors = []
    
    # Get all CommandType enum values
    expected_methods = {cmd_type.value for cmd_type in CommandType}
    
    # Get all public methods from Operations class
    actual_methods = {
        name for name in dir(operations) 
        if not name.startswith('_') and callable(getattr(operations, name))
    }
    
    # Check for missing methods
    missing_methods = expected_methods - actual_methods
    if missing_methods:
        errors.append(f"Operations class missing methods for CommandTypes: {sorted(missing_methods)}")
    
    # Check for extra methods that don't correspond to CommandTypes
    extra_methods = actual_methods - expected_methods
    # Filter out common non-command methods
    common_non_command_methods = {'close', 'commit', 'rollback', 'begin_transaction'}
    unexpected_extra = extra_methods - common_non_command_methods
    if unexpected_extra:
        logger.info(f"Operations class has extra methods not in CommandType: {sorted(unexpected_extra)}")
    
    # Validate that each CommandType method is async
    for cmd_type in CommandType:
        method_name = cmd_type.value
        if hasattr(operations, method_name):
            method = getattr(operations, method_name)
            if not asyncio.iscoroutinefunction(method):
                errors.append(f"Operations method '{method_name}' is not async")
    
    return errors

def validate_command_serialization(command_data: str) -> List[str]:
    """
    Validate that a serialized command has the correct structure.
    
    Returns a list of validation errors, empty if all validations pass.
    """
    errors = []
    
    try:
        from base.json_helpers import bank_json_loads
        parsed = bank_json_loads(command_data)
    except Exception as e:
        return [f"Command serialization is invalid JSON: {e}"]
    
    # Check required fields
    if not isinstance(parsed, dict):
        errors.append("Command must be a JSON object")
        return errors
    
    if 'command_name' not in parsed:
        errors.append("Command missing 'command_name' field")
    elif not isinstance(parsed['command_name'], str):
        errors.append(f"command_name must be string, got {type(parsed['command_name'])}")
    
    if 'args' not in parsed:
        errors.append("Command missing 'args' field")
    elif not isinstance(parsed['args'], dict):
        errors.append(f"args must be dict, got {type(parsed['args'])}")
    
    # Validate command_name is a valid CommandType value
    if 'command_name' in parsed and isinstance(parsed['command_name'], str):
        valid_commands = {cmd_type.value for cmd_type in CommandType}
        if parsed['command_name'] not in valid_commands:
            errors.append(f"Unknown command_name '{parsed['command_name']}'. Valid commands: {sorted(valid_commands)}")
    
    return errors

def diagnose_system_health(operations: Ops, recent_commands: List[str] = None) -> dict:
    """
    Run comprehensive diagnostics on the operations system.
    
    Returns a dict with diagnostic results and recommendations.
    """
    results = {
        'operations_validation': [],
        'command_validation_errors': [],
        'health_status': 'unknown',
        'recommendations': []
    }
    
    # Validate operations methods
    results['operations_validation'] = validate_operations_methods(operations)
    
    # Validate recent commands if provided
    if recent_commands:
        for i, cmd in enumerate(recent_commands[-10:]):  # Check last 10 commands
            cmd_errors = validate_command_serialization(cmd)
            if cmd_errors:
                results['command_validation_errors'].append({
                    'command_index': i,
                    'command_preview': cmd[:100] + '...' if len(cmd) > 100 else cmd,
                    'errors': cmd_errors
                })
    
    # Determine overall health
    total_errors = len(results['operations_validation']) + len(results['command_validation_errors'])
    if total_errors == 0:
        results['health_status'] = 'healthy'
    elif total_errors < 3:
        results['health_status'] = 'warning'
    else:
        results['health_status'] = 'critical'
    
    # Generate recommendations
    if results['operations_validation']:
        results['recommendations'].append(
            "Fix Operations class method mismatches with CommandType enum"
        )
    
    if results['command_validation_errors']:
        results['recommendations'].append(
            "Review command serialization in Collector.build_command()"
        )
    
    if not results['recommendations']:
        results['recommendations'].append("System validation passed - no issues detected")
    
    return results

# Convenience function for quick validation
def quick_validate_operations(operations: Ops) -> bool:
    """Quick validation check. Returns True if operations are valid."""
    errors = validate_operations_methods(operations)
    if errors:
        logger.error(f"Operations validation failed: {errors}")
        return False
    return True