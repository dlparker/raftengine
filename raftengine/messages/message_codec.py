"""
Message encoding/decoding for Raft protocol messages.

This module provides centralized message serialization between 
Raft message objects and bytes for network transmission.
"""
import json
import time
from datetime import datetime, timezone
from typing import Union, Any, Type
import msgspec

from raftengine.messages.base_message import BaseMessage
from raftengine.messages.log_msg import LogMessage
from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage, PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage

# Epoch: January 1, 2025, 00:00:00 UTC
EPOCH = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()

class SerialNumberGenerator:
    generator = None

    @classmethod
    def get_generator(cls):
        if cls.generator is None:
            cls.generator = cls()
        return cls.generator
    
    def __init__(self):
        self.last_timebase = None
        self.counter = 0

    def generate(self):
        # Get current UTC time
        now = time.time()
        # Calculate days and seconds since epoch
        seconds_since_epoch = int(now - EPOCH)
        days_since_epoch = seconds_since_epoch // 86400
        seconds_since_midnight = seconds_since_epoch % 86400
        # Compute timebase
        timebase = days_since_epoch * 86400 + seconds_since_midnight
        # Reset counter if timebase has changed
        if timebase != self.last_timebase:
            self.counter = 0
            self.last_timebase = timebase
        # Generate serial number
        serial = timebase * 1000000 + self.counter
        # Increment counter (up to 999,999)
        self.counter = (self.counter + 1) % 1000000
        return serial


class MessageCodec:
    """
    Handles encoding and decoding of Raft messages to/from bytes.
    
    This class provides a centralized way to serialize Raft message objects
    to bytes for network transmission and deserialize bytes back to message objects.
    I tried implementing this with msgspec but only saw a small and inconsistent
    improvement in throughput in performace testing. Testing on a laptop running
    a full desktop of stuff. With builtin json I got a maximum throughput of 548/s,
    with msgspec I got 551/s. The test application I used is in examples/bank. When
    I converted the Collector/Dispatcher code in that example from jsonpickle to
    msgspec json I got a big improvement. With jsonpickle I was getting a max of
    463/s, so 1.18x, pretty hefty. I think the moral of the story is that encoding
    and decoding is a pretty small part of what this library is doing.
    """
    
    MESSAGE_TYPE_BY_CODE = {
        AppendEntriesMessage.get_code(): AppendEntriesMessage,
        AppendResponseMessage.get_code(): AppendResponseMessage,
        RequestVoteMessage.get_code(): RequestVoteMessage,
        RequestVoteResponseMessage.get_code(): RequestVoteResponseMessage,
        PreVoteMessage.get_code(): PreVoteMessage,
        PreVoteResponseMessage.get_code(): PreVoteResponseMessage,
        TransferPowerMessage.get_code(): TransferPowerMessage,
        TransferPowerResponseMessage.get_code(): TransferPowerResponseMessage,
        MembershipChangeMessage.get_code(): MembershipChangeMessage,
        MembershipChangeResponseMessage.get_code(): MembershipChangeResponseMessage,
        SnapShotMessage.get_code(): SnapShotMessage,
        SnapShotResponseMessage.get_code(): SnapShotResponseMessage,
    }
    
    @classmethod
    def encode_message(cls, message) -> tuple[bytes, int]:
        if not hasattr(message, 'serial_number') or message.serial_number is None or message.serial_number == 0:
            message.serial_number = SerialNumberGenerator.get_generator().generate()
            
        json_str = json.dumps(message, default=lambda o: o.__dict__)
        return json_str.encode('utf-8'), message.serial_number
    
    @classmethod
    def decode_message(cls, data):
        # we let exceptions propogate, callers all have handlers
        if isinstance(data, bytes):
            json_str = data.decode('utf-8')
        else:
            json_str = data
        message_dict = json.loads(json_str)
        message_type = cls.MESSAGE_TYPE_BY_CODE[message_dict['code']]
        return message_type.from_dict(message_dict)

