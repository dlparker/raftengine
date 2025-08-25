import os
import logging
from raftengine.deck.log_control import LogController

def setup_logging():

    if LogController.controller:
        return LogController.controller
    test_loggers = [('ClusterOps', 'Cluster operations'),
                    ('PausingServer', 'Test server implementation'),
                    ('SimulatedNetwork', 'Network simulation'),
                    ('test_code', 'Test code logger')]
    log_control = LogController(additional_loggers=test_loggers)
    if "RAFT_DEBUG_LOGGING" in os.environ:
        log_control.set_default_level('debug')
    elif "RAFT_INFO_LOGGING" in os.environ:
        log_control.set_default_level('info')
    elif "RAFT_WARN_LOGGING" in os.environ:
        log_control.set_default_level('warning')
    else:
        log_control.set_default_level('error')
        
    return log_control
