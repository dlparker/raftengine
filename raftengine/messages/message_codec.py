"""
Message encoding/decoding for Raft protocol messages.

This module provides centralized message serialization between 
Raft message objects and bytes for network transmission.
"""
import json
import time
from datetime import datetime, timezone
from typing import Union

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
    """
    
    # All supported message types
    MESSAGE_TYPES = [
        AppendEntriesMessage, AppendResponseMessage,
        RequestVoteMessage, RequestVoteResponseMessage,
        PreVoteMessage, PreVoteResponseMessage,
        TransferPowerMessage, TransferPowerResponseMessage,
        MembershipChangeMessage, MembershipChangeResponseMessage,
        SnapShotMessage, SnapShotResponseMessage,
    ]
    
    @classmethod
    def encode_message(cls, message) -> tuple[bytes, int]:
        """
        Encode a message object to bytes.
        
        Args:
            message: A Raft message object that extends BaseMessage
            
        Returns:
            tuple[bytes, int]: A tuple containing (encoded_message_bytes, serial_number)
            
        Raises:
            TypeError: If message cannot be serialized
        """
        try:
            # Auto-assign serial number if not set
            if not hasattr(message, 'serial_number') or message.serial_number is None or message.serial_number == 0:
                message.serial_number = SerialNumberGenerator.get_generator().generate()
            
            json_str = json.dumps(message, default=lambda o: o.__dict__)
            return json_str.encode('utf-8'), message.serial_number
        except Exception as e:
            raise TypeError(f"Failed to encode message: {e}")
    
    @classmethod
    def decode_message(cls, data):
        """
        Decode bytes or string to a message object.
        
        Args:
            data: bytes or string containing the encoded message
            
        Returns:
            A Raft message object that extends BaseMessage
            
        Raises:
            ValueError: If data cannot be decoded or message type is unknown
        """
        try:
            if isinstance(data, bytes):
                json_str = data.decode('utf-8')
            elif isinstance(data, str):
                json_str = data
            else:
                raise ValueError(f"Data must be bytes or string, got {type(data)}")
            
            message_dict = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to decode message: {e}")
        
        # Find the appropriate message type based on the code
        message_code = message_dict.get('code')
        if not message_code:
            raise ValueError("Message missing required 'code' field")
        
        for message_type in cls.MESSAGE_TYPES:
            if message_dict['code'] == message_type.get_code():
                return message_type.from_dict(message_dict)
        
        raise ValueError(f'Message is not decodeable as a raft type: {message_code}')


# Convenience functions for backward compatibility
def encode_message(message) -> bytes:
    """Encode a message object to bytes. Returns only the bytes for backward compatibility."""
    encoded_bytes, _ = MessageCodec.encode_message(message)
    return encoded_bytes


def decode_message(data):
    """Decode bytes or string to a message object."""
    return MessageCodec.decode_message(data)




