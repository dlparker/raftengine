import asyncio
import json
import logging
import traceback
import types
import pytest

from rpc_common import RaftServerSim, seq_1, error_seq_1
from raftengine.extras.astream_rpc import RPCServer, RPCClient
from raftengine.extras.astream_rpc.rpc_server import ClientFollower

logger = logging.getLogger("test_code")

async def test_astream_1():
    
    from raftengine.extras.astream_rpc import RPCServer, RPCClient
    await seq_1(RPCServer, RPCClient)
    await error_seq_1(RPCServer, RPCClient)

class LoggerWrapper(logging.Logger):

    def __init__(self, *args, **kwargs):
        self.actual_logger = kwargs.pop('actual_logger')
        self.error_lines = []
        self.warning_lines = []
        self.info_lines = []
        self.debug_lines = []
        
    def error(self, *args, **kwargs):
        self.error_lines.append(args[0])
        self.actual_logger.error(*args, **kwargs)
        
    def warning(self, *args, **kwargs):
        self.warning_lines.append(args[0])
        self.actual_logger.warning(*args, **kwargs)

    def info(self, *args, **kwargs):
        self.info_lines.append(args[0])
        self.actual_logger.info(*args, **kwargs)

    def debug(self, *args, **kwargs):
        self.debug_lines.append(args[0])
        self.actual_logger.debug(*args, **kwargs)


class InsertServer(RPCServer):
    re_raise_cancel = False

    def __init__(self, *args, **kwargs):
        self.client_follower_class = kwargs.pop('client_follower_class', None)
        super().__init__(*args, **kwargs)
        self.logger = LoggerWrapper(actual_logger=self.logger)
        self.skip_close = False

    async def serve(self):
        self.logger.info(f"server running on port {self.port}")
        try:
            # Keep the server running
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.logger.warning(f'astream server cancelled')
            if self.re_raise_cancel:
                self.logger.warning('re-rasing')
                raise
        finally:
            if self.sock_server and not self.skip_close:
                self.sock_server.close()
                self.sock_server = None
            self.server_task = None

    async def handle_client(self, reader, writer):
        if not self.client_follower_class:
            return await super().handle_client(reader, writer)
        info = writer.get_extra_info("peername")
        self.logger.debug(f"New client connection from {info}")
        cf = self.client_follower_class(self, reader, writer)
        
        # Track this connection
        self.active_connections.add(cf)
        
        try:
            await cf.run()
        finally:
            # Remove from tracking
            self.active_connections.discard(cf)
            self.logger.debug(f"Client connection from {info} closed (my port={self.port})")
            try:
                writer.close()
            except:
                pass
            
async def test_astream_shutdowns():
    
    logger.info("Check that delete of client follower instance cancels pending tasks")
    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    # make sure a second call does not blow up
    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]
    asyncio.create_task(client.issue_command('delay'))
    await asyncio.sleep(0.001)
    assert len(conn.active_tasks) > 0
    conn.__del__()
    assert len(conn.active_tasks) == 0
    server.active_connections = set()
    await asyncio.sleep(0.01)

    await client.close()
    await server.stop()
    
    logger.info("Check that stop of server cancels pending tasks")
    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]
    asyncio.create_task(client.issue_command('delay'))
    await asyncio.sleep(0.001)
    assert len(conn.active_tasks) > 0
    await server.stop()
    assert len(conn.active_tasks) == 0
    await client.close()

    logger.info("Check that errors do not block client follower shutdown")
    
    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]

    del conn.active_tasks  # will cause exception in active task cleanup
    del conn.writer # will cause exception in writer close check
    await conn.cleanup()
    # didn't blow up
    server.active_connects = set()
    await server.stop()
    await client.close()

