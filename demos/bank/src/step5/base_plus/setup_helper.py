from abc import ABC, abstractmethod
from base.client import Client
from base.operations import Ops
from base.proxy_api import OpsProxyAPI

class SetupHelperAPI(ABC):

    @abstractmethod
    async def get_client(self, **kwargs): 
        """ get a client instance configured with the kwargs contents"""
        raise NotImplemented # pragma: no cover

    @abstractmethod
    async def get_client_from_uri(self, uri):
        """ get a client instance configured with the kwargs contents"""
        raise NotImplemented # pragma: no cover

    @abstractmethod
    async def get_rpc_client(self, **kwargs):
        """ get a server proxy instance configured with the kwargs contents"""
        raise NotImplemented # pragma: no cover
    
    @abstractmethod
    async def get_raft_server(self, initial_cluster_config, local_config):
        """ get a server instance configured with the kwargs contents"""
        raise NotImplemented # pragma: no cover

    @abstractmethod
    async def get_rpc_server(self, raft_server):
        """ get a server instance configured with the kwargs contents"""
        raise NotImplemented # pragma: no cover
    
    @abstractmethod
    async def start_server_task(self, rpc_server):
        """ enter the servers run loop """
        raise NotImplemented # pragma: no cover
        
    @abstractmethod
    async def stop_server_task(self):
        """ enter the servers run loop """
        raise NotImplemented # pragma: no cover
        
