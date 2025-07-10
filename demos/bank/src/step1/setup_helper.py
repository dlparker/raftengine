import os
from base.setup_helper import SetupHelperAPI
from base.client import Client
from base.operations import Ops
from step1.proxy import ServerProxy


class SetupHelper(SetupHelperAPI):

    async def get_client(self, db_file:os.PathLike):
        server = await self.get_server(db_file=db_file)
        proxy = await self.get_proxy(server=server)
        return Client(server_proxy=proxy)

    async def get_server(self, db_file:os.PathLike):
        return Ops(db_file)
    
    async def get_proxy(self, server:Ops):
        return ServerProxy(server=server)
        
    
    async def serve(self, server):
        pass
