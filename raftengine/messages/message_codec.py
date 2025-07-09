"""
Message encoding/decoding for Raft protocol messages.

This module provides centralized message serialization between 
Raft message objects and bytes for network transmission.
"""
import json
from typing import Union

from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage, PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage


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
    def encode_message(cls, message) -> bytes:
        """
        Encode a message object to bytes.
        
        Args:
            message: A Raft message object that extends BaseMessage
            
        Returns:
            bytes: The encoded message as bytes
            
        Raises:
            TypeError: If message cannot be serialized
        """
        try:
            json_str = json.dumps(message, default=lambda o: o.__dict__)
            return json_str.encode('utf-8')
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
    """Encode a message object to bytes."""
    return MessageCodec.encode_message(message)


def decode_message(data):
    """Decode bytes or string to a message object."""
    return MessageCodec.decode_message(data)