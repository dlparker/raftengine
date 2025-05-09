import abc
from typing import Any, Optional

class SnapShotAPI(abc.ABC):

    @abc.abstractmethod
    def get_last_index(self) -> int:# pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_last_term(self) -> int:# pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def add_data_item(self, item:Any) -> None:# pragma: no cover abstract
        raise NotImplementedError
        
    @abc.abstractmethod
    async def get_chunk(self, offset:Optional[int] = 0) -> (str, int, bool):# pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def save_chunk(self, data:str, offset:Optional[int] = 0) -> None:# pragma: no cover abstract
        raise NotImplementedError

class SnapToolAPI(abc.ABC):

    @abc.abstractmethod
    def set_log(self, log) -> None:# pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def take_snapshot(self) -> SnapShotAPI:# pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def start_snapshot_load(self, last_index, last_term, first_chunk) -> None: # pragma: no cover abstract
        raise NotImplementedError
        
    @abc.abstractmethod
    async def continue_snapshot_load(self, chunk, offset, done) -> None:# pragma: no cover abstract
        raise NotImplementedError
        


