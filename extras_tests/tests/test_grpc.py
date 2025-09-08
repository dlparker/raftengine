import asyncio
import logging
import types
import pytest


from rpc_common import RaftServerSim, seq_1, error_seq_1

async def test_grpc_1():
    
    from raftengine.extras.grpc_rpc import RPCServer, RPCClient
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

        
async def test_stop_errors(monkeypatch):
    from raftengine.extras.grpc_rpc import RPCServer

    class InsertServer(RPCServer):
        re_raise_cancel = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.logger = LoggerWrapper(actual_logger=self.logger)

            
        async def serve(self):
            try:
                await self.server.wait_for_termination()
            except asyncio.CancelledError:
                logger.warning(f'grpc server canceled')
                if self.re_raise_cancel:
                    raise
            finally:
                self.server_task = None
            
    class RaftServerSim:
        pass
    server = InsertServer(raft_server=RaftServerSim())

    await server.start(port=55555)
    server.re_raise_cancel = True
    await server.stop()
    assert "server_task cancelled" in server.logger.warning_lines

    
    server = InsertServer(raft_server=RaftServerSim())

    await server.start(port=55555)

    await server.start(port=55555)

    grpc_server = server.server

    # Save the original bound stop method
    original_stop = grpc_server.stop

    # Define mock (with self)
    async def mock_stop(self, grace=None):
        raise Exception("Forced error during server stop!")

    # Bind the mock to the instance to make it an instance method
    bound_mock = types.MethodType(mock_stop, server.server)

    # Monkeypatch with the bound mock
    monkeypatch.setattr(server.server, 'stop', bound_mock)

    # Test the stop error (this calls RPCServer.stop(), which uses the mocked server.stop())
    await server.stop()

    # Assert the error was logged
    found = False
    for elem in server.logger.error_lines:
        if "Error during server.stop(): Forced error during server stop!" in elem:
            found = True
            break
    assert found

    # Cleanup: Use the original stop method
    try:
        await original_stop(grace=0)
    except Exception:
        pass
    await grpc_server.wait_for_termination()
    await asyncio.sleep(0.05)


