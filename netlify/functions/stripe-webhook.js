/**
 * Netlify serverless function for handling Stripe webhooks
 * 
 * This function processes webhook events from Stripe for payment processing
 * and subscription management.
 */
const stripe = require('stripe')(process.env.STRIPE_API_KEY);

/**
 * Structured logging helper for consistent production monitoring
 */
function logEvent(level, message, context = {}) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    timestamp,
    level,
    message,
    function: 'stripe-webhook',
    ...context
  };
  console.log(JSON.stringify(logEntry));
}

/**
 * Main Stripe webhook handler function
 */
exports.handler = async function(event, context) {
  // Generate request ID for tracing
  const requestId = context.awsRequestId || Math.random().toString(36).substring(2, 15);
  
  // Only allow POST requests
  if (event.httpMethod !== 'POST') {
    logEvent('warn', 'Method not allowed', { requestId, method: event.httpMethod });
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  // Get the signature from the headers
  const signature = event.headers['stripe-signature'];
  if (!signature) {
    logEvent('error', 'Missing Stripe signature', { requestId });
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'Missing Stripe signature' })
    };
  }

  try {
    // Get webhook secret from environment
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
    if (!webhookSecret) {
      logEvent('error', 'Stripe webhook secret not configured', { requestId });
      return {
        statusCode: 500,
        body: JSON.stringify({ error: 'Webhook secret not configured' })
      };
    }

    // Verify the event
    const stripeEvent = stripe.webhooks.constructEvent(
      event.body,
      signature,
      webhookSecret
    );

    logEvent('info', 'Received Stripe webhook', { 
      requestId, 
      eventType: stripeEvent.type,
      eventId: stripeEvent.id
    });

    // Handle different event types
    switch (stripeEvent.type) {
      case 'payment_intent.succeeded':
        await handlePaymentIntentSucceeded(stripeEvent.data.object, requestId);
        break;
      case 'payment_intent.failed':
        await handlePaymentIntentFailed(stripeEvent.data.object, requestId);
        break;
      case 'subscription.created':
      case 'subscription.updated':
      case 'subscription.deleted':
        await handleSubscriptionEvent(stripeEvent.data.object, stripeEvent.type, requestId);
        break;
      default:
        logEvent('info', 'Unhandled event type', { requestId, eventType: stripeEvent.type });
    }

    return {
      statusCode: 200,
      body: JSON.stringify({ received: true })
    };
  } catch (err) {
    logEvent('error', 'Error processing Stripe webhook', { 
      requestId, 
      error: err.message,
      stack: err.stack
    });

    return {
      statusCode: 400,
      body: JSON.stringify({ error: `Webhook Error: ${err.message}` })
    };
  }
};

/**
 * Handle successful payment intent
 */
async function handlePaymentIntentSucceeded(paymentIntent, requestId) {
  logEvent('info', 'Payment succeeded', { 
    requestId, 
    paymentIntentId: paymentIntent.id,
    amount: paymentIntent.amount,
    customer: paymentIntent.customer
  });

  // Here you would update your database, send confirmation emails, etc.
  // For now, we'll just log the event
}

/**
 * Handle failed payment intent
 */
async function handlePaymentIntentFailed(paymentIntent, requestId) {
  logEvent('warn', 'Payment failed', { 
    requestId, 
    paymentIntentId: paymentIntent.id,
    error: paymentIntent.last_payment_error
  });

  // Here you would update your database, send failure notifications, etc.
  // For now, we'll just log the event
}

/**
 * Handle subscription events
 */
async function handleSubscriptionEvent(subscription, eventType, requestId) {
  logEvent('info', 'Subscription event', { 
    requestId, 
    subscriptionId: subscription.id,
    eventType: eventType,
    customer: subscription.customer,
    status: subscription.status
  });

  // Here you would update your database, update user subscription status, etc.
  // For now, we'll just log the event
}