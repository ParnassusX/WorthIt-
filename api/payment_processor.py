"""Secure Payment Processing Module for WorthIt!

This module implements secure payment processing with encryption and fraud detection.
It provides functionality to securely process payments, encrypt sensitive payment data,
and detect potentially fraudulent transactions.
"""

import logging
import os
from typing import Dict, Any, Optional, Tuple
import time
from datetime import datetime

import stripe
from fastapi import HTTPException

from api.payment_encryption import encrypt_payment_data, decrypt_payment_data
from api.fraud_detection import FraudDetector
from api.payment_config import PaymentProvider, SubscriptionTier

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize fraud detector
fraud_detector = FraudDetector()

class PaymentProcessor:
    """Secure payment processor with encryption and fraud detection."""
    
    def __init__(self):
        """Initialize the payment processor."""
        # Initialize payment providers
        self._init_payment_providers()
        
        # Transaction log for auditing
        self.transaction_log = []
        self.max_log_entries = 1000
        
    def _init_payment_providers(self):
        """Initialize payment provider clients."""
        # Initialize Stripe
        stripe_key = os.getenv("STRIPE_API_KEY", "")
        if not stripe_key:
            logger.warning("STRIPE_API_KEY not set. Stripe payments will not work.")
        else:
            stripe.api_key = stripe_key
            logger.info("Stripe payment provider initialized")
        
        # Initialize encryption and fraud detection
        self.encryption_enabled = True
        self.fraud_detection_enabled = True
        logger.info("Payment encryption and fraud detection enabled")
        
        # Additional payment providers would be initialized here
        # e.g., PayPal, Square, etc.
    
    async def process_payment(self, payment_data: Dict[str, Any], user_id: str, 
                           ip_address: str) -> Dict[str, Any]:
        """Process a payment securely.
        
        Args:
            payment_data: Payment details including amount, card info, etc.
            user_id: ID of the user making the payment
            ip_address: IP address of the user
            
        Returns:
            Dictionary with payment result
            
        Raises:
            HTTPException: If payment processing fails or fraud is detected
        """
        try:
            # Step 1: Fraud detection
            is_fraudulent, risk_score, fraud_reason = await self._check_for_fraud(
                payment_data, user_id, ip_address)
            
            if is_fraudulent:
                logger.warning(f"Fraudulent payment attempt detected: {fraud_reason}")
                self._log_transaction(payment_data, user_id, "rejected", fraud_reason)
                raise HTTPException(status_code=403, 
                                   detail="Payment rejected due to security concerns")
            
            # Step 2: Encrypt sensitive payment data
            encrypted_data = encrypt_payment_data(payment_data)
            
            # Step 3: Process payment with appropriate provider
            provider = payment_data.get("provider", PaymentProvider.STRIPE)
            result = await self._process_with_provider(provider, payment_data, encrypted_data)
            
            # Step 4: Log successful transaction
            self._log_transaction(payment_data, user_id, "completed")
            
            return result
            
        except Exception as e:
            logger.error(f"Payment processing error: {str(e)}")
            self._log_transaction(payment_data, user_id, "failed", str(e))
            raise HTTPException(status_code=500, 
                               detail="Payment processing failed. Please try again later.")
    
    async def _check_for_fraud(self, payment_data: Dict[str, Any], user_id: str, 
                            ip_address: str) -> Tuple[bool, float, Optional[str]]:
        """Check for potential fraud in the payment.
        
        Args:
            payment_data: Payment details
            user_id: ID of the user
            ip_address: IP address of the user
            
        Returns:
            Tuple of (is_fraudulent, risk_score, reason)
        """
        return await fraud_detector.analyze_transaction(payment_data, user_id, ip_address)
    
    async def _process_with_provider(self, provider: str, payment_data: Dict[str, Any], 
                                  encrypted_data: Dict[str, str]) -> Dict[str, Any]:
        """Process payment with the specified provider.
        
        Args:
            provider: Payment provider name
            payment_data: Original payment data
            encrypted_data: Encrypted sensitive data
            
        Returns:
            Dictionary with payment result
        """
        if provider == PaymentProvider.STRIPE:
            return await self._process_stripe_payment(payment_data, encrypted_data)
        # Add other providers as needed
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported payment provider: {provider}")
    
    async def _process_stripe_payment(self, payment_data: Dict[str, Any], 
                                   encrypted_data: Dict[str, str]) -> Dict[str, Any]:
        """Process payment with Stripe.
        
        Args:
            payment_data: Original payment data
            encrypted_data: Encrypted sensitive data
            
        Returns:
            Dictionary with payment result
        """
        try:
            # Create a payment intent with Stripe
            amount = int(float(payment_data.get("amount", 0)) * 100)  # Convert to cents
            currency = payment_data.get("currency", "usd")
            payment_method = payment_data.get("payment_method_id")
            
            if not payment_method:
                raise ValueError("Payment method ID is required")
            
            # Create the payment intent
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                confirm=True,
                return_url=payment_data.get("return_url"),
                metadata={
                    "encrypted_data_ref": encrypted_data.get("version", "1"),
                    "user_id": payment_data.get("user_id", "anonymous")
                }
            )
            
            return {
                "success": True,
                "provider": "stripe",
                "payment_id": intent.id,
                "status": intent.status,
                "amount": amount / 100,  # Convert back to dollars
                "currency": currency,
                "timestamp": datetime.now().isoformat()
            }
            
        except stripe.error.CardError as e:
            # Card was declined
            logger.warning(f"Card declined: {str(e)}")
            return {
                "success": False,
                "provider": "stripe",
                "error": "card_declined",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Stripe payment error: {str(e)}")
            raise
    
    def _log_transaction(self, payment_data: Dict[str, Any], user_id: str, 
                        status: str, error: str = None):
        """Log a payment transaction for auditing.
        
        Args:
            payment_data: Payment details
            user_id: ID of the user
            status: Transaction status (completed, failed, rejected)
            error: Optional error message
        """
        # Create sanitized log entry (no sensitive data)
        log_entry = {
            "user_id": user_id,
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "usd"),
            "provider": payment_data.get("provider", "unknown"),
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        if error:
            log_entry["error"] = error
            
        # Add to transaction log
        self.transaction_log.append(log_entry)
        
        # Trim log if it gets too large
        if len(self.transaction_log) > self.max_log_entries:
            self.transaction_log = self.transaction_log[-self.max_log_entries:]

# Singleton instance for application-wide use
_processor_instance = None

def get_payment_processor() -> PaymentProcessor:
    """Get the singleton instance of PaymentProcessor.
    
    Returns:
        The PaymentProcessor instance
    """
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = PaymentProcessor()
    return _processor_instance