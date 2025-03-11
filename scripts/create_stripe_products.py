import os
import stripe
import sys

# Read API key directly from .env file
with open('.env', 'r') as env_file:
    for line in env_file:
        if line.startswith('STRIPE_API_KEY='):
            stripe.api_key = line.split('=', 1)[1].strip()
            break

if not stripe.api_key:
    print("Error: STRIPE_API_KEY environment variable not set.")
    sys.exit(1)

print("Creating Stripe products and prices for WorthIt! subscription tiers...")

try:
    # Create Basic Tier product
    basic_product = stripe.Product.create(
        name="Basic Tier",
        description="Advanced product analysis, Increased API calls (1000/day), Priority support, Historical data access"
    )
    
    # Create price for Basic Tier (9.99 USD monthly)
    basic_price = stripe.Price.create(
        product=basic_product.id,
        unit_amount=999,  # Amount in cents
        currency="usd",
        recurring={"interval": "month"}
    )
    
    print(f"✅ Created Basic Tier product: {basic_product.id}")
    print(f"✅ Created Basic Tier price: {basic_price.id}")
    
    # Create Premium Tier product
    premium_product = stripe.Product.create(
        name="Premium Tier",
        description="Enterprise-level product analysis, Unlimited API calls, 24/7 Premium support, Advanced analytics, Custom integrations"
    )
    
    # Create price for Premium Tier (29.99 USD monthly)
    premium_price = stripe.Price.create(
        product=premium_product.id,
        unit_amount=2999,  # Amount in cents
        currency="usd",
        recurring={"interval": "month"}
    )
    
    print(f"✅ Created Premium Tier product: {premium_product.id}")
    print(f"✅ Created Premium Tier price: {premium_price.id}")
    
    # Print configuration for payment_config.py
    print("\nAdd the following to your payment_config.py file:")
    print("""\nSTRIPE_PRODUCTS = {
    SubscriptionTier.BASIC: {
        "product_id": "%s",
        "price_id": "%s"
    },
    SubscriptionTier.PREMIUM: {
        "product_id": "%s",
        "price_id": "%s"
    }
}""" % (basic_product.id, basic_price.id, premium_product.id, premium_price.id))
    
except stripe.error.StripeError as e:
    print(f"Error creating Stripe products: {e}")
    sys.exit(1)

print("\nDone! Your Stripe products and prices have been created successfully.")