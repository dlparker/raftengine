import os
import logging
from raftengine.deck.log_control import LogController

def setup_logging():

    if LogController.controller:
        log_control = LogController.controller
    else:
        test_loggers = [('rpc.client',''),
                        ('rpc.server',''),
                        ('raft.RaftServer',''),
                        ('raft.RaftClient',''),
                        ('test_code', 'Test code logger')]
        log_control = LogController(additional_loggers=test_loggers)
        
    if "TEST_DEBUG_LOGGING" in os.environ:
        log_control.set_default_level('debug')
    if "TEST_INFO_LOGGING" in os.environ:
        log_control.set_default_level('info')
    log_control.set_logger_level('rpc.client', 'warning')
    return log_control
