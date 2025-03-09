import logging
import time
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    response_time: float
    request_count: int
    error_count: int
    cache_hits: int
    cache_misses: int
    compression_ratio: float
    batch_size: int
    timestamp: datetime

class PerformanceMonitor:
    def __init__(self):
        self._metrics: Dict[str, List[PerformanceMetrics]] = {}
        self._current_window: Dict[str, PerformanceMetrics] = {}
        self._window_size = 300  # 5 minutes
        self._last_cleanup = time.time()
        self.alerts = {
            'high_latency': 2.0,  # seconds
            'error_rate': 0.1,    # 10%
            'cache_miss': 0.3     # 30%
        }

    async def record_request(self, component: str, response_time: float, is_error: bool = False,
                           is_cache_hit: bool = False, compression_ratio: float = 1.0,
                           batch_size: int = 1) -> None:
        """Record performance metrics for a request."""
        if component not in self._current_window:
            self._current_window[component] = PerformanceMetrics(
                response_time=0,
                request_count=0,
                error_count=0,
                cache_hits=0,
                cache_misses=0,
                compression_ratio=0,
                batch_size=0,
                timestamp=datetime.now()
            )

        metrics = self._current_window[component]
        metrics.response_time = (metrics.response_time * metrics.request_count + response_time) / (metrics.request_count + 1)
        metrics.request_count += 1
        if is_error:
            metrics.error_count += 1
        if is_cache_hit:
            metrics.cache_hits += 1
        else:
            metrics.cache_misses += 1
        metrics.compression_ratio = (metrics.compression_ratio * (metrics.request_count - 1) + compression_ratio) / metrics.request_count
        metrics.batch_size = (metrics.batch_size * (metrics.request_count - 1) + batch_size) / metrics.request_count

        await self._check_alerts(component, metrics)
        await self._cleanup_old_metrics()

    async def _check_alerts(self, component: str, metrics: PerformanceMetrics) -> None:
        """Check for performance issues and log alerts."""
        if metrics.response_time > self.alerts['high_latency']:
            logger.warning(f"High latency detected in {component}: {metrics.response_time:.2f}s")

        error_rate = metrics.error_count / metrics.request_count
        if error_rate > self.alerts['error_rate']:
            logger.warning(f"High error rate in {component}: {error_rate:.2%}")

        if metrics.request_count > 10:  # Only check cache performance after sufficient requests
            cache_miss_rate = metrics.cache_misses / (metrics.cache_hits + metrics.cache_misses)
            if cache_miss_rate > self.alerts['cache_miss']:
                logger.warning(f"High cache miss rate in {component}: {cache_miss_rate:.2%}")

    async def _cleanup_old_metrics(self) -> None:
        """Move current window metrics to history and cleanup old data."""
        current_time = time.time()
        if current_time - self._last_cleanup > self._window_size:
            for component, metrics in self._current_window.items():
                if component not in self._metrics:
                    self._metrics[component] = []
                self._metrics[component].append(metrics)
                # Keep only last hour of metrics
                self._metrics[component] = self._metrics[component][-12:]

            self._current_window.clear()
            self._last_cleanup = current_time

    def get_component_metrics(self, component: str) -> Dict:
        """Get performance metrics for a component."""
        if component not in self._metrics:
            return {}

        current = self._current_window.get(component)
        historical = self._metrics[component]

        return {
            'current': current.__dict__ if current else None,
            'historical': [m.__dict__ for m in historical],
            'summary': {
                'avg_response_time': sum(m.response_time for m in historical) / len(historical),
                'error_rate': sum(m.error_count for m in historical) / sum(m.request_count for m in historical),
                'cache_hit_rate': sum(m.cache_hits for m in historical) / sum(m.request_count for m in historical),
                'avg_compression_ratio': sum(m.compression_ratio for m in historical) / len(historical),
                'avg_batch_size': sum(m.batch_size for m in historical) / len(historical)
            }
        }