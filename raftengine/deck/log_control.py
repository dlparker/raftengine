from dataclasses import dataclass, field
import logging
from logging.config import dictConfig
from typing import Dict, List, Optional, Union, Any

@dataclass
class HandlerDef:
    """Definition of a logging handler configuration."""
    name: str
    description: str
    handler_type: str  # 'stream', 'file', 'custom'
    level: str = "DEBUG"
    formatter: str = "standard"
    # Handler-specific configuration
    stream: Optional[str] = None  # e.g., "ext://sys.stdout"
    filename: Optional[str] = None  # for file handlers
    mode: str = "a"  # file mode
    encoding: str = "utf-8"
    handler_class: Optional[str] = None  # for custom handlers
    extra_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoggerDef:
    """Definition of a logger configuration."""
    name: str
    description: str
    custom_level: Optional[str] = None
    propagate: bool = False
    handler_names: list[str] = field(default_factory=list, repr=False)

class LogController:
    controller = None

    @classmethod
    def get_controller(cls):
        if cls.controller is None:
            raise Exception('you must call make controller first, or initialize it directly')
        return cls.controller

    @classmethod
    def make_controller(cls, *args, **kwargs):
        if cls.controller is not None:
            raise Exception('you must call make_controller one time only, then call get_controller afterwards')
        cls.controller = cls(*args, **kwargs)
        return cls.controller

    def __init__(self, additional_loggers: Optional[List[tuple]] = None, default_level: str = "ERROR",
                 temporary=False):
        """
        Initialize the LogController with the known logger names from the system.
        Builds a dictionary of logger names as a class property during init.
        
        Args:
            additional_loggers: Optional list of tuples (name, description) to add to known loggers
        """
        if not temporary:
            if LogController.controller is not None:
                raise Exception('initializing LogController class twice causes issues')
            else:
                LogController.controller = self
        # Default level for all loggers
        self.default_level = default_level.upper()
        
        # Default handlers for new loggers
        self.default_handlers: List[str] = ["stdout"]
        
        # Known handlers from the original logging_ops.py setup_logging function
        self.known_handlers = {
            "stdout": HandlerDef(
                name="stdout",
                description="Standard output handler",
                handler_type="stream",
                level="DEBUG",
                formatter="standard",
                stream="ext://sys.stdout",
                handler_class="logging.StreamHandler"
            ),
        }
        
        # Known logger names from the original logging_ops.py set_levels function
        self.known_loggers = {
            '': LoggerDef('', 'root logger', handler_names=self.default_handlers.copy()),
            'Leader': LoggerDef('Leader', 'Leader role', handler_names=self.default_handlers.copy()),
            'Follower': LoggerDef('Follower', 'Follower role', handler_names=self.default_handlers.copy()),
            'Candidate': LoggerDef('Candidate', 'Candidate role',
                                   handler_names=self.default_handlers.copy()),
            'BaseRole': LoggerDef('BaseRole', 'Base role functionality',
                                  handler_names=self.default_handlers.copy()),
            'Deck': LoggerDef('Deck', 'Main Raft engine controller', handler_names=self.default_handlers.copy()),
            'Elections': LoggerDef('Elections', 'Events in election logic',
                                   handler_names=self.default_handlers.copy()),
            'SqliteLog': LoggerDef('SqliteLog', '',
                                   handler_names=self.default_handlers.copy()),
            'LMDBLog': LoggerDef('LMDBLog', '',
                                   handler_names=self.default_handlers.copy()),
            'HybridLog': LoggerDef('HybridLog', '',
                                   handler_names=self.default_handlers.copy()),
            'HybridLog.sqlite_writer': LoggerDef('HybridLog.sqlite_writer', '',
                                                 handler_names=self.default_handlers.copy()),
         }
        
        if additional_loggers:
            for logger_name, description in additional_loggers:
                self.known_loggers[logger_name] = LoggerDef(
                    logger_name, description, handler_names=self.default_handlers.copy()
                )
        
        # Storage for saved levels during temporary changes
        self._saved_levels: Dict[str, int] = {}
        self._saved_custom_levels: Dict[str, Optional[str]] = {}
        self._saved_handler_names: Dict[str, List[str]] = {}
        self.apply_config()
        
    def set_logger_level(self, logger_name: str, level: Union[str, int]) -> None:
        """
        Set the logging level for a specific logger.
        
        Args:
            logger_name: Name of the logger to modify
            level: Logging level (string like 'DEBUG', 'INFO', 'WARNING', 'ERROR' or int)
        """
        if logger_name not in self.known_loggers:
            raise ValueError(f"Unknown logger: {logger_name}. Known loggers: {list(self.known_loggers.keys())}")
            
        logger = logging.getLogger(logger_name)
        
        # Convert string levels to logging constants
        level_str = level
        if isinstance(level, str):
            level_upper = level.upper()
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO, 
                'WARNING': logging.WARNING,
                'WARN': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            if level_upper not in level_map:
                raise ValueError(f"Invalid level: {level}. Valid levels: {list(level_map.keys())}")
            level = level_map[level_upper]
            level_str = level_upper
        else:
            # Convert int level back to string for storage
            level_map = {
                logging.DEBUG: 'DEBUG',
                logging.INFO: 'INFO',
                logging.WARNING: 'WARNING',
                logging.ERROR: 'ERROR',
                logging.CRITICAL: 'CRITICAL'
            }
            level_str = level_map.get(level, str(level))
            
        logger.setLevel(level)
        
        # Set the custom_level property in the LoggerDef
        self.known_loggers[logger_name].custom_level = level_str
        
    def _set_logger_level_without_custom_flag(self, logger_name: str, level: Union[str, int]) -> None:
        """
        Set the logging level for a logger without marking it as having a custom level.
        Used internally by set_default_level.
        """
        if logger_name not in self.known_loggers:
            raise ValueError(f"Unknown logger: {logger_name}. Known loggers: {list(self.known_loggers.keys())}")
            
        logger = logging.getLogger(logger_name)
        
        # Convert string levels to logging constants
        if isinstance(level, str):
            level_upper = level.upper()
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO, 
                'WARNING': logging.WARNING,
                'WARN': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            if level_upper not in level_map:
                raise ValueError(f"Invalid level: {level}. Valid levels: {list(level_map.keys())}")
            level = level_map[level_upper]
            
        logger.setLevel(level)
        # Don't set custom_level - this is for default level changes
        
    def set_default_level(self, level: Union[str, int]) -> None:
        """
        Set the default logging level for all known loggers that don't have a custom level.
        
        Args:
            level: Logging level to apply to loggers without custom levels
        """
        # Convert level to string format for storage
        if isinstance(level, int):
            level_map = {
                logging.DEBUG: 'DEBUG',
                logging.INFO: 'INFO',
                logging.WARNING: 'WARNING',
                logging.ERROR: 'ERROR',
                logging.CRITICAL: 'CRITICAL'
            }
            level_str = level_map.get(level, str(level))
        else:
            level_str = level.upper()
        
        # Update the default_level property
        self.default_level = level_str
        
        # Apply to all loggers that don't have custom levels
        for logger_name, logger_def in self.known_loggers.items():
            # Only set level if logger doesn't have a custom level
            if logger_def.custom_level is None:
                self._set_logger_level_without_custom_flag(logger_name, level)
            
    def get_logger_level(self, logger_name: str) -> int:
        """
        Get the current logging level for a specific logger.
        
        Args:
            logger_name: Name of the logger
            
        Returns:
            Current logging level as integer
        """
        if logger_name not in self.known_loggers:
            raise ValueError(f"Unknown logger: {logger_name}")
            
        logger = logging.getLogger(logger_name)
        return logger.level
        
    def save_current_levels(self) -> None:
        """
        Save the current logging levels and handler assignments for all known loggers.
        This enables temporary changes that can be reverted later.
        """
        self._saved_levels = {}
        self._saved_custom_levels = {}
        self._saved_handler_names = {}
        for logger_name, logger_def in self.known_loggers.items():
            logger = logging.getLogger(logger_name)
            self._saved_levels[logger_name] = logger.level
            self._saved_custom_levels[logger_name] = logger_def.custom_level
            self._saved_handler_names[logger_name] = logger_def.handler_names.copy()
            
    def restore_saved_levels(self) -> None:
        """
        Restore logging levels and handler assignments to the previously saved state.
        Must be called after save_current_levels().
        """
        if not self._saved_levels:
            raise RuntimeError("No saved levels to restore. Call save_current_levels() first.")
            
        for logger_name, saved_level in self._saved_levels.items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(saved_level)
            # Restore the custom_level property
            self.known_loggers[logger_name].custom_level = self._saved_custom_levels[logger_name]
            # Restore the handler assignments
            self.known_loggers[logger_name].handler_names = self._saved_handler_names[logger_name]
            
        self._saved_levels = {}
        self._saved_custom_levels = {}
        self._saved_handler_names = {}
        
    def add_logger(self, logger_name: str, description: str = "", level: Optional[Union[str, int]] = None) -> None:
        """
        Add a new logger to the known loggers dictionary.
        
        Args:
            logger_name: Name of the logger to add
            description: Optional description of the logger's purpose
            level: Optional logging level to set for this logger
        """
        handler_names = self.default_handlers.copy()

        dotted = []
        for sub in logger_name.split('.'):
            dotted.append(sub)
            l_name = '.'.join(dotted)
            desc = ""
            if l_name == logger_name:
                desc = description
                self.known_loggers[l_name] = LoggerDef(l_name, desc, handler_names=handler_names)
            else:
                self.known_loggers[l_name] = LoggerDef(l_name, desc, handler_names=self.default_handlers.copy())
            logging.getLogger(l_name)
        
            if l_name != logger_name:
                # only set the actual leaf to the requested level
                self.set_logger_level(l_name, self.default_level)
            else:
                if level is None:
                    level = self.default_level
                self.set_logger_level(l_name, level)
        return logging.getLogger(logger_name)
        
    def get_known_loggers(self) -> Dict[str, LoggerDef]:
        """
        Get a copy of the known loggers dictionary.
        
        Returns:
            Dictionary mapping logger names to LoggerDef instances
        """
        return self.known_loggers.copy()

    def apply_config(self) -> None:
        config = self.to_dict_config()
        dictConfig(config)
        
    def to_dict_config(self) -> Dict[str, Any]:
        """
        Generate a dictConfig compatible dictionary from the current LogController state.
        
        Returns:
            Dictionary compatible with logging.config.dictConfig
        """
        # Define formatters
        formatters = {
            "standard": {
                "format": "[%(asctime)s.%(msecs)03d %(levelname)-7s] %(name)-15s: %(message)s",
                'datefmt': "%M:%S"
            }
        }
        
        # Build handlers dictionary
        handlers = {}
        for handler_name, handler_def in self.known_handlers.items():
            handler_config = {
                "level": handler_def.level,
                "formatter": handler_def.formatter,
                "class": handler_def.handler_class
            }
            
            # Add handler-specific configuration
            if handler_def.handler_type == "stream" and handler_def.stream:
                handler_config["stream"] = handler_def.stream
            
            # Add any extra configuration
            handler_config.update(handler_def.extra_config)
            
            handlers[handler_name] = handler_config
        
        # Build loggers dictionary
        loggers = {}
        for logger_name, logger_def in self.known_loggers.items():
            # Determine the effective level for this logger
            if logger_def.custom_level is not None:
                level = logger_def.custom_level
            else:
                level = self.default_level
            
            logger_config = {
                "handlers": logger_def.handler_names,
                "level": level,
                "propagate": logger_def.propagate
            }
            
            loggers[logger_name] = logger_config
        
        # Return complete dictConfig structure
        return {
            "version": 1,
            "disable_existing_loggers": True,
            "formatters": formatters,
            "handlers": handlers,
            "loggers": loggers
        }
    
    # Handler Management Methods
    

