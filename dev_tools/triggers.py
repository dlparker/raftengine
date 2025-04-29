import logging
from collections import defaultdict

from raftengine.messages.append_entries import AppendEntriesMessage


class PauseTrigger: # pragma: no cover

    async def is_tripped(self, server):
        return False

async def flush_one_out_message(server, message):
     new_list = None
     if not server.block_messages:
         for msg in server.out_messages:
             if new_list is None:
                 new_list = []
             if msg == message:
                 server.logger.debug("FLUSH forwarding message %s", msg)
                 await server.cluster.post_in_message(msg)
             else:
                 new_list.append(msg)
     if new_list is not None:
         server.out_messages = new_list
     return new_list


class WhenMessageOut(PauseTrigger):
    # When a particular message have been sent
    # by the raft code, and is waiting to be transported
    # to the receiver. You can just check the message
    # type, or require that type and a specific target receiver.
    # If you don't care about inspecting the message before it
    # is transported to the target server, leave the flush_when_done
    # flag set to True, otherwise set if false and then arrange for
    # transport after inspecting.
    def __init__(self, message_code, message_target=None, flush_when_done=True):
        self.message_code = message_code
        self.message_target = message_target
        self.flush_when_done = flush_when_done
        self.trigger_message = None

    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code}"
        if self.message_target:
            msg += f"target={self.message_target}"
        return msg

    async def is_tripped(self, server):
        done = False
        message = None
        for message in server.out_messages:
            if message.get_code() == self.message_code:
                if self.message_target is None:
                    done = True
                elif self.message_target == message.receiver:
                    done = True
        if done:
            self.trigger_message = message
            if self.flush_when_done:
                await flush_one_out_message(server, message)
        return done


class WhenCommitIndexSent(WhenMessageOut):

    def __init__(self, target_index, message_target=None):
        super().__init__(AppendEntriesMessage.get_code(), message_target, flush_when_done=True)
        self.target_index = target_index
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" index={self.target_index}"
        return msg

    async def is_tripped(self, server):
        done = False
        if await super().is_tripped(server):
            if self.trigger_message.commitIndex == self.target_index:
                done = True
        return done
    
class WhenMessageIn(PauseTrigger):
    # When a particular message have been transported
    # from a different server and placed in the input
    # pending buffer of this server. The message
    # in question has not yet been delivered to the
    # raft code. You can just check the message
    # type, or require that type and a specific sender
    def __init__(self, message_code, message_sender=None):
        self.message_code = message_code
        self.message_sender = message_sender

    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code} {self.message_sender}"
        return msg
    
    async def is_tripped(self, server):
        done = False
        for message in server.in_messages:
            if message.get_code() == self.message_code:
                if self.message_sender is None:
                    done = True
                if self.message_sender == message.sender:
                    done = True
        return done
    
class WhenInMessageCount(PauseTrigger):
    # When a particular message has been transported
    # from a different server and placed in the input
    # pending buffer of this server a number of times.
    # Until the count is reached, messages will be processed,
    # then the last on will be held in the input queue.
    # If this is a problem follow the wait for this trigger
    # with server.do_next_in_msg()

    def __init__(self, message_code, goal):
        self.message_code = message_code
        self.goal = goal
        self.captured = []
        self.logged_done = False

    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code} {self.goal}"
        return msg
    
    async def is_tripped(self, server):
        logger = logging.getLogger("Triggers")
        for message in server.in_messages:
            if message.get_code() == self.message_code:
                if message not in self.captured:
                    self.captured.append(message)
                    logger.debug("%s captured = %s", self, self.captured)
        if len(self.captured) == self.goal:
            if not self.logged_done:
                logger.debug("%s satisfied ", self)
                self.logged_done = True
            return True
        else:
            return False
    
    
class WhenAllMessagesForwarded(PauseTrigger):
    # When the server has forwarded (i.e. transported) all
    # of its pending output messages to the other servers,
    # where they sit in the input queues.

    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
    
    async def is_tripped(self, server):
        if len(server.out_messages) > 0:
            return False
        return True
    
class WhenAllInMessagesHandled(PauseTrigger):
    # When the server has processed all the messages
    # in the input queue, submitting them to the raft
    # code for processing.

    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
    
    async def is_tripped(self, server):
        if len(server.in_messages) > 0:
            return False
        return True
    
class WhenIsLeader(PauseTrigger):
    # When the server has won the election and
    # knows it.
    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
    
    async def is_tripped(self, server):
        if server.hull.get_role_name() == "LEADER":
            return True
        return False
    
class WhenHasLeader(PauseTrigger):
    # When the server started following specified leader
    def __init__(self, leader_uri):
        self.leader_uri = leader_uri

    def __repr__(self):
        msg = f"{self.__class__.__name__} leader={self.leader_uri}"
        return msg
        
    async def is_tripped(self, server):
        if server.hull.get_role_name() != "FOLLOWER":
            return False
        if server.hull.role.leader_uri == self.leader_uri:
            return True
        return False
    
class WhenHasLogIndex(PauseTrigger):
    # When the server has saved record with provided index
    def __init__(self, index):
        self.index = index

    def __repr__(self):
        msg = f"{self.__class__.__name__} index={self.index}"
        return msg
        
    async def is_tripped(self, server):
        if await server.hull.log.get_last_index() >= self.index:
            return True
        return False
    
class WhenHasCommitIndex(PauseTrigger):
    # When the server has committed record with provided index
    def __init__(self, index):
        self.index = index

    def __repr__(self):
        msg = f"{self.__class__.__name__} index={self.index}"
        return msg
        
    async def is_tripped(self, server):
        if await server.hull.log.get_commit_index() >= self.index:
            return True
        return False
    
class WhenHasAppliedIndex(PauseTrigger):
    # When the server has applied record with provided index
    def __init__(self, index):
        self.index = index

    def __repr__(self):
        msg = f"{self.__class__.__name__} index={self.index}"
        return msg
        
    async def is_tripped(self, server):
        if await server.hull.log.get_applied_index() >= self.index:
            return True
        return False
    
class WhenElectionDone(PauseTrigger):
    # Examine whole cluster to make sure we are in the
    # post election quiet period

    def __init__(self, voters=None):
        self.announced = defaultdict(dict)
        self.voters = voters
        
    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
        
    async def is_tripped(self, server):
        logger = logging.getLogger("Triggers")
        quiet = []
        have_leader = False
        if self.voters is None:
            self.voters = list(server.cluster.nodes.keys())
        for uri in self.voters:
            node = server.cluster.nodes[uri]
            if node.hull.get_role_name() == "LEADER":
                have_leader = True
                rec = self.announced[uri]
                if "is_leader" not in rec:
                    rec['is_leader'] = True
                    logger.debug('%s is now leader', uri)
            if len(node.in_messages) == 0 and len(node.out_messages) == 0:
                quiet.append(uri)
                rec = self.announced[uri]
                if "is_quiet" not in rec:
                    rec['is_quiet'] = True
                    logger.debug('%s is now quiet, total quiet == %d', uri, len(quiet))
        if have_leader and len(quiet) == len(self.voters):
            return True
        return False
    
class TriggerSet:

    def __init__(self, triggers=None, mode="and", name=None):
        if triggers is None:
            triggers = []
        self.triggers = triggers
        self.mode = mode
        if name is None:
            bits = ' '.join([str(cond) for cond in triggers])
            name = f"Set-{bits}"
        self.name = name

    def __repr__(self):
        bits = ' '.join([str(cond) for cond in self.triggers])
        name = f"Set-{bits}"
        return name

    def add_trigger(self, trigger):
        self.triggers.append(trigger)

    async def is_tripped(self, server):
        logger = logging.getLogger("Triggers")
        for_set = 0
        for cond in self.triggers:
            is_tripped = await cond.is_tripped(server)
            if not is_tripped:
                if self.mode == "and":
                    return False
            for_set += 1
            if self.mode == "or":
                logger.debug(f"%s Trigger {cond} tripped, run done (or)", server.uri)
                return True
            if for_set == len(self.triggers):
                logger.debug(f"%s Trigger {cond} tripped, all tripped", server.uri)
                return True
        return False


