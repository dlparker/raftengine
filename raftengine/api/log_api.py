"""
Definitions for the API of the operations log managed by the state variants.

"""
import os
import abc
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional, Any
import time
from enum import Enum
from raftengine.api.types import ClusterConfig
from raftengine.api.snapshot_api import SnapShot

class RecordCode(str, Enum):
    """ String enum representing purpose of record. """

    """ Record leader saves to start a term, effectively committing all 
         previous recurds because of the usual commit logic """
    term_start = "TERM_START"
    
    """ Results of client command operation """
    client_command = "CLIENT_COMMAND"
    
    """ Cluster Configuration Data """
    cluster_config = "CLUSTER_CONFIG" 

    def __str__(self):
        return self.value
    
@dataclass
class LogRec:
    index: int = field(default = 0)
    term: int = field(default = 0)
    command: str = field(default = None, repr=False)
    code: RecordCode = field(default=RecordCode.client_command)
    serial: int = field(default = None, repr=False)
    leader_id: str = field(default = None, repr=False)
    committed: bool = field(default = False)
    applied: bool =  field(default = False)

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        if not isinstance(data['code'], RecordCode):
            copy_of['code'] = RecordCode(data['code'])
        rec = cls(**copy_of)
        return rec

class CommandLogRec(LogRec):
    pass

class ConfigLogRec(LogRec):
    code=RecordCode.cluster_config


@dataclass
class LogStats:
    """
    Statistics about the log storage for snapshot and pruning decisions.
    
    Attributes:
        record_count (int): Total number of log entries currently stored
        records_since_snapshot (int): Number of records since last snapshot (0 if no snapshot)
        records_per_minute (float): Average records written per minute (recent rate)
        percent_remaining (Optional[float]): Percentage of storage capacity remaining (0-100), 
                                           None if unlimited storage
        total_size_bytes (int): Total storage size in bytes (data + metadata)
        snapshot_index (Optional[int]): Index of last snapshot, None if no snapshot
        last_record_timestamp (Optional[float]): Unix timestamp of most recent record
    """
    first_index: int
    last_index: int
    last_term: int
    record_count: int
    records_since_snapshot: int
    records_per_minute: float
    percent_remaining: Optional[float]
    total_size_bytes: int
    snapshot_index: Optional[int] = None
    last_record_timestamp: Optional[float] = None
    extra_stats: Optional[Any] = None