class TemporaryLogControl:
    """
    Context manager for temporarily changing logging levels.
    
    This enables the pattern seen in test_long_catchup where certain loggers
    are silenced during noisy operations and then restored afterward.
    """
    
    def __init__(self, log_controller: LogController, keep_active: Optional[List[str]] = None, 
                 silence_level: Optional[Union[str, int]] = None):
        """
        Initialize the temporary log control context manager.
        
        Args:
            log_controller: LogController instance to work with
            keep_active: List of logger names to keep at current level (not silence)
            silence_level: Level to set for silenced loggers (default: uses controller's default_level)
        """
        self.log_controller = log_controller
        self.keep_active = keep_active or []
        self.silence_level = silence_level if silence_level is not None else log_controller.default_level
        
    def __enter__(self):
        """
        Enter the context: save current levels/handlers and apply temporary changes.
        """
        # Save current state (levels and handlers)
        self.log_controller.save_current_levels()
        
        # Silence all loggers except those in keep_active list
        for logger_name in self.log_controller.known_loggers:
            if logger_name not in self.keep_active:
                self.log_controller.set_logger_level(logger_name, self.silence_level)
                
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context: restore original logging levels.
        """
        self.log_controller.restore_saved_levels()
        
        
def create_temporary_log_control(keep_active: Optional[List[str]] = None, 
                                silence_level: Optional[Union[str, int]] = None) -> TemporaryLogControl:
    """
    Convenience function to create a TemporaryLogControl context manager with a new LogController.
    
    Args:
        keep_active: List of logger names to keep active (not silence)
        silence_level: Level to set for silenced loggers (default: uses controller's default_level)
        
    Returns:
        TemporaryLogControl context manager
    """
    log_controller = LogController(temporary=True)
    return TemporaryLogControl(log_controller, keep_active, silence_level)


