import asyncio
from collections import defaultdict
from typing import Optional

from raftengine.api.events import EventType, EventHandler, ErrorEvent, MsgSentEvent, MsgRecvEvent, MsgHandledEvent
from raftengine.api.events import RoleChangeEvent, TermChangeEvent, LeaderChangeEvent, IndexChangeEvent, CommitChangeEvent
from raftengine.api.events import MembershipChangeDoneEvent, MembershipChangeAbortedEvent
from raftengine.messages.base_message import BaseMessage


class EventControl:

    def __init__(self):
        self.error_events = [EventType.error,]
        self.message_events = [EventType.msg_sent, EventType.msg_recv,
                               EventType.msg_handled]
        self.major_events = [EventType.role_change, EventType.term_change,
                             EventType.leader_change]
        self.common_events = [EventType.index_change, EventType.commit_change]

        self.active_events = []
        self.handlers = []
        self.handler_map = defaultdict(list)

    def add_handler(self, handler: EventHandler) -> None:
        if not handler in self.handlers:
            self.handlers.append(handler)
            for event_type in handler.events_handled():
                if event_type not in self.active_events:
                    self.active_events.append(event_type)
                if handler not in self.handler_map[event_type]:
                    self.handler_map[event_type].append(handler)

    def remove_handler(self, handler: EventHandler) -> None:
        if handler in self.handlers:
            self.handlers.remove(handler)
            for event_type in handler.events_handled():
                self.handler_map[event_type].remove(handler)
                if len(self.handler_map[event_type]) == 0:
                    self.active_events.remove(event_type)

    async def emit_error(self, error:str) -> None:
        my_type = EventType.error
        event = ErrorEvent(error)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_sent_msg(self, msg:BaseMessage) -> None:
        my_type = EventType.msg_sent
        event = MsgSentEvent(msg)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_recv_msg(self, msg:BaseMessage) -> None:
        my_type = EventType.msg_recv
        event = MsgRecvEvent(msg)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_handled_msg(self, msg:BaseMessage, result: Optional[str] = None,
                               error: Optional[str] = None) -> None:
        my_type = EventType.msg_handled
        event = MsgHandledEvent(msg, result, error)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_role_change(self, new_role: str) -> None:
        my_type = EventType.role_change
        event = RoleChangeEvent(new_role)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_term_change(self, new_term:int) -> None:
        my_type = EventType.term_change
        event = TermChangeEvent(new_term)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_leader_change(self, new_leader:str) -> None:
        my_type = EventType.leader_change
        event = LeaderChangeEvent(new_leader)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_index_change(self, new_index):
        my_type = EventType.index_change
        event = IndexChangeEvent(new_index)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_commit_change(self, new_commit):
        my_type = EventType.commit_change
        event = CommitChangeEvent(new_commit)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_membership_change_complete(self, op, new_node_uri):
        my_type = EventType.membership_change_complete
        event = MembershipChangeDoneEvent(op, new_node_uri)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))

    async def emit_membership_change_aborted(self, op, new_node_uri):
        my_type = EventType.membership_change_aborted
        event = MembershipChangeAbortedEvent(op, new_node_uri)
        for handler in self.handler_map[my_type]:
            asyncio.create_task(handler.on_event(event))
