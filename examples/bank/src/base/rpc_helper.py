from abc import ABC, abstractmethod



class RPCHelperAPI(ABC):

    @abstractmethod
    async def rpc_client_maker(self, host, port):
        raise NotImplemented

    @abstractmethod
    async def get_rpc_server(self, raft_server):
        raise NotImplemented

    @abstractmethod
    async def start_server_task(self):
        raise NotImplemented

    @abstractmethod
    async def stop_server_task(self):
        raise NotImplemented


