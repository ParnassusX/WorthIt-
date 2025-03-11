# Setting Up Stripe Webhook

This guide will help you set up a webhook endpoint in your Stripe dashboard to receive payment events for the WorthIt! application.

## Prerequisites

- Stripe account with API keys configured in the `.env` file
- Access to the Stripe Dashboard

## Steps to Set Up Webhook

1. **Log in to your Stripe Dashboard**
   - Go to [https://dashboard.stripe.com/](https://dashboard.stripe.com/)
   - Sign in with your credentials

2. **Navigate to Webhooks**
   - In the left sidebar, click on "Developers"
   - Select "Webhooks"

3. **Add Endpoint**
   - Click "Add endpoint"
   - Enter the following URL as your endpoint:
     ```
     https://worthit-py.netlify.app/stripe-webhook
     ```
   - This URL should match your deployed Netlify site

4. **Select Events**
   - Under "Select events to listen to", choose "Select events"
   - Select the following events:
     - `payment_intent.succeeded`
     - `payment_intent.failed`
     - `subscription.created`
     - `subscription.updated`
     - `subscription.deleted`
   - Click "Add events"

5. **Create Endpoint**
   - Click "Add endpoint" to create the webhook

6. **Get Webhook Secret**
   - After creating the endpoint, you'll see a webhook signing secret
   - Click "Reveal" to view the secret
   - Copy this secret

7. **Add Webhook Secret to Environment Variables**
   - Add the webhook secret to your `.env` file:
     ```
     STRIPE_WEBHOOK_SECRET=your_webhook_secret_here
     ```
   - Also add it to your Netlify environment variables in the Netlify dashboard

## Testing the Webhook

1. **Send a Test Webhook Event**
   - In the Stripe Dashboard, go to the webhook details page
   - Click "Send test webhook"
   - Select an event type (e.g., `payment_intent.succeeded`)
   - Click "Send test webhook"

2. **Verify Receipt**
   - Check your Netlify function logs to verify the webhook was received
   - You should see a log entry with the event details

## Troubleshooting

- If webhooks aren't being received, verify the endpoint URL is correct
- Check that the webhook secret is properly configured in your environment variables
- Ensure the Netlify function has the necessary permissions
- Review the Netlify function logs for any errors

## Next Steps

After setting up the webhook, you can create Stripe Products and Prices to match your subscription tiers:

1. Go to Products in your Stripe Dashboard
2. Create products for each subscription tier (Free, Basic, Premium)
3. Add pricing information that matches your configuration

These products and prices can then be referenced in your payment processing code.