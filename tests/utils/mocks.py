from unittest.mock import MagicMock

# Mock API responses
class MockAPIResponses:
    @staticmethod
    def get_success_response(data=None):
        """Returns a mock successful API response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'data': data or {}
        }
        return mock_response
    
    @staticmethod
    def get_error_response(status_code=400, message="Error"):
        """Returns a mock error API response"""
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = {
            'success': False,
            'error': message
        }
        return mock_response

# Mock Telegram API responses
class MockTelegramResponses:
    @staticmethod
    def get_webhook_info_response():
        """Returns a mock Telegram getWebhookInfo response"""
        return {
            'ok': True,
            'result': {
                'url': 'https://example.com/webhook',
                'has_custom_certificate': False,
                'pending_update_count': 0,
                'max_connections': 40
            }
        }
    
    @staticmethod
    def get_update_response(with_message=True):
        """Returns a mock Telegram getUpdates response"""
        result = []
        if with_message:
            result.append({
                'update_id': 123456789,
                'message': {
                    'message_id': 123,
                    'from': {'id': 456, 'first_name': 'Test User'},
                    'chat': {'id': 789, 'type': 'private'},
                    'text': '/analyze https://example.com/product'
                }
            })
        return {'ok': True, 'result': result}

# Mock Redis client
class MockRedisClient:
    def __init__(self):
        self.data = {}
        self.lists = {}
        self.sets = {}
    
    def get(self, key):
        return self.data.get(key)
    
    def set(self, key, value, ex=None):
        self.data[key] = value
        return True
    
    def lpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].insert(0, value)
        return len(self.lists[key])
    
    def rpop(self, key):
        if key not in self.lists or not self.lists[key]:
            return None
        return self.lists[key].pop()
    
    def sadd(self, key, value):
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].add(value)
        return 1
    
    def smembers(self, key):
        return self.sets.get(key, set())