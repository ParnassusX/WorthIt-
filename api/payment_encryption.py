"""Payment encryption utilities for secure payment processing."""

import os
import base64
import logging
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get encryption key from environment or generate a secure one
ENCRYPTION_KEY = os.getenv("PAYMENT_ENCRYPTION_KEY", "")
if not ENCRYPTION_KEY:
    logger.warning("PAYMENT_ENCRYPTION_KEY not set. Generating a temporary key.")
    # In production, this should be set in environment variables
    # This is just a fallback for development
    ENCRYPTION_KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()

# Salt for key derivation
KEY_SALT = os.getenv("PAYMENT_KEY_SALT", "")
if not KEY_SALT:
    logger.warning("PAYMENT_KEY_SALT not set. Generating a temporary salt.")
    # In production, this should be set in environment variables
    KEY_SALT = base64.urlsafe_b64encode(os.urandom(16)).decode()


def derive_key(key: str, salt: str) -> bytes:
    """Derive a cryptographic key from a password using PBKDF2.
    
    Args:
        key: The base key or password
        salt: Salt for key derivation
        
    Returns:
        Derived key as bytes
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits
        salt=salt.encode(),
        iterations=100000,  # High iteration count for security
        backend=default_backend()
    )
    return kdf.derive(key.encode())


def encrypt_payment_data(payment_data: Dict[str, Any]) -> Dict[str, str]:
    """Encrypt sensitive payment data.
    
    Args:
        payment_data: Dictionary containing payment information
        
    Returns:
        Dictionary with encrypted data and metadata
    """
    try:
        # Convert payment data to string
        data_str = str(payment_data)
        
        # Generate a random IV (Initialization Vector)
        iv = os.urandom(16)
        
        # Derive encryption key
        key = derive_key(ENCRYPTION_KEY, KEY_SALT)
        
        # Pad the data
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data_str.encode()) + padder.finalize()
        
        # Create cipher and encrypt
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        
        # Create HMAC for integrity verification
        h = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())
        h.update(encrypted_data)
        hmac_digest = h.finalize()
        
        # Encode binary data to base64 for storage/transmission
        return {
            "encrypted_data": base64.b64encode(encrypted_data).decode(),
            "iv": base64.b64encode(iv).decode(),
            "hmac": base64.b64encode(hmac_digest).decode(),
            "version": "1",  # For future crypto upgrades
        }
    except Exception as e:
        logger.error(f"Error encrypting payment data: {str(e)}")
        raise


def decrypt_payment_data(encrypted_package: Dict[str, str]) -> Dict[str, Any]:
    """Decrypt payment data and verify integrity.
    
    Args:
        encrypted_package: Dictionary with encrypted data and metadata
        
    Returns:
        Original payment data dictionary
    """
    try:
        # Extract components
        encrypted_data = base64.b64decode(encrypted_package["encrypted_data"])
        iv = base64.b64decode(encrypted_package["iv"])
        hmac_digest = base64.b64decode(encrypted_package["hmac"])
        
        # Derive key
        key = derive_key(ENCRYPTION_KEY, KEY_SALT)
        
        # Verify HMAC first (to prevent timing attacks)
        h = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())
        h.update(encrypted_data)
        try:
            h.verify(hmac_digest)
        except Exception:
            logger.error("HMAC verification failed - data may have been tampered with")
            raise ValueError("Payment data integrity check failed")
        
        # Decrypt the data
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
        
        # Unpad the data
        unpadder = padding.PKCS7(128).unpadder()
        data_bytes = unpadder.update(padded_data) + unpadder.finalize()
        
        # Convert back to dictionary
        # Note: Using eval is generally not recommended for security reasons
        # In a production environment, use json.loads or another secure method
        # This is simplified for the example
        import ast
        return ast.literal_eval(data_bytes.decode())
    except Exception as e:
        logger.error(f"Error decrypting payment data: {str(e)}")
        raise


def mask_card_number(card_number: str) -> str:
    """Mask a credit card number for display or logging.
    
    Args:
        card_number: Full credit card number
        
    Returns:
        Masked card number (e.g., "************1234")
    """
    if not card_number or len(card_number) < 4:
        return "****"
    return "*" * (len(card_number) - 4) + card_number[-4:]


def generate_payment_token(payment_data: Dict[str, Any], expiry_minutes: int = 15) -> str:
    """Generate a temporary payment token for secure handling.
    
    Args:
        payment_data: Payment data to tokenize
        expiry_minutes: Token expiry time in minutes
        
    Returns:
        Secure token string
    """
    import time
    import uuid
    
    # Add expiry timestamp and token ID
    tokenized_data = payment_data.copy()
    tokenized_data["token_id"] = str(uuid.uuid4())
    tokenized_data["expires_at"] = int(time.time()) + (expiry_minutes * 60)
    
    # Encrypt the data
    encrypted = encrypt_payment_data(tokenized_data)
    
    # Return a token that includes only the necessary reference
    # In a real implementation, you would store the encrypted data in a secure database
    # and return only a reference token
    return f"pt_{tokenized_data['token_id']}"


def validate_card_number(card_number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm.
    
    Args:
        card_number: Credit card number to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Remove any spaces or dashes
    card_number = card_number.replace(" ", "").replace("-", "")
    
    # Check if the card number contains only digits
    if not card_number.isdigit():
        return False
    
    # Check length (most card types are 13-19 digits)
    if not (13 <= len(card_number) <= 19):
        return False
    
    # Luhn algorithm
    digits = [int(d) for d in card_number]
    checksum = 0
    odd_even = len(digits) % 2
    
    for i, digit in enumerate(digits):
        if ((i + odd_even) % 2) == 0:
            doubled = digit * 2
            checksum += doubled if doubled < 10 else doubled - 9
        else:
            checksum += digit
    
    return checksum % 10 == 0