class StreamReaderWrapper:

    def __init__(self, real):
        self.real = real
        self.read_no_length = False
        self.read_no_message = False
        self.explode_on_length = False
        self.have_length = False
        self.bogus_message = None
        
    async def read(self, length):
        try:
            if self.bogus_message:
                if length == 20:
                    mlen = len(self.bogus_message)
                    logger.debug(f"Wrapper returning length {mlen} of bogus message on length read")
                    return str(mlen).encode()
                else:
                    logger.debug(f"Wrapper returning bogus message {self.bogus_message}")
                    msg = self.bogus_message
                    self.bogus_message = None
                    return msg
            res = await self.real.read(length)
            if self.bogus_message:
                if length == 20:
                    # read and discard the triggering message
                    msg_len = int(res.decode().strip())
                    msg = await self.real.read(msg_len)
                    mlen = len(self.bogus_message)
                    logger.debug(f"Wrapper returning length {mlen} of bogus message on length read (already pending)")
                    return str(mlen).encode()
                else:
                    logger.debug(f"Wrapper returning bogus message (already pending) {self.bogus_message}")
                    msg = self.bogus_message
                    self.bogus_message = None
                    return msg
            if length == 20 and not self.have_length:
                if self.read_no_length:
                    logger.debug(f"Wrapper returning None on length read")
                    return None
                if self.explode_on_length:
                    raise Exception('Exploding in inserted error reading length from command channel')
                self.have_length = True
                logger.debug(f"Wrapper returning from length read with {res}")
            else:
                self.have_length = False
                if self.read_no_message:
                    logger.debug(f"Wrapper returning None on message read length {length}")
                    return None
        except:
            res = None
            logger.debug(traceback.format_exc())
            raise
        logger.debug(f"Read of length {length} got res={res}")
        return res
        
class StreamWriterWrapper:

    def __init__(self, real):
        self.real = real
        self.explode_on_send = False
        self.catch_outgoing = False
        self.parts = []

    def get_extra_info(self, *args, **kwargs):
        return self.real.get_extra_info(*args, **kwargs)
    
    def write(self, data):
        if self.catch_outgoing:
            self.parts.append(data)
        if self.explode_on_send:
            raise Exception('Exploding on inserted error in stream send')
        return self.real.write(data)

    def drain(self):
        return self.real.drain()
    
class LoggerWrapper(logging.Logger):

    def __init__(self, *args, **kwargs):
        self.actual_logger = kwargs.pop('actual_logger')
        self.error_lines = []
        self.warning_lines = []
        self.info_lines = []
        self.debug_lines = []
        
    def error(self, *args, **kwargs):
        self.error_lines.append(args[0])
        self.actual_logger.error(*args, **kwargs)
        
    def warning(self, *args, **kwargs):
        self.warning_lines.append(args[0])
        self.actual_logger.warning(*args, **kwargs)

    def info(self, *args, **kwargs):
        self.info_lines.append(args[0])
        self.actual_logger.info(*args, **kwargs)

    def debug(self, *args, **kwargs):
        self.debug_lines.append(args[0])
        self.actual_logger.debug(*args, **kwargs)

    
class BreakingFollower(ClientFollower):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.writer = StreamWriterWrapper(self.writer)
        self.reader = StreamReaderWrapper(self.reader)
        self.explode_locally = False
        self.logger = LoggerWrapper(actual_logger=self.logger)
        
    async def process_request(self, request, request_id):
        mtype = request.get('mtype')
        message = request.get('message')
        timeout = request.get('timeout', 10.0)
        if self.explode_locally and mtype == "command" and message == "explode":
            # break the writer so that sending the response fails
            self.writer.real.close()
        return await super().process_request(request, request_id)

    async def cleanup(self):
        if self.explode_in_cleanup:
            raise Exception("inserted error in cleanup")
        return await super().cleanup()

async def test_astream_cf_explodes():

    logger.info("Check that error in client follower run cause exit")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer),client_follower_class=BreakingFollower)
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]

    conn.explode_locally = True
    with pytest.raises(Exception) as excinfo:
        await client.issue_command('explode')
    assert "closed" in str(excinfo)

    await server.stop()
    await client.close()
    
async def test_astream_server_short_reads():
    
    logger.info("Check that server short read of length from client channel closes the listener")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer),client_follower_class=BreakingFollower)
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]

    conn.reader.read_no_length = True
    with pytest.raises(Exception) as excinfo:
        await client.issue_command('foo')
    assert "closed" in str(excinfo)

    await server.stop()
    await client.close()

    logger.info("Check that server short read of message from client channel closes the listener")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer),client_follower_class=BreakingFollower)
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]

    conn.reader.read_no_message = True
    with pytest.raises(Exception) as excinfo:
        await client.issue_command('foo')
    assert "closed" in str(excinfo)

    await server.stop()
    await client.close()

async def test_astream_server_read_explodes():
    
    logger.info("Check that server read exception closes the listener")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer),client_follower_class=BreakingFollower)
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    await client.issue_command('foo')
    conn = list(server.active_connections)[0]

    conn.reader.explode_on_length = True
    with pytest.raises(Exception) as excinfo:
        await client.issue_command('foo')
    assert "closed" in str(excinfo)

    found = False
    for elem in conn.logger.error_lines:
        if "Exploding" in elem:
            found = True
            break
    assert found

    await server.stop()
    await client.close()
    
