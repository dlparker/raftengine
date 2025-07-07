from typing import Dict, Any
from src.base.server import Server


class RaftServer(Server):
    """Banking server extended with Raft messaging capability"""
    
    async def raft_message(self, in_message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Raft consensus messages - stub implementation"""
        print(f"Raft message received: {in_message}")
        return in_message