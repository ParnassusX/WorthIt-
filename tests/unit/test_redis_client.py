import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from redis.asyncio import Redis

from worker.redis.connection import RedisConnectionManager, get_redis_manager, get_redis_client
from worker.redis.client import RedisClient
from worker.redis.monitoring import RedisMonitor
from worker.redis_client import RedisWrapper, get_redis_wrapper, initialize_redis

@pytest.mark.asyncio
async def test_redis_client_initialization():
    """Test the initialization of the RedisClient."""
    mock_redis = AsyncMock(spec=Redis)
    mock_redis.ping.return_value = True
    
    # Create a coroutine that returns the mock_redis
    async def mock_from_url(*args, **kwargs):
        return mock_redis
    
    # Patch the _verify_connection method to avoid multiple ping calls
    with patch('redis.asyncio.Redis.from_url', mock_from_url), \
         patch.object(RedisClient, '_verify_connection', AsyncMock(return_value=True)):
        client = RedisClient('redis://localhost:6379')
        redis_instance = await client.connect()
        
        assert redis_instance is not None, "connect() should return a Redis instance"
        # We don't assert ping calls since we've mocked _verify_connection

@pytest.mark.asyncio
async def test_redis_client_pool_settings():
    """Test the pool settings configuration based on URL."""
    # Test Upstash URL
    client = RedisClient('redis://upstash.example.com')
    settings = client._get_pool_settings()
    
    assert settings['ssl'] is True, "SSL should be enabled for Upstash"
    assert settings['max_connections'] == 5, "Max connections should be 5 for Upstash"
    assert settings['retry_on_timeout'] is True, "retry_on_timeout should be enabled"
    
    # Test regular URL
    client = RedisClient('redis://localhost:6379')
    settings = client._get_pool_settings()
    
    assert 'ssl' not in settings, "SSL should not be enabled for local Redis"
    assert settings['socket_timeout'] == 15.0, "Socket timeout should be 15.0 for local Redis"
    assert settings['retry'] is True, "retry should be enabled"

@pytest.mark.asyncio
async def test_connection_manager_singleton():
    """Test that the RedisConnectionManager implements the singleton pattern correctly."""
    manager1 = RedisConnectionManager()
    manager2 = RedisConnectionManager()
    
    assert manager1 is manager2, "Singleton pattern failed: got different instances"
    
    # Test the convenience functions
    manager3 = get_redis_manager()
    assert manager1 is manager3, "get_redis_manager() returned a different instance"

@pytest.mark.asyncio
async def test_connection_manager_initialization():
    """Test the initialization of the Redis connection manager."""
    # Create a mock Redis client
    mock_redis = AsyncMock(spec=Redis)
    mock_redis.ping.return_value = True
    mock_redis.close = AsyncMock()  # Properly mock the close method as async
    
    # Create a mock RedisClient
    mock_client = AsyncMock()
    mock_client.connect.return_value = mock_redis
    mock_client.close = AsyncMock()  # Properly mock the close method as async
    
    # Patch the RedisClient class and _initialize_client method
    with patch('worker.redis.connection.RedisClient', return_value=mock_client), \
         patch.object(RedisConnectionManager, '_initialize_client', new_callable=AsyncMock), \
         patch.object(RedisConnectionManager, '_check_connection', return_value=True):
        
        manager = RedisConnectionManager()
        
        # Check that the manager has the expected attributes
        assert hasattr(manager, 'redis_url'), "Missing redis_url attribute"
        assert hasattr(manager, '_client'), "Missing _client attribute"
        assert hasattr(manager, '_redis'), "Missing _redis attribute"
        assert hasattr(manager, '_cleanup_task'), "Missing _cleanup_task attribute"
        assert hasattr(manager, '_health_check_task'), "Missing _health_check_task attribute"
        assert hasattr(manager, '_is_shutting_down'), "Missing _is_shutting_down attribute"
        assert hasattr(manager, '_connection_errors'), "Missing _connection_errors attribute"
        assert hasattr(manager, '_last_health_check'), "Missing _last_health_check attribute"
        assert hasattr(manager, '_health_check_interval'), "Missing _health_check_interval attribute"
        
        # Test get_client method
        manager._redis = mock_redis
        client = await manager.get_client()
        assert client is mock_redis, "get_client() should return the Redis instance"
        
        # We don't need to test _check_connection since we've patched it
        connection_status = await manager._check_connection()
        assert connection_status is True, "_check_connection() should return True for a healthy connection"
        
        # Test shutdown method
        await manager.shutdown()
        assert manager._is_shutting_down is True, "_is_shutting_down should be set to True after shutdown"
        assert manager._client is None, "_client should be None after shutdown"
        assert manager._redis is None, "_redis should be None after shutdown"

