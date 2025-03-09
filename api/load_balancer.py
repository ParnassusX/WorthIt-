import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ServiceNode:
    id: str
    url: str
    weight: int = 1
    active_connections: int = 0
    last_response_time: float = 0.0
    last_health_check: Optional[datetime] = None
    is_healthy: bool = True

class LoadBalancer:
    def __init__(self):
        self._nodes: Dict[str, ServiceNode] = {}
        self._current_index = 0
        self._lock = asyncio.Lock()
        self._strategies = {
            'round_robin': self._round_robin,
            'least_connections': self._least_connections,
            'weighted': self._weighted_round_robin,
            'response_time': self._response_time_based
        }
    
    async def add_node(self, node_id: str, url: str, weight: int = 1) -> None:
        """Add a new service node to the load balancer."""
        async with self._lock:
            self._nodes[node_id] = ServiceNode(id=node_id, url=url, weight=weight)
    
    async def remove_node(self, node_id: str) -> None:
        """Remove a service node from the load balancer."""
        async with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
    
    async def get_next_node(self, strategy: str = 'round_robin') -> Optional[ServiceNode]:
        """Get the next available node based on the selected strategy."""
        if not self._nodes:
            return None
        
        async with self._lock:
            if strategy not in self._strategies:
                raise ValueError(f"Unsupported load balancing strategy: {strategy}")
            return await self._strategies[strategy]()
    
    async def _round_robin(self) -> Optional[ServiceNode]:
        """Simple round-robin load balancing."""
        healthy_nodes = [node for node in self._nodes.values() if node.is_healthy]
        if not healthy_nodes:
            return None
        
        self._current_index = (self._current_index + 1) % len(healthy_nodes)
        return healthy_nodes[self._current_index]
    
    async def _least_connections(self) -> Optional[ServiceNode]:
        """Select the node with the least active connections."""
        healthy_nodes = [node for node in self._nodes.values() if node.is_healthy]
        if not healthy_nodes:
            return None
        
        return min(healthy_nodes, key=lambda x: x.active_connections)
    
    async def _weighted_round_robin(self) -> Optional[ServiceNode]:
        """Weighted round-robin load balancing."""
        healthy_nodes = [node for node in self._nodes.values() if node.is_healthy]
        if not healthy_nodes:
            return None
        
        total_weight = sum(node.weight for node in healthy_nodes)
        if total_weight == 0:
            return None
        
        point = (self._current_index + 1) % total_weight
        for node in healthy_nodes:
            if point <= node.weight:
                self._current_index = point - 1
                return node
            point -= node.weight
        
        return healthy_nodes[0]
    
    async def _response_time_based(self) -> Optional[ServiceNode]:
        """Select node based on recent response times."""
        healthy_nodes = [node for node in self._nodes.values() if node.is_healthy]
        if not healthy_nodes:
            return None
        
        # Find node with lowest response time
        return min(healthy_nodes, key=lambda x: x.last_response_time if x.last_response_time > 0 else float('inf'))
    
    async def update_metrics(self, node_id: str, response_time: float) -> None:
        """Update node metrics for better load balancing decisions."""
        async with self._lock:
            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.last_response_time = response_time
                # Adjust weight based on response time trend
                if response_time < 0.1:  # Fast response
                    node.weight = min(node.weight + 1, 10)
                elif response_time > 1.0:  # Slow response
                    node.weight = max(node.weight - 1, 1)
    
    async def update_node_status(self, node_id: str, *, 
                                is_healthy: Optional[bool] = None,
                                response_time: Optional[float] = None,
                                connections: Optional[int] = None) -> None:
        """Update node status information."""
        async with self._lock:
            if node_id in self._nodes:
                node = self._nodes[node_id]
                if is_healthy is not None:
                    node.is_healthy = is_healthy
                if response_time is not None:
                    node.last_response_time = response_time
                if connections is not None:
                    node.active_connections = connections
                node.last_health_check = datetime.now()
    
    async def get_node_status(self) -> Dict[str, Dict]:
        """Get status information for all nodes."""
        return {
            node_id: {
                'url': node.url,
                'healthy': node.is_healthy,
                'connections': node.active_connections,
                'response_time': node.last_response_time,
                'last_check': node.last_health_check.isoformat() if node.last_health_check else None
            }
            for node_id, node in self._nodes.items()
        }