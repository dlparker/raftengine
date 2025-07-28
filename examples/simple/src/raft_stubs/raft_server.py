import json
from pathlib import Path
from raftengine.api.types import CommandResult
from base.counters import Counters
from split_base.dispatcher import Dispatcher
from raft_stubs.rpc_helper import RPCHelper

class RaftServerStub:
    """
    In a real Raft server setup this class will probably implement the
    startup logic that to get the application ready to run, and will
    also fully implement the PilotAPI, or it will have some class instance
    that does so. Tying that all together is an application specific
    concernt, but the "raft_full" library modules will show how that
    can be done.
    """
    
    def __init__(self, port, clear=False):
        self.port =  port
        self.my_uri = f"aiozmq://localhost:{port}"
        self.storage_dir = Path("/tmp/counters_raft_stub.0")
        if not self.storage_dir.exists():
            self.storage_dir.mkdir()
        self.file_path = Path(self.storage_dir, 'counters.pickle')
        if self.file_path.exists() and clear:
            self.file_path.unlink()
        self.counters = Counters(self.storage_dir)
        self.dispatcher = Dispatcher(self.counters)
        self.pilot = PilotStub(self.dispatcher)
        self.deck = DeckStub(self.pilot)
        self.helper = RPCHelper()
        self.rpc_server = None
        
    # local only method
    async def start(self):
        await self.deck.start()
        self.rpc_server = await self.helper.get_rpc_server(self.port, self)
        await self.helper.start_server_task()
        self.stopped = False
    
    # local only method 
    async def stop(self):
        if not self.stopped:
            await self.helper.stop_server_task()
            await self.deck.stop()
            self.stopped = True

    # RPC method
    async def run_command(self, command):
        # RPC server calls this, we call the deck it calls the dispatcher.
        # This indirection has meaning in real raft setup as the run_command
        # is executed by the cluster leader only after it gets a majority
        # vote from the cluster. The indirection here is just to practice
        # getting the wiring right.
        raw_result = await self.deck.run_command(command)
        wrapped = json.dumps(CommandResult(command=command, result=raw_result).__dict__)
        #print(f"returning {json.loads(wrapped)}")
        return wrapped

    # RPC method
    async def raft_message(self, message):
        # RPC server calls this, we call the deck it. In real mode that
        # gets passed to role specific logic, Leader, Follower, Candidate,
        # whatever role the server currently fills. The Raft components
        # use this RPC to do the protocol data exchange to achieve consesus
        # on elections, commands, cluster membership changes, and also to
        # distrubute snapshots.
        return await self.deck.on_message(message)

class PilotStub:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
    
    async def process_command(self, command, serial):
        # In real mode this call comes from the "role" class
        # in the Raftengine, either Leader or Follower. 
        # We would not return a CommandResult, that is constructed
        # by the Leader. Followers don't even examine the result,
        # nor do they deliver it anywhere, so what you return
        # in that case. In this stub setup it is convienient
        # to construct the CommandResult here.
        return await self.dispatcher.route_command(command)
    
class DeckStub:
    """
    In a real Raft server setup this class is provided by Raftengine, so
    you create one of these and supply it with a PilotAPI implemention and
    a bunch of configuration. Whatever creates a Deck instance needs to
    tie it somehow to the PilotAPI and the application logic, which
    in this case means the Counters class wrapped up in a Dispatcher.
    """

    def __init__(self, pilot):
        self.pilot = pilot

    def set_pilot(self, pilot):
        self.pilot = pilot
        
    async def start(self):
        pass
    
    async def stop(self):
        pass
    
    async def run_command(self, command):
        # In real mode this goes to the "role" class, and if it
        # is a Leader role it will, if successful, eventually
        # call the Pilot process_command method. Here we take a
        # shortcut and go straight to the pilot. In real mode
        # the Leader will wrap up the result in a CommandResult
        # instance.
        return  await self.pilot.process_command(command, serial=1)


    async def on_message(self, message):
        # for this stage just be an echo server
        return message