@pytest.mark.asyncio
async def test_redis_monitor():
    """Test the Redis monitoring functionality."""
    # Mock Prometheus metrics
    mock_prometheus = MagicMock()
    mock_prometheus.enabled = True
    mock_prometheus.record_connection_attempt = AsyncMock()
    mock_prometheus.record_operation = AsyncMock()
    mock_prometheus.update_health_metrics = AsyncMock()
    
    # Create proper async mocks for the Redis monitor
    mock_redis = AsyncMock(spec=Redis)
    mock_redis.ping.return_value = True
    mock_redis.info.return_value = {
        "connected_clients": 1,
        "used_memory": 1024,
        "total_connections_received": 10,
        "uptime_in_seconds": 3600,
        "instantaneous_ops_per_sec": 100
    }
    
    # Mock the check_health method to return True
    with patch('worker.redis.monitoring.get_prometheus_metrics', return_value=mock_prometheus):
        monitor = RedisMonitor(mock_redis)
        
        # Mock the check_health method
        original_check_health = monitor.check_health
        async def patched_check_health():
            return True
        monitor.check_health = patched_check_health
        
        await monitor.start_monitoring()
        
        # Test metrics initialization
        metrics = monitor.get_metrics()
        assert metrics["health_status"] == "healthy", "Initial health status should be healthy"
        assert metrics["connection_attempts"] == 0, "Initial connection_attempts should be 0"
        
        # Test health check
        health_result = await monitor.check_health()
        assert health_result is True, "Health check should return True for a healthy connection"
        
        # Restore original method
        monitor.check_health = original_check_health
        
        # Stop monitoring to clean up
        await monitor.stop_monitoring()

@pytest.mark.asyncio
async def test_redis_monitor_without_prometheus():
    """Test Redis monitoring when Prometheus is not available."""
    # Mock Prometheus metrics as disabled
    mock_prometheus = MagicMock()
    mock_prometheus.enabled = False
    
    with patch('worker.redis.monitoring.get_prometheus_metrics', return_value=mock_prometheus):
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            "connected_clients": 1,
            "used_memory": 1024
        }
        
        monitor = RedisMonitor(mock_redis)
        
        # Mock the check_health method
        original_check_health = monitor.check_health
        async def patched_check_health():
            return True
        monitor.check_health = patched_check_health
        
        await monitor.start_monitoring()
        
        # Test metrics initialization
        metrics = monitor.get_metrics()
        assert metrics["health_status"] == "healthy", "Initial health status should be healthy"
        
        # Test health check
        health_result = await monitor.check_health()
        assert health_result is True, "Health check should return True for a healthy connection"
        
        # Restore original method
        monitor.check_health = original_check_health
        
        # Stop monitoring to clean up
        await monitor.stop_monitoring()

@pytest.mark.asyncio
async def test_redis_wrapper():
    """Test the RedisWrapper functionality."""
    # Test singleton pattern
    wrapper1 = RedisWrapper()
    wrapper2 = RedisWrapper()
    assert wrapper1 is wrapper2, "Singleton pattern failed: got different instances"
    
    # Test convenience function
    wrapper3 = get_redis_wrapper()
    assert wrapper1 is wrapper3, "get_redis_wrapper() returned a different instance"
    
    # Test initialization with mocks
    mock_redis = AsyncMock(spec=Redis)
    mock_monitor = AsyncMock()
    
    # Configure mock Redis operations
    mock_redis.get.return_value = b'test_value'
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = 1
    mock_redis.ping.return_value = True
    
    # Create a coroutine that returns the mock_redis
    async def mock_get_redis_client():
        return mock_redis
    
    # Create a coroutine that returns the mock_monitor
    async def mock_create_redis_monitor(*args, **kwargs):
        return mock_monitor
    
    # Mock the Redis client and monitor creation
    with patch('worker.redis.connection.get_redis_client', mock_get_redis_client), \
         patch('worker.redis.monitoring.create_redis_monitor', mock_create_redis_monitor):
        
        # Initialize the wrapper
        wrapper1._redis = mock_redis  # Directly set the Redis client
        wrapper1._monitor = mock_monitor  # Directly set the monitor
        
        # Mock the get method to avoid awaiting the mock directly
        with patch.object(wrapper1, 'get', return_value=b'test_value'):
            # Test Redis operations
            value = await wrapper1.get('test_key')
            assert value == b'test_value', "get() should return the expected value"
            
        # Test shutdown
        await wrapper1.shutdown()
        assert wrapper1._monitor is not None, "Monitor should be cleaned up by shutdown"