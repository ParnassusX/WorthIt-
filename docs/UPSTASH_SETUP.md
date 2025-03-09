# Upstash Redis Setup Guide for WorthIt!

## Overview
WorthIt! uses Upstash Redis for its serverless-compatible caching and data storage needs. This guide explains how to set up and configure Upstash Redis for the project.

## Why Upstash Redis?
- **Serverless-First**: Built specifically for serverless environments like Netlify
- **Global Database**: Automatic replication across regions for low latency
- **Simple Integration**: Direct integration with Netlify and other platforms
- **REST API Support**: HTTP-based access when TCP connections are problematic

## Setup Instructions

### 1. Create Upstash Account & Database
1. Go to [Upstash Console](https://console.upstash.com/)
2. Sign up or log in
3. Click "Create Database"
4. Choose the region closest to your Netlify deployment
5. Select your preferred plan (Free tier is sufficient for development)

### 2. Get Connection Details
From your Upstash database dashboard:
1. Find the "Connect to your database" section
2. Copy the Redis connection string (UPSTASH_REDIS_URL)

### 3. Update Environment Variables
Update your .env and .env.test files with the Upstash connection string:

```env
# Replace the existing REDIS_URL with:
REDIS_URL=your_upstash_redis_url_here
```

### 4. Verify Connection
Run the Redis diagnostics tool to verify the connection:
```bash
python tools/redis_diagnostics.py
```

## Connection String Format
Upstash Redis uses the following connection string format:
```
redis://default:REDIS_PASSWORD@REDIS_ENDPOINT:PORT
```

## Best Practices
1. **Environment Variables**: Always use environment variables for the connection string
2. **Connection Pooling**: Not required for Upstash - it handles connection management
3. **Error Handling**: Implement retry logic for temporary connection issues
4. **Monitoring**: Use Upstash dashboard to monitor usage and performance

## Troubleshooting

### Common Issues
1. **Connection Timeout**
   - Check if the Redis URL is correct
   - Verify network connectivity
   - Ensure your IP is not blocked

2. **Authentication Failed**
   - Verify the password in the connection string
   - Check if the database is active

3. **High Latency**
   - Choose a closer region for your database
   - Consider upgrading to a paid plan for better performance

### Getting Help
- Check [Upstash Documentation](https://docs.upstash.com/)
- Visit [Upstash Discord](https://discord.upstash.com/) for community support
- Contact Upstash support for critical issues

## Migration from Redis Cloud
If you're migrating from Redis Cloud:
1. Export your data from Redis Cloud if needed
2. Create a new Upstash database
3. Update environment variables with new connection string
4. Test thoroughly before switching production traffic

## Security Considerations
1. Keep your connection string secure
2. Use environment variables for credentials
3. Rotate passwords periodically
4. Monitor database access logs

## Next Steps
1. Set up monitoring and alerts
2. Configure backup strategy
3. Document any specific usage patterns
4. Train team members on Upstash dashboard