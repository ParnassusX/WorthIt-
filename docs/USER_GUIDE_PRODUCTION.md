# WorthIt! User Guide - Production Version

## Introduction
Welcome to WorthIt! - your intelligent shopping assistant that helps you determine if a product is worth the price. This guide will help you get started with using WorthIt! and troubleshoot common issues in the production environment.

## Getting Started

### Accessing WorthIt!
You can access WorthIt! through:

1. **Telegram Bot**: Search for `@WorthItValueBot` on Telegram
2. **Web App**: Visit [https://worthit-app.netlify.app](https://worthit-app.netlify.app)
3. **API**: For developers, access our API at [https://worthit-app.netlify.app/api](https://worthit-app.netlify.app/api)

### Basic Usage

#### Using the Telegram Bot
1. Start a chat with `@WorthItValueBot`
2. Send a product URL from Amazon or eBay
3. Wait for the analysis to complete
4. Review the value assessment and recommendation

#### Using the Web App
1. Navigate to [https://worthit-app.netlify.app](https://worthit-app.netlify.app)
2. Paste a product URL in the analysis box
3. Click "Analyze"
4. View the detailed product analysis

## Features

### Product Analysis
WorthIt! analyzes products based on:
- Price comparison with similar products
- Review sentiment analysis
- Quality-to-price ratio assessment
- Historical price tracking

### Value Score
Each product receives a Value Score from 0-10:
- **8-10**: Excellent value - highly recommended purchase
- **6-7**: Good value - recommended purchase
- **4-5**: Average value - consider alternatives
- **0-3**: Poor value - not recommended

### Subscription Tiers

#### Free Tier
- Basic product analysis
- Limited to 100 API calls per day
- Standard support

#### Basic Tier ($9.99/month)
- Advanced product analysis
- 1,000 API calls per day
- Priority support
- Historical data access

#### Premium Tier ($29.99/month)
- Enterprise-level product analysis
- Unlimited API calls
- 24/7 Premium support
- Advanced analytics
- Custom integrations

## Troubleshooting Guide

### Common Issues

#### "URL Not Supported" Error
**Problem**: You receive an error stating the URL is not supported.

**Solution**:
- Ensure you're using a product URL from Amazon or eBay
- Check that the URL is complete and valid
- Try copying the URL directly from your browser's address bar
- Make sure the URL format matches: `https://www.amazon.com/dp/PRODUCTID` or `https://www.ebay.com/itm/ITEMID`

#### Analysis Takes Too Long
**Problem**: Your analysis request seems to be taking too long.

**Solution**:
- Check your internet connection
- Try a different product URL
- If using the Telegram bot, start a new conversation with /start
- If the issue persists, try again later as the service might be experiencing high demand
- For persistent issues, contact support at support@worthit-app.netlify.app

#### Incorrect Product Information
**Problem**: The analysis shows incorrect product information.

**Solution**:
- Verify you've submitted the correct URL
- Try refreshing the product page and copying the URL again
- Report the issue through the "Report Issue" button in the web app
- Include details about what information is incorrect to help us improve

#### Payment Issues
**Problem**: You're experiencing issues with subscription payments.

**Solution**:
- Verify your payment method is valid and has sufficient funds
- Check that your billing information is correct
- Try a different payment method if available
- Clear your browser cache and cookies before attempting payment again
- Contact support at support@worthit-app.netlify.app for assistance

#### Account Access Problems
**Problem**: You cannot access your account or subscription features.

**Solution**:
- Verify you're using the correct login credentials
- Try resetting your password
- Clear browser cookies and cache
- Check if your subscription is active in the account settings
- Contact support with your account details for assistance

### Error Codes

WorthIt! may display error codes to help diagnose issues:

- **E001**: Invalid URL format
- **E002**: Unsupported retailer
- **E003**: Product not found
- **E004**: Analysis service unavailable
- **E005**: Rate limit exceeded
- **E006**: Authentication failure
- **E007**: Subscription expired
- **E008**: Payment processing error

If you encounter any of these error codes, please include them when contacting support.

## Security Information

### Payment Security
All payment information is securely processed using industry-standard encryption. WorthIt! never stores your complete credit card information. Payments are processed through Stripe, a PCI-compliant payment processor.

### Data Privacy
WorthIt! values your privacy:
- We only collect data necessary to provide our service
- Product analysis data is anonymized
- Personal information is never shared with third parties
- You can request deletion of your data at any time

## Contact Support

If you need assistance with WorthIt!, contact our support team:

- **Email**: support@worthit-app.netlify.app
- **Telegram**: Send a message to @WorthItSupport
- **Web**: Use the contact form at [https://worthit-app.netlify.app/support](https://worthit-app.netlify.app/support)

Our support team is available Monday-Friday, 9am-5pm EST. Premium subscribers have access to 24/7 support.

## FAQ

### General Questions

**Q: How accurate is the Value Score?**
A: The Value Score is based on multiple factors including price comparison, review sentiment, and historical pricing. While we strive for accuracy, the score should be used as a guideline rather than an absolute determination.

**Q: Which retailers are supported?**
A: Currently, WorthIt! supports Amazon and eBay. We're working to add more retailers in the future.

**Q: Is my data secure?**
A: Yes, we use industry-standard security practices to protect your data. All communications are encrypted using HTTPS, and we never share your personal information with third parties.

**Q: Can I use WorthIt! on mobile devices?**
A: Yes, WorthIt! is fully responsive and works on mobile browsers. You can also use our Telegram bot on any device with Telegram installed.

**Q: How do I cancel my subscription?**
A: You can cancel your subscription at any time from your account settings page. Your subscription will remain active until the end of the current billing period.

## Updates and Changes

WorthIt! is constantly improving. Check our blog at [https://worthit-app.netlify.app/blog](https://worthit-app.netlify.app/blog) for the latest updates and feature announcements.