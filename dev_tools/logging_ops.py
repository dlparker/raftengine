from logging.config import dictConfig
from pathlib import Path


def setup_logging(additions=None, default_level="error"): # pragma: no cover
    #lfstring = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    lfstring = '[%(levelname)s] %(name)s: %(message)s'
    log_formaters = dict(standard=dict(format=lfstring))
    logfile_path = Path('.', "test.log")
    if False:
        file_handler = dict(level="DEBUG",
                            formatter="standard",
                            encoding='utf-8',
                            mode='w',
                            filename=str(logfile_path))
        file_handler['class'] = "logging.FileHandler"
    stdout_handler =  dict(level="DEBUG",
                           formatter="standard",
                           stream="ext://sys.stdout")
    # can't us "class" in above form
    stdout_handler['class'] = "logging.StreamHandler"
    log_handlers = dict(stdout=stdout_handler)
    handler_names = ['stdout']
    if False:
        log_handlers = dict(file=file_handler, stdout=stdout_handler)
        handler_names = ['file', 'stdout']
    log_loggers = set_levels(handler_names, additions=additions, default_level=default_level)
    global log_config
    log_config = dict(version=1, disable_existing_loggers=False,
                      formatters=log_formaters,
                      handlers=log_handlers,
                      loggers=log_loggers)
        # apply the caller's modifications to the level specs
    try:
        dictConfig(log_config)
    except:
        from pprint import pprint
        pprint(log_config)
        raise
    return log_config


def set_levels(handler_names, additions=None, default_level='error'): # pragma: no cover
    log_loggers = dict()
    err_log = dict(handlers=handler_names, level="ERROR", propagate=False)
    warn_log = dict(handlers=handler_names, level="WARNING", propagate=False)
    root_log = dict(handlers=handler_names, level="ERROR", propagate=False)
    info_log = dict(handlers=handler_names, level="INFO", propagate=False)
    debug_log = dict(handlers=handler_names, level="DEBUG", propagate=False)
    log_loggers[''] = root_log
    default_log = err_log
    if default_level == "warn":
        default_log =  warn_log
    elif default_level == "info":
        default_log =  info_log
    elif default_level == "debug":
        default_log =  debug_log
    log_loggers['Leader'] = default_log
    log_loggers['Follower'] = default_log
    log_loggers['Candidate'] = default_log
    log_loggers['BaseRole'] = default_log
    log_loggers['Hull'] = default_log
    log_loggers['Substates'] = default_log
    log_loggers['ClusterOps'] = default_log
    log_loggers['PausingServer'] = default_log
    log_loggers['SimulatedNetwork'] = default_log
    log_loggers['test_code'] = default_log
    if additions:
        for add in additions:
            if add['level'] == "debug":
                log_loggers[add['name']] = debug_log
            elif add['level'] == "info":
                log_loggers[add['name']] = info_log
            elif add['level'] == "warn":
                log_loggers[add['name']] = warn_log
            elif add['level'] == "error":
                log_loggers[add['name']] = error_log
            else:
                raise Exception('Invalid level')
    return log_loggers


log_config = None
