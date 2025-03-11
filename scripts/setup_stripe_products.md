# Setting Up Stripe Products and Prices

This guide will help you set up products and prices in your Stripe dashboard to match the subscription tiers defined in the WorthIt! application.

## Prerequisites

- Stripe account with API keys configured in the `.env` file
- Webhook endpoint already configured (see `setup_stripe_webhook.md`)
- Access to the Stripe Dashboard

## Steps to Set Up Products and Prices

### 1. Log in to your Stripe Dashboard
- Go to [https://dashboard.stripe.com/](https://dashboard.stripe.com/)
- Sign in with your credentials

### 2. Create Products for Each Subscription Tier

#### Basic Tier Product
1. Navigate to Products in your Stripe Dashboard
2. Click "Add Product"
3. Enter the following details:
   - **Name**: Basic Tier
   - **Description**: Advanced product analysis, Increased API calls (1000/day), Priority support, Historical data access
   - **Image**: (Optional) Upload an image representing the Basic tier
4. Under Pricing, add a recurring price:
   - **Price**: $9.99
   - **Billing period**: Monthly
   - **Currency**: USD
5. Click "Save product"
6. Note the Product ID and Price ID for later use

#### Premium Tier Product
1. Click "Add Product"
2. Enter the following details:
   - **Name**: Premium Tier
   - **Description**: Enterprise-level product analysis, Unlimited API calls, 24/7 Premium support, Advanced analytics, Custom integrations
   - **Image**: (Optional) Upload an image representing the Premium tier
3. Under Pricing, add a recurring price:
   - **Price**: $29.99
   - **Billing period**: Monthly
   - **Currency**: USD
4. Click "Save product"
5. Note the Product ID and Price ID for later use

### 3. Update Your Application Code

After creating the products and prices, you'll need to update your application code to reference these IDs. Here's how:

1. Create a configuration file or update your existing one to store the product and price IDs:

```python
# Example configuration in api/payment_config.py

STRIPE_PRODUCTS = {
    SubscriptionTier.BASIC: {
        "product_id": "prod_XXXXXXXXXXXXX",  # Replace with your actual Product ID
        "price_id": "price_XXXXXXXXXXXXX"    # Replace with your actual Price ID
    },
    SubscriptionTier.PREMIUM: {
        "product_id": "prod_XXXXXXXXXXXXX",  # Replace with your actual Product ID
        "price_id": "price_XXXXXXXXXXXXX"    # Replace with your actual Price ID
    }
}
```

2. Update your payment service to use these IDs when creating subscriptions:

```python
# In api/payment_service.py

from api.payment_config import STRIPE_PRODUCTS

# Then in the _create_stripe_subscription method:
checkout_session = stripe.checkout.Session.create(
    customer_email=f"{user_id}@example.com",
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
```

## Testing the Products

1. **Create a Test Checkout Session**
   - Use the Stripe API to create a checkout session with one of your products
   - Open the checkout URL in your browser
   - Complete the checkout process using a test card (e.g., 4242 4242 4242 4242)

2. **Verify Subscription Creation**
   - Check the Stripe Dashboard to verify that a subscription was created
   - Verify that the webhook received the subscription events

## Troubleshooting

- If products aren't appearing in checkout, verify that the product and price IDs are correct
- Ensure that the products are active in your Stripe Dashboard
- Check that the currency matches what your application expects

## Next Steps

After setting up products and prices, you should:

1. Test the complete subscription flow from your application
2. Set up email notifications for subscription events
3. Implement subscription management features in your application