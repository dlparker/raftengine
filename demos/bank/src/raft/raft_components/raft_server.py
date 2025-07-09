from typing import Dict, Any
from src.base.server import Server
from src.raft.raft_components.pilot import DeckHand

class RaftServer(Server):
    """Banking server extended with Raft messaging capability"""

    def __init__(self, db_file):
        self.deckhand = None
        super().__init__(db_file=db_file)

    def set_deckhand(self, deckhand: DeckHand):
        self.deckhand = deckhand
    
    async def raft_message(self, in_message: Dict[str, Any]) -> Dict[str, Any]:
        print('in server raft_message')
        return await self.deckhand.raft_message(in_message)