# abstract class for all roles
class LogAPI(abc.ABC):
    """
    Abstract base class defining the interface for Raft consensus algorithm log storage.
    
    This interface provides persistent storage for log entries, Raft state metadata,
    cluster configuration, and snapshot management. Implementations must handle
    critical boundary conditions correctly to ensure Raft protocol compliance.
    
    ## Log State Management
    
    The log maintains several critical pieces of state:
    - **Log entries**: Ordered sequence of commands with term, index, and status
    - **Current term**: Monotonically increasing election term 
    - **Voted for**: Node ID voted for in current term (None if not voted)
    - **Commit index**: Highest log index known to be committed
    - **Applied index**: Highest log index applied to state machine
    - **Cluster configuration**: Set of nodes and consensus settings
    - **Snapshot**: Compact representation of applied state up to specific index
    
    ## Index Semantics and Boundary Conditions
    
    ### Empty Log State
    When the log contains no entries (newly initialized or after snapshot deletion):
    - `get_first_index()` returns None or 0 (implementation-specific)
    - `get_last_index()` returns 0 
    - `get_last_term()` returns 0 (or snapshot term if snapshot exists)
    - `get_commit_index()` returns 0 (or snapshot index if snapshot exists) 
    - `get_applied_index()` returns 0 (or snapshot index if snapshot exists)
    - `read()` with no arguments returns None
    - `read(index)` with any index returns None
    
    ### First Entry Append
    When appending the first entry to an empty log:
    - Entry gets index 1 (log indices start at 1, not 0)
    - `get_first_index()` returns 1
    - `get_last_index()` returns 1
    - The entry inherits the current term
    
    ### Snapshot Installation Effects
    When `install_snapshot(snapshot)` is called:
    - All log entries with index ≤ snapshot.index are deleted
    - If entries remain: `get_first_index()` returns snapshot.index + 1
    - If no entries remain: `get_first_index()` returns None
    - `get_last_index()` returns max(snapshot.index, highest_remaining_entry_index)
    - `get_commit_index()` considers snapshot.index as baseline for committed state
    - `get_applied_index()` considers snapshot.index as baseline for applied state
    
    ## Method Behavior Specifications
    
    ### Index Queries
    - `get_first_index()`: Returns index of earliest entry, or None if log empty
    - `get_last_index()`: Returns index of latest entry, or 0 if log empty, or snapshot.index if only snapshot
    - `get_last_term()`: Returns term of last entry, or 0 if empty, or snapshot.term if only snapshot
    
    ### State Queries  
    - `get_commit_index()`: Searches entries for highest committed, falls back to snapshot.index, then 0
    - `get_applied_index()`: Searches entries for highest applied, falls back to snapshot.index, then 0
    - `get_term()`: Returns current election term (persisted across restarts)
    - `get_voted_for()`: Returns node ID voted for in current term, or None
    
    ### Entry Operations
    - `insert(entry)`: If entry has an index, inserts record at that index, replacing if needed. Otherwise,
                       Assigns next sequential index, stores entry, updates last_index
    - `read(index)`: Returns entry at index, or None if index invalid/not found
    - `read()`: Returns entry at last_index, or None if log empty
    - `delete_all_from(index)`: Removes all entries with index ≥ specified index
    
    ### State Updates
    - `mark_committed(entry)`: Marks entry as committed, updates commit_index tracking
    - `mark_applied(entry)`: Marks entry as applied, updates applied_index tracking
    - `set_term(term)`: Sets current term, clears voted_for (new election)
    - `incr_term()`: Increments and returns new term, clears voted_for
    
    ## Implementation Requirements
    
    Implementations MUST:
    1. Persist all state across process restarts
    2. Handle empty log boundary conditions correctly
    3. Maintain index invariants after snapshot installation
    4. Search actual entries for commit/applied index calculation 
    5. Return consistent values for index queries in all states
    6. Ensure atomicity of state updates
    7. Handle concurrent access safely (if applicable)
    
    ## Error Conditions
    
    Implementations SHOULD raise exceptions for:
    - Invalid index values (< 1 for most operations)
    - Attempts to read/modify non-existent entries
    - Storage I/O failures
    - Data corruption detection
    
    The `broken` flag indicates when the log storage has encountered an
    unrecoverable error and should not be used for further operations.
    """
    
    @abc.abstractmethod
    async def start(self): # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def stop(self): # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_broken(self) -> None:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_fixed(self) -> None:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_broken(self) -> bool:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_uri(self) -> Union[str, None]:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_uri(self, uri: str):  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_term(self, value: int):  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def incr_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_voted_for(self) -> str:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_voted_for(self, value: str):  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_last_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_first_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_last_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_commit_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_applied_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def append(self, record: LogRec) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def insert(self, record: LogRec) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    def mark_committed(self, index) -> None: # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    def mark_applied(self, index) -> None:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_all_from(self, index: int) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def save_cluster_config(self, config: ClusterConfig) -> None:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_cluster_config(self) -> Optional[ClusterConfig]:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def install_snapshot(self, snapshot:SnapShot) -> None: # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_snapshot(self) -> Optional[SnapShot]: # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_stats(self) -> LogStats: # pragma: no cover abstract
        """
        Get statistics about the log storage for snapshot and pruning decisions.
        
        Returns LogStats containing:
        - record_count: Total number of log entries
        - records_since_snapshot: Records added since last snapshot  
        - records_per_minute: Recent write rate
        - percent_remaining: Storage capacity remaining (None if unlimited)
        - total_size_bytes: Total storage size
        - snapshot_index: Index of last snapshot (None if no snapshot)
        - last_record_timestamp: Timestamp of most recent record
        """
        raise NotImplementedError

        



        
    
