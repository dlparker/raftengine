
setup_configs = {
    'step1': {
        'direct': 'step1.direct.setup_helper',
    },
    'step2': {
        'aiozmq': 'step2.aiozmq.setup_helper',
        'grpc': 'step2.grpc.setup_helper', 
        'fastapi': 'step2.fastapi.setup_helper',
    },
    'step3': {
        'direct': 'step3.direct.setup_helper',
        'astream': 'step3.astream.setup_helper',
    },
}

def get_available_steps():
    """Get list of available steps"""
    return list(setup_configs.keys())

def get_available_transports(step):
    """Get list of available transports for a given step"""
    return list(setup_configs.get(step, {}).keys())

def get_all_step_transport_combinations():
    """Get all valid step/transport combinations as (step, transport) tuples"""
    combinations = []
    for step, transports in setup_configs.items():
        for transport in transports:
            combinations.append((step, transport))
    return combinations

def get_module_path(step, transport):
    """Get the module path for a given step and transport combination"""
    return setup_configs.get(step, {}).get(transport)

def validate_step_transport(step, transport):
    """Validate that a step/transport combination is valid"""
    if step not in setup_configs:
        return False, f"Invalid step '{step}'. Available steps: {', '.join(get_available_steps())}"
    
    if transport not in setup_configs[step]:
        available = get_available_transports(step)
        return False, f"Invalid transport '{transport}' for step '{step}'. Available transports: {', '.join(available)}"
    
    return True, "Valid combination"

