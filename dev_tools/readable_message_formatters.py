"""
Readable message formatters for PlantUML sequence diagrams.

These formatters produce human-readable message descriptions instead of the
heavily abbreviated format used for table output. Designed specifically for
PlantUML diagrams where space is not as constrained.
"""

from dev_tools.trace_shorthand import MessageFormat, decode_message


class ReadableMessageFormat(MessageFormat):
    """Base class for readable message formatting"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        self.node_state = node_state


class RequestVoteReadableFormat(ReadableMessageFormat):
    """Readable format for request_vote messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "request_vote":
            raise Exception(f'not a request_vote message {str(self.message)}')

    def format(self):
        return f"RequestVote(term={self.message.term}, lastIndex={self.message.prevLogIndex}, lastTerm={self.message.prevLogTerm})"


class RequestVoteResponseReadableFormat(ReadableMessageFormat):
    """Readable format for request_vote_response messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "request_vote_response":
            raise Exception(f'not a request_vote_response message {str(self.message)}')

    def format(self):
        return f"VoteResponse(granted={self.message.vote})"


class AppendEntriesReadableFormat(ReadableMessageFormat):
    """Readable format for append_entries messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)  
        if self.message.code != "append_entries":
            raise Exception(f'not an append_entries message {str(self.message)}')

    def format(self):
        entry_count = len(self.message.entries)
        if entry_count == 0:
            entry_desc = "heartbeat"
        elif entry_count == 1:
            entry_desc = "1 entry"
        else:
            entry_desc = f"{entry_count} entries"
            
        return f"AppendEntries(term={self.message.term}, prevIndex={self.message.prevLogIndex}, prevTerm={self.message.prevLogTerm}, {entry_desc}, commitIndex={self.message.commitIndex})"


class AppendResponseReadableFormat(ReadableMessageFormat):
    """Readable format for append_response messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "append_response":
            raise Exception(f'not an append_response message {str(self.message)}')

    def format(self):
        return f"AppendResponse(success={self.message.success}, maxIndex={self.message.maxIndex})"


class PreVoteReadableFormat(ReadableMessageFormat):
    """Readable format for pre_vote messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "pre_vote":
            raise Exception(f'not a pre_vote message {str(self.message)}')

    def format(self):
        return f"PreVoteRequest(term={self.message.term}, lastIndex={self.message.prevLogIndex}, lastTerm={self.message.prevLogTerm})"


class PreVoteResponseReadableFormat(ReadableMessageFormat):
    """Readable format for pre_vote_response messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "pre_vote_response":
            raise Exception(f'not a pre_vote_response message {str(self.message)}')

    def format(self):
        return f"PreVoteResponse(granted={self.message.vote})"


class MembershipChangeReadableFormat(ReadableMessageFormat):
    """Readable format for membership_change messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "membership_change":
            raise Exception(f'not a membership_change message {str(self.message)}')

    def format(self):
        return f"MembershipChange(operation={self.message.op}, node={self.message.target_uri})"


class MembershipChangeResponseReadableFormat(ReadableMessageFormat):
    """Readable format for membership_change_response messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "membership_change_response":
            raise Exception(f'not a membership_change_response message {str(self.message)}')

    def format(self):
        return f"MembershipChangeResponse(operation={self.message.op}, node={self.message.target_uri}, success={self.message.ok})"


class TransferPowerReadableFormat(ReadableMessageFormat):
    """Readable format for transfer_power messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "transfer_power":
            raise Exception(f'not a transfer_power message {str(self.message)}')

    def format(self):
        return f"TransferPower(prevIndex={self.message.prevLogIndex})"


class TransferPowerResponseReadableFormat(ReadableMessageFormat):
    """Readable format for transfer_power_response messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "transfer_power_response":
            raise Exception(f'not a transfer_power_response message {str(self.message)}')

    def format(self):
        return f"TransferPowerResponse(prevIndex={self.message.prevLogIndex}, success={self.message.success})"


class SnapshotReadableFormat(ReadableMessageFormat):
    """Readable format for snapshot messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "snapshot":
            raise Exception(f'not a snapshot message {str(self.message)}')

    def format(self):
        return f"Snapshot(prevIndex={self.message.prevLogIndex})"


class SnapshotResponseReadableFormat(ReadableMessageFormat):
    """Readable format for snapshot_response messages"""
    
    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage, node_state)
        if self.message.code != "snapshot_response":
            raise Exception(f'not a snapshot_response message {str(self.message)}')

    def format(self):
        return f"SnapshotResponse(prevIndex={self.message.prevLogIndex}, success={self.message.success})"


# Mapping of message codes to readable formatter classes
READABLE_MESSAGE_FORMATTERS = {
    'request_vote': RequestVoteReadableFormat,
    'request_vote_response': RequestVoteResponseReadableFormat,
    'append_entries': AppendEntriesReadableFormat,
    'append_response': AppendResponseReadableFormat,
    'pre_vote': PreVoteReadableFormat,
    'pre_vote_response': PreVoteResponseReadableFormat,
    'membership_change': MembershipChangeReadableFormat,
    'membership_change_response': MembershipChangeResponseReadableFormat,
    'transfer_power': TransferPowerReadableFormat,
    'transfer_power_response': TransferPowerResponseReadableFormat,
    'snapshot': SnapshotReadableFormat,
    'snapshot_response': SnapshotResponseReadableFormat,
}