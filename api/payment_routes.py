"""Payment routes for handling payment processing and subscription management."""

from fastapi import APIRouter, Depends, Header, Request, HTTPException, Body
from typing import Dict, Optional, Any

from api.payment_config import SubscriptionTier, PaymentProvider
from api.payment_service import PaymentService
from api.auth import get_current_user

# Create router
payment_router = APIRouter(prefix="/payment", tags=["payment"])


@payment_router.post("/subscription/create")
async def create_subscription(
    tier: SubscriptionTier = Body(...),
    provider: PaymentProvider = Body(PaymentProvider.STRIPE),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Create a subscription for the current user.
    
    Args:
        tier: The subscription tier.
        provider: The payment provider to use.
        current_user: The current user, injected by dependency.
        
    Returns:
        Dict containing subscription details and payment URL.
    """
    try:
        user_id = current_user["id"]
        result = await PaymentService.create_subscription(user_id, tier, provider)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating subscription: {str(e)}")


@payment_router.post("/subscription/cancel")
async def cancel_subscription(
    subscription_id: str = Body(...),
    provider: PaymentProvider = Body(PaymentProvider.STRIPE),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Cancel a subscription.
    
    Args:
        subscription_id: The ID of the subscription to cancel.
        provider: The payment provider.
        current_user: The current user, injected by dependency.
        
    Returns:
        Dict containing cancellation details.
    """
    try:
        # In a real implementation, you would verify that the subscription belongs to the user
        result = await PaymentService.cancel_subscription(subscription_id, provider)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling subscription: {str(e)}")


@payment_router.post("/webhook/{provider}")
async def payment_webhook(
    request: Request,
    provider: PaymentProvider,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")
) -> Dict[str, Any]:
    """Handle webhooks from payment providers.
    
    Args:
        request: The request object.
        provider: The payment provider.
        stripe_signature: The Stripe signature header for webhook verification.
        
    Returns:
        Dict containing webhook processing result.
    """
    try:
        # Get the raw payload
        payload = await request.json()
        
        # Process the webhook
        result = await PaymentService.process_webhook(provider, payload, stripe_signature)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing webhook: {str(e)}")