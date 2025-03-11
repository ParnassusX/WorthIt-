"""Integration tests for security features.

This module tests the security enhancements implemented for production readiness:
- API key rotation mechanism
- Secure payment processing with encryption
- Fraud detection for payment transactions
- Image processing optimization
"""

import pytest
import json
import time
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from api.main import app
from api.key_rotation import key_rotation_manager
from api.payment_encryption import encrypt_payment_data, decrypt_payment_data
from api.fraud_detection import fraud_detector
from api.image_processor import ImageProcessor
from api.data_cache import DataCache

# Create test client
client = TestClient(app)


@pytest.fixture
def mock_data_cache():
    """Create a mock data cache for testing."""
    cache = MagicMock(spec=DataCache)
    cache.get_data = AsyncMock(return_value=None)
    cache.set_data = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_payment_data():
    """Create mock payment data for testing."""
    return {
        "card_number": "4111111111111111",
        "expiry": "12/25",
        "cvv": "123",
        "amount": 99.99,
        "currency": "USD",
        "customer_id": "test_user_123"
    }


class TestKeyRotation:
    """Tests for API key rotation mechanism."""
    
    def test_key_rotation_initialization(self):
        """Test that key rotation manager initializes correctly."""
        # Verify the manager exists and has expected attributes
        assert hasattr(key_rotation_manager, "rotation_schedules")
        assert hasattr(key_rotation_manager, "last_rotation")
    
    @pytest.mark.asyncio
    async def test_key_rotation_process(self):
        """Test the key rotation process."""
        # Set up a test service
        service_name = "test_service"
        original_key = "test_key_original"
        new_key = "test_key_new"
        
        # Store the original key
        key_rotation_manager._store_key(service_name, original_key)
        
        # Verify the key is stored correctly
        assert key_rotation_manager.get_key(service_name) == original_key
        
        # Rotate the key
        rotation_result = await key_rotation_manager.rotate_key(service_name, new_key)
        
        # Verify rotation was successful
        assert rotation_result is True
        
        # Verify the new key is now the current key
        assert key_rotation_manager.get_key(service_name) == new_key
        
        # Verify the original key is now the previous key
        assert key_rotation_manager.get_previous_key(service_name) == original_key
        
        # Verify both keys are valid during overlap period
        assert key_rotation_manager.is_key_valid(service_name, original_key) is True
        assert key_rotation_manager.is_key_valid(service_name, new_key) is True


class TestPaymentEncryption:
    """Tests for payment encryption functionality."""
    
    def test_payment_encryption_decryption(self, mock_payment_data):
        """Test that payment data can be encrypted and decrypted correctly."""
        # Encrypt the payment data
        encrypted = encrypt_payment_data(mock_payment_data)
        
        # Verify the encrypted data has the expected structure
        assert "encrypted_data" in encrypted
        assert "iv" in encrypted
        assert "hmac" in encrypted
        assert "version" in encrypted
        
        # Decrypt the payment data
        decrypted = decrypt_payment_data(encrypted)
        
        # Verify the decrypted data matches the original
        assert decrypted["card_number"] == mock_payment_data["card_number"]
        assert decrypted["amount"] == mock_payment_data["amount"]
        assert decrypted["customer_id"] == mock_payment_data["customer_id"]
    
    def test_payment_encryption_middleware(self, mock_payment_data):
        """Test the payment encryption middleware."""
        with patch("api.payment_encryption.encrypt_payment_data") as mock_encrypt:
            mock_encrypt.return_value = {"encrypted": "data"}
            
            # Make a request to a payment endpoint
            response = client.post(
                "/api/payment/process",
                json={"payment_data": mock_payment_data}
            )
            
            # Verify the encryption function was called
            mock_encrypt.assert_called_once()


class TestFraudDetection:
    """Tests for fraud detection functionality."""
    
    def test_fraud_detection_risk_scoring(self):
        """Test that fraud detection correctly scores transaction risk."""
        # Create a test transaction
        transaction = {
            "amount": 500,
            "card_last4": "1234",
            "country_code": "US"
        }
        
        # Analyze the transaction
        is_fraudulent, risk_score, reason = fraud_detector.analyze_transaction(
            transaction, "test_user", "127.0.0.1"
        )
        
        # Verify the result
        assert isinstance(is_fraudulent, bool)
        assert 0 <= risk_score <= 1
        
        # Test high-risk transaction
        high_risk_transaction = {
            "amount": 5000,  # High amount
            "card_last4": "5678",
            "country_code": "XX"  # High-risk country
        }
        
        # Analyze the high-risk transaction
        is_fraudulent, risk_score, reason = fraud_detector.analyze_transaction(
            high_risk_transaction, "test_user", "127.0.0.1"
        )
        
        # Verify the result indicates higher risk
        assert risk_score > 0.5
    
    def test_fraud_detection_middleware(self):
        """Test the fraud detection middleware."""
        # Make a request to a payment endpoint
        with patch("api.fraud_detection.fraud_detector.analyze_transaction") as mock_analyze:
            mock_analyze.return_value = (False, 0.3, None)
            
            response = client.post(
                "/api/payment/process",
                json={"amount": 100, "card_last4": "1234"}
            )
            
            # Verify the middleware allows the request to proceed
            assert response.status_code != 403


class TestImageProcessing:
    """Tests for image processing optimization."""
    
    @pytest.mark.asyncio
    async def test_image_processing_optimization(self, mock_data_cache):
        """Test that image processing optimizations work correctly."""
        # Create an image processor with mock cache
        processor = ImageProcessor(mock_data_cache)
        
        # Create test image data (a simple 10x10 red square)
        from PIL import Image
        import io
        
        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        test_image_data = buffer.getvalue()
        
        # Process the image
        processed_data = await processor.process_image(test_image_data, ['optimize'])
        
        # Verify the image was processed
        assert processed_data is not None
        assert len(processed_data) > 0
        
        # Verify cache was used
        mock_data_cache.set_data.assert_called_once()
        
        # Process the same image again to test caching
        mock_data_cache.get_data.return_value = processed_data
        cached_data = await processor.process_image(test_image_data, ['optimize'])
        
        # Verify cached data was returned
        assert cached_data == processed_data
        assert processor.processing_stats['cached_hits'] == 1
    
    @pytest.mark.asyncio
    async def test_parallel_image_processing(self, mock_data_cache):
        """Test parallel processing of multiple images."""
        # Create an image processor with mock cache
        processor = ImageProcessor(mock_data_cache)
        
        # Create test image data
        from PIL import Image
        import io
        
        test_images = []
        for i in range(3):
            img = Image.new('RGB', (100, 100), color=(255, i*50, 0))
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG')
            test_images.append(buffer.getvalue())
        
        # Process multiple images in parallel
        processed_images = await processor.process_multiple_images(test_images, ['optimize'])
        
        # Verify all images were processed
        assert len(processed_images) == 3
        assert all(img is not None for img in processed_images)
        
        # Verify parallel batch was recorded
        assert processor.processing_stats['parallel_batches'] == 1


# Run the tests with: pytest -xvs tests/integration/test_security_features.py