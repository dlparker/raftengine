"""
Configuration classes for setting up an instance of the class::`Server` class.
"""
from dataclasses import dataclass, field
from typing import Any, Type, Callable, Awaitable
import os
import json
from raftengine.api.log_api import LogAPI
from raftengine.messages.base_message import BaseMessage

@dataclass
class LocalConfig:
    """
    Class used to supply details of the runtime configuration on the local machine to 
    the server code. 
    Args:
        working_dir:
            The location for the runtime to use as a working directory for output files 
            and the like
        uri: 
            Unique identifyer for this server, either directly
            serving as a comms endpoint or translatable to one
        record_message_problems:
            Whenever a message causes and error, the messages is recorded in a problem
            history buffer if this flag is True. The records can be accessed and managed
            by calling get_message_problem_history. Message errors also generate
            an error event, so you can use that as a trigger to collect and clear the records.
    """
    working_dir: os.PathLike # where the server should run and place log files, data files, etc
    uri: Any                 # unique identifier of this server
    record_message_problems: bool = field(default=True)

@dataclass
class ClusterInitConfig:
    """
    Class used to supply details of the initial cluster configuration to the server code.
    The same information will be augmented and the results store in the log as
    raftengine.api.types.ClusterConfig. Once save in the log that version will be used
    and this initial config will no longer have any effect.

    Args:
        node_uris: 
            A list of addresses of the all nodes in the cluster
            in the same form as the uri in the LocalConfig. This server's
            uri is in there too.
        heartbeat_period:
            Leader sends a heartbeat message if it hasn't sent other messages 
            in this amount of time (float seconds)
        election_timeout_min:
            start another election if no leader elected in a random
            amount of time bounded by election_timeout_min and election_timeout_max,
            raft paper suggests range of 150 to 350 milliseconds
            if no leader messages in longer than this time, start an election
        election_timeout_max:
            start another election if no leader elected in a random
            amount of time bounded by election_timeout_min and election_timeout_max,
            raft paper suggests range of 150 to 350 milliseconds
            if no leader messages in longer than this time, start an election
        max_entries_per_message:
            the maximum number of log entries that will be sent in a single
            append entries message
        use_pre_vote:
            Use the prevote extension for elections, defaults to True
        use_check_quorum:
            Use the check quorum extension to make leaders proactively resign, defaults to True
        use_dynamic_config:
            Cluster config can change while running, stored in log with usual raft replication, defaults to True
    """
    node_uris: list # addresses of other nodes in the cluster
    heartbeat_period: float
    election_timeout_min: float
    election_timeout_max: float
    max_entries_per_message: int
    use_pre_vote: bool = True
    use_check_quorum: bool = True
    use_dynamic_config: bool = True

