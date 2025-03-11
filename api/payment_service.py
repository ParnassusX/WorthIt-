"""Payment service for handling payment processing and subscription management."""

import logging
import os
from typing import Dict, Optional, Tuple, Any

import stripe
from fastapi import HTTPException

from api.payment_config import SubscriptionTier, PaymentProvider, PRICING_TIERS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize payment providers
try:
    # Initialize Stripe
    stripe.api_key = os.getenv("STRIPE_API_KEY", "")
    if not stripe.api_key:
        logger.warning("STRIPE_API_KEY not set. Stripe payments will not work.")
        
    # PayPal would be initialized here
    # paypal_client_id = os.getenv("PAYPAL_CLIENT_ID", "")
    # paypal_client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    # if not paypal_client_id or not paypal_client_secret:
    #     logger.warning("PayPal credentials not set. PayPal payments will not work.")
    
except Exception as e:
    logger.error(f"Error initializing payment providers: {str(e)}")


class PaymentService:
    """Service for handling payment processing and subscription management."""
    
    @staticmethod
    async def create_subscription(user_id: str, tier: SubscriptionTier, 
                               provider: PaymentProvider = PaymentProvider.STRIPE) -> Dict[str, Any]:
        """Create a subscription for a user.
        
        Args:
            user_id: The ID of the user.
            tier: The subscription tier.
            provider: The payment provider to use.
            
        Returns:
            Dict containing subscription details and payment URL.
            
        Raises:
            HTTPException: If there's an error creating the subscription.
        """
        try:
            if provider == PaymentProvider.STRIPE:
                return await PaymentService._create_stripe_subscription(user_id, tier)
            elif provider == PaymentProvider.PAYPAL:
                return await PaymentService._create_paypal_subscription(user_id, tier)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported payment provider: {provider}")
        except Exception as e:
            logger.error(f"Error creating subscription: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error creating subscription: {str(e)}")
    
    @staticmethod
    async def _create_stripe_subscription(user_id: str, tier: SubscriptionTier) -> Dict[str, Any]:
        """Create a Stripe subscription."""
        try:
            if not stripe.api_key:
                raise ValueError("Stripe API key not configured")
                
            # Get price information for the tier
            price_monthly = PRICING_TIERS[tier]["price_monthly"]
            
            # In a real implementation, you would:
            # 1. Create or get a customer
            # 2. Create a subscription with the appropriate price ID
            # 3. Return the checkout URL
            
            # Use the Stripe product IDs from configuration
            from api.payment_config import STRIPE_PRODUCTS
            
            # Check if we have product IDs configured
            if tier in STRIPE_PRODUCTS and STRIPE_PRODUCTS[tier]["price_id"] != "price_placeholder":
                # Use the configured price ID
                checkout_session = stripe.checkout.Session.create(
                    customer_email=f"{user_id}@example.com",  # In real app, get from user profile
                    payment_method_types=["card"],
                    line_items=[{
                        "price": STRIPE_PRODUCTS[tier]["price_id"],
                        "quantity": 1
                    }],
                    mode="subscription",
                    success_url="https://worthit-app.netlify.app/subscription/success",
                    cancel_url="https://worthit-app.netlify.app/subscription/cancel",
                    metadata={
                        "user_id": user_id,
                        "tier": tier.value
                    }
                )
            else:
                # Fall back to dynamic price creation if product IDs aren't configured
                checkout_session = stripe.checkout.Session.create(
                    customer_email=f"{user_id}@example.com",  # In real app, get from user profile
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": PRICING_TIERS[tier]["name"],
                                "description": ", ".join(PRICING_TIERS[tier]["features"])
                            },
                            "unit_amount": int(price_monthly * 100),  # Convert to cents
                            "recurring": {
                                "interval": "month"
                            }
                        },
                        "quantity": 1
                    }],
                    mode="subscription",
                    success_url="https://worthit-app.netlify.app/subscription/success",
                    cancel_url="https://worthit-app.netlify.app/subscription/cancel",
                    metadata={
                        "user_id": user_id,
                        "tier": tier.value
                    }
                )
            
            
            return {
                "subscription_id": checkout_session.id,
                "payment_url": checkout_session.url,
                "tier": tier.value,
                "provider": PaymentProvider.STRIPE.value
            }
            
        except Exception as e:
            logger.error(f"Stripe subscription error: {str(e)}")
            raise
    
    @staticmethod
    async def _create_paypal_subscription(user_id: str, tier: SubscriptionTier) -> Dict[str, Any]:
        """Create a PayPal subscription."""
        # This would be implemented with PayPal SDK
        raise NotImplementedError("PayPal integration not implemented yet")
    
    @staticmethod
    async def cancel_subscription(subscription_id: str, provider: PaymentProvider) -> Dict[str, Any]:
        """Cancel a subscription."""
        try:
            if provider == PaymentProvider.STRIPE:
                return await PaymentService._cancel_stripe_subscription(subscription_id)
            elif provider == PaymentProvider.PAYPAL:
                return await PaymentService._cancel_paypal_subscription(subscription_id)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported payment provider: {provider}")
        except Exception as e:
            logger.error(f"Error cancelling subscription: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error cancelling subscription: {str(e)}")
    
    @staticmethod
    async def _cancel_stripe_subscription(subscription_id: str) -> Dict[str, Any]:
        """Cancel a Stripe subscription."""
        try:
            if not stripe.api_key:
                raise ValueError("Stripe API key not configured")
                
            # In a real implementation, you would cancel the actual subscription
            # This is a simplified example
            cancelled_subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
            
            return {
                "subscription_id": subscription_id,
                "status": cancelled_subscription.status,
                "cancelled_at": cancelled_subscription.canceled_at,
                "provider": PaymentProvider.STRIPE.value
            }
            
        except Exception as e:
            logger.error(f"Stripe cancellation error: {str(e)}")
            raise
    
    @staticmethod
    async def _cancel_paypal_subscription(subscription_id: str) -> Dict[str, Any]:
        """Cancel a PayPal subscription."""
        # This would be implemented with PayPal SDK
        raise NotImplementedError("PayPal integration not implemented yet")
    
    @staticmethod
    async def process_webhook(provider: PaymentProvider, payload: Dict[str, Any], 
                            signature: Optional[str] = None) -> Dict[str, Any]:
        """Process a webhook from a payment provider."""
        try:
            if provider == PaymentProvider.STRIPE:
                return await PaymentService._process_stripe_webhook(payload, signature)
            elif provider == PaymentProvider.PAYPAL:
                return await PaymentService._process_paypal_webhook(payload)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported payment provider: {provider}")
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing webhook: {str(e)}")
    
    @staticmethod
    async def _process_stripe_webhook(payload: Dict[str, Any], signature: Optional[str]) -> Dict[str, Any]:
        """Process a Stripe webhook."""
        try:
            if not stripe.api_key:
                raise ValueError("Stripe API key not configured")
                
            webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
            if not webhook_secret:
                logger.warning("STRIPE_WEBHOOK_SECRET not set. Webhook signature verification will be skipped.")
            
            if webhook_secret and signature:
                # Verify webhook signature
                event = stripe.Webhook.construct_event(
                    payload=payload,
                    sig_header=signature,
                    secret=webhook_secret
                )
            else:
                # Skip signature verification (not recommended for production)
                event = payload
            
            # Handle different event types
            event_type = event.get("type")
            if event_type == "payment_intent.succeeded":
                # Handle successful payment
                payment_intent = event.get("data", {}).get("object", {})
                return {
                    "status": "success",
                    "event_type": event_type,
                    "payment_intent_id": payment_intent.get("id"),
                    "amount": payment_intent.get("amount"),
                    "customer": payment_intent.get("customer")
                }
            elif event_type == "payment_intent.failed":
                # Handle failed payment
                payment_intent = event.get("data", {}).get("object", {})
                return {
                    "status": "failed",
                    "event_type": event_type,
                    "payment_intent_id": payment_intent.get("id"),
                    "error": payment_intent.get("last_payment_error", {})
                }
            elif event_type in ["subscription.created", "subscription.updated", "subscription.deleted"]:
                # Handle subscription events
                subscription = event.get("data", {}).get("object", {})
                return {
                    "status": "success",
                    "event_type": event_type,
                    "subscription_id": subscription.get("id"),
                    "customer": subscription.get("customer"),
                    "status": subscription.get("status")
                }
            else:
                # Handle other events
                return {
                    "status": "ignored",
                    "event_type": event_type
                }
                
        except Exception as e:
            logger.error(f"Stripe webhook error: {str(e)}")
            raise
    
    @staticmethod
    async def _process_paypal_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a PayPal webhook."""
        # This would be implemented with PayPal SDK
        raise NotImplementedError("PayPal webhook processing not implemented yet")