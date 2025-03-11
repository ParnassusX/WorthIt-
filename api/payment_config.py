"""Payment configuration and pricing tiers for WorthIt!"""

from enum import Enum
from typing import Dict, List

class SubscriptionTier(Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"

class PaymentProvider(Enum):
    STRIPE = "stripe"
    PAYPAL = "paypal"

PRICING_TIERS: Dict[SubscriptionTier, Dict] = {
    SubscriptionTier.FREE: {
        "name": "Free Tier",
        "price_monthly": 0,
        "features": [
            "Basic product analysis",
            "Limited API calls (100/day)",
            "Standard support"
        ],
        "api_rate_limit": 100,
        "concurrent_requests": 2
    },
    SubscriptionTier.BASIC: {
        "name": "Basic Tier",
        "price_monthly": 9.99,
        "features": [
            "Advanced product analysis",
            "Increased API calls (1000/day)",
            "Priority support",
            "Historical data access"
        ],
        "api_rate_limit": 1000,
        "concurrent_requests": 5
    },
    SubscriptionTier.PREMIUM: {
        "name": "Premium Tier",
        "price_monthly": 29.99,
        "features": [
            "Enterprise-level product analysis",
            "Unlimited API calls",
            "24/7 Premium support",
            "Advanced analytics",
            "Custom integrations"
        ],
        "api_rate_limit": float('inf'),
        "concurrent_requests": 10
    }
}

PAYMENT_PROVIDERS_CONFIG = {
    PaymentProvider.STRIPE: {
        "api_version": "2023-10-16",
        "webhook_events": [
            "payment_intent.succeeded",
            "payment_intent.failed",
            "subscription.created",
            "subscription.updated",
            "subscription.deleted"
        ]
    },
    PaymentProvider.PAYPAL: {
        "api_version": "v2",
        "webhook_events": [
            "PAYMENT.CAPTURE.COMPLETED",
            "PAYMENT.CAPTURE.DENIED",
            "BILLING.SUBSCRIPTION.CREATED",
            "BILLING.SUBSCRIPTION.CANCELLED"
        ]
    }
}

# Stripe product and price IDs for subscription tiers
# Updated using scripts/cleanup_duplicate_stripe_products.py
STRIPE_PRODUCTS = {
    SubscriptionTier.BASIC: {
        "product_id": "prod_RvSSzOwZJs0I3Q",
        "price_id": "price_1R1bXVCaW54VekBC0AGZOHgy"
    },
    SubscriptionTier.PREMIUM: {
        "product_id": "prod_RvSS3Xv780xsJC",
        "price_id": "price_1R1bXWCaW54VekBCmE6x1pdp"
    }
}

def get_tier_features(tier: SubscriptionTier) -> List[str]:
    """Get the features for a specific subscription tier."""
    return PRICING_TIERS[tier]["features"]

def get_tier_rate_limit(tier: SubscriptionTier) -> float:
    """Get the API rate limit for a specific subscription tier."""
    return PRICING_TIERS[tier]["api_rate_limit"]

def get_tier_price(tier: SubscriptionTier) -> float:
    """Get the monthly price for a specific subscription tier."""
    return PRICING_TIERS[tier]["price_monthly"]