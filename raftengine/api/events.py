from enum import Enum
from typing import Optional
from raftengine.messages.base_message import BaseMessage

class EventType(str, Enum):
    error = "ERROR"
    msg_sent = "MSG_SENT"
    msg_recv = "MSG_RECV"
    msg_handled = "MSG_HANDLED"
    role_change = "ROLE_CHANGE"
    term_change = "TERM_CHANGE"
    leader_change = "LEADER_CHANGE"
    log_update = "LOG_UPDATE"

    def __str__(self):
        return self.value

class Event:

    def __init__(self, event_type):
        self.event_type = event_type

class RoleChangeEvent(Event):

    def __init__(self, new_role):
        self.event_type = EventType.role_change
        self.new_role = new_role

        
class MsgEvent(Event):

    def __init__(self, msg:BaseMessage, event_type:EventType):
        self.event_type = EventType.msg_handled
        self.msg_type = msg.code
        self.term = msg.term
        self.sender = msg.sender
        self.receiver = msg.receiver
        self.prevLogIndex = msg.prevLogIndex
        self.prevLogTerm = msg.prevLogTerm
        
class HandledMessageEvent(MsgEvent):

    def __init__(self, msg:BaseMessage, result: Optional[str] = None, error: Optional[str] = None):
        super().__init__(msg, EventType.msg_handled)
        self.result = result
        self.error = error

class EventHandler:

    def __init__(self, event_types: list[EventType]):
        self.event_types = event_types

    def events_handled(self) -> list[EventType]:
        return self.event_types
    
    def handles(self, event_type: EventType) -> bool:
        if event_type in self.event_types:
            return True
        return False

    async def do_on_event(self, event_type: EventType, data: dict) -> None:
        if not event_type in self.event_types:
            return 
        await self.on_event(event_type, data)

    # override this
    async def on_event(self, event: Event) -> None:
        pass