async def test_astream_server_bad_command():
    
    logger.info("Check that server read of a bad command sends an error reply")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer),client_follower_class=BreakingFollower)
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    print(await client.issue_command('foo'))
    conn = list(server.active_connections)[0]

    conn.reader.bogus_message = json.dumps(dict(mtype="badtype", message="foo", timeout=1.0, request_id=1111)).encode()
    conn.writer.catch_outgoing = True
    with pytest.raises(Exception) as excinfo:
        await client.issue_command('foo', timeout=0.01)
    assert "timed out" in str(excinfo)
    out_len = conn.writer.parts[0]
    out_msg_raw = conn.writer.parts[1]
    out_msg = json.loads(out_msg_raw.decode())
    assert "badtype" in out_msg['result']
    await server.stop()
    await client.close()
    
async def test_astream_server_cleanup_explodes():
    
    logger.info("Check that server shutdown succeeds when error happens in client follower cleanup")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer),client_follower_class=BreakingFollower)
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    print(await client.issue_command('foo'))
    server.logger = LoggerWrapper(actual_logger=server.logger)
    conn = list(server.active_connections)[0]
    conn.explode_in_cleanup = True
    await server.stop()

    found = False
    for elem in server.logger.warning_lines:
        if "Closing connection" in elem and "got error" in elem:
            found = True
            break
    assert found

    await client.close()
    
async def test_astream_server_stop_errors(monkeypatch):

    logger.info("Check that serve method re-raising cancelled does not break server stop method")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    print(await client.issue_command('foo'))
    server.logger = LoggerWrapper(actual_logger=server.logger)

    server.re_raise_cancel = True
    await server.stop()
    found = False
    for line in server.logger.warning_lines:
        if "server_task got cancelled" in line:
            found = True
            break
    assert found

    await client.close()

    logger.info("Check that server serve exit logic does not break due to exception on sock_server.close")

    server = RPCServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    print(await client.issue_command('foo'))
    server.logger = LoggerWrapper(actual_logger=server.logger)

    original_close = server.sock_server.close
    server.skip_close = True

    def mock_close(self):
        raise Exception("Forced error on sock_server.close during serve exit!")

    # Bind the mock to the instance to make it an instance method
    bound_mock = types.MethodType(mock_close, server.sock_server)

    # Monkeypatch with the bound mock
    monkeypatch.setattr(server.sock_server, 'close', bound_mock)

    await server.stop()
    found = False
    for elem in server.logger.warning_lines:
        if "serve exit" in elem and "closing sock_server got error" in elem:
            found = True
            break
    assert found
    original_close()
    await client.close()

    logger.info("Check that server stop succeeds when errors happen stopping socket server during stop method")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    print(await client.issue_command('foo'))
    server.logger = LoggerWrapper(actual_logger=server.logger)


    original_close = server.sock_server.close
    server.skip_close = True

    def mock_close(self):
        raise Exception("Forced error during server close!")

    # Bind the mock to the instance to make it an instance method
    bound_mock = types.MethodType(mock_close, server.sock_server)

    # Monkeypatch with the bound mock
    monkeypatch.setattr(server.sock_server, 'close', bound_mock)

    await server.stop()
    found = False
    for elem in server.logger.warning_lines:
        if "closing sock_server got error" in elem:
            found = True
            break
    assert found
    original_close()
    
    await client.close()

    logger.info("Check that server stop succeeds when wait closed gets cancelled")

    server = InsertServer(raft_server=RaftServerSim(rpc_server_class=RPCServer))
    port = 55555

    await server.start(port=port)
    client = RPCClient(host='127.0.0.1', port=port, timeout=0.1)
    print(await client.issue_command('foo'))
    server.logger = LoggerWrapper(actual_logger=server.logger)

    original_wait_close = server.sock_server.wait_closed
    server.skip_close = True

    async def mock_wait_closed(self):
        raise asyncio.CancelledError('inserted cancel')

    # Bind the mock to the instance to make it an instance method
    bound_mock = types.MethodType(mock_wait_closed, server.sock_server)

    # Monkeypatch with the bound mock
    monkeypatch.setattr(server.sock_server, 'wait_closed', bound_mock)

    await server.stop()
    found = False
    for elem in server.logger.warning_lines:
        if "sock_server.closed got cancelled" in elem:
            found = True
            break
    assert found
    await client.close()
    
