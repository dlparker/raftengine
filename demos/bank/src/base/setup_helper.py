from abc import ABC, abstractmethod
from base.client import Client
from base.server import Server
from base.proxy_api import ProxyAPI

class SetupHelperAPI(ABC):

    @abstractmethod
    async def get_client(self, **kwargs):
        """ get a client instance configured with the kwargs contents"""
        raise NotImplemented

    @abstractmethod
    async def get_server(self, **kwargs):
        """ get a server instance configured with the kwargs contents"""
        raise NotImplemented
    
    @abstractmethod
    async def get_proxy(self, **kwargs):
        """ get a server proxy instance configured with the kwargs contents"""
        raise NotImplemented
    
