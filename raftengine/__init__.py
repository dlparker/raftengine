"""
RaftEngine - A Python implementation of the Raft consensus algorithm for distributed systems.

This library provides a modular implementation of the Raft consensus algorithm that can be
integrated into distributed systems. Users supply their own message transport and log storage
implementations through the PilotAPI interface.

Key Components:
- DeckAPI/Deck: Main entry point and control center for the Raft engine
- PilotAPI: User-supplied interface for message transport and log storage  
- LogAPI: Interface for persistent log storage
- Configuration classes for cluster and local setup
- Event handling system for monitoring and debugging

Example usage:
    from raftengine import Deck, LocalConfig, ClusterInitConfig
    
    # Create configuration
    local_config = LocalConfig(working_dir="/tmp/raft", uri="node1")
    cluster_config = ClusterInitConfig(uris=["node1", "node2", "node3"])
    
    # Create pilot implementation (user-supplied)
    pilot = MyPilotImplementation()
    
    # Create and start Raft engine
    deck = Deck(cluster_config, local_config, pilot)
    await deck.start()
"""

__version__ = "0.1.0"
__author__ = "RaftEngine Contributors"
__license__ = "MIT"

# Main API classes
from .api.deck_api import DeckAPI
from .deck.deck import Deck
from .api.pilot_api import PilotAPI
from .api.log_api import LogAPI, LogRec, RecordCode
from .api.snapshot_api import SnapShot, SnapShotToolAPI
from .api.events import EventHandler, EventType
from .api.deck_config import LocalConfig, ClusterInitConfig
from .api.types import RoleName, OpDetail, ClusterSettings, ClusterConfig

# Make the main classes available at package level
__all__ = [
    # Main interfaces
    "DeckAPI",
    "Deck", 
    "PilotAPI",
    "LogAPI",
    
    # Configuration
    "LocalConfig",
    "ClusterInitConfig",
    "ClusterSettings",
    "ClusterConfig",
    
    # Log and storage
    "LogRec",
    "RecordCode",
    "SnapShot",
    "SnapShotToolAPI",
    
    # Events
    "EventHandler",
    "EventType",
    
    # Types and enums
    "RoleName",
    "OpDetail",
    
    # Package metadata
    "__version__",
    "__author__",
    "__license__",
]

