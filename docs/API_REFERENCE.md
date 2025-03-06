# WorthIt! API Reference

## Overview
This document provides detailed information about the WorthIt! API endpoints, their parameters, and expected responses.

## Base URL
The API is hosted on Vercel. The base URL is:
```
https://worthit-py.netlify.app/api
```
This is the base URL for the WorthIt! API endpoints.

## Authentication
The API requires two authentication tokens:
- `APIFY_TOKEN`: For web scraping functionality
- `HF_TOKEN`: For machine learning model access

These should be set as environment variables on your deployment platform.

### Testing Authentication
For testing purposes, use the `.env.test` file with mock tokens. The test suite uses `TestClient` and `AsyncClient` from FastAPI's testing utilities to simulate authenticated requests.

## Endpoints

### Product Analysis
#### POST /analyze
Analyzes a product URL and returns detailed value assessment.

**Parameters:**
```json
{
    "url": "string (required) - Product URL from Amazon or eBay"
}
```

**Response:**
```json
{
    "title": "string - Product title",
    "price": "string - Current price",
    "value_score": "number (0-10) - Overall value score",
    "recommendation": "string - Purchase recommendation",
    "pros": ["string[] - List of product strengths"],
    "cons": ["string[] - List of product weaknesses"],
    "url": "string - Original product URL"
}
```

**Error Responses:**
- 400: Invalid product URL
- 401: API authentication error
- 503: Service temporarily unavailable
- 504: Analysis timeout

### Health Check
#### GET /health
Returns API health status.

**Response:**
```json
{
    "status": "string - Service status (ok/error)",
    "service": "string - Service name",
    "version": "string - API version"
}
```

## Rate Limits
- Maximum 100 requests per hour per IP
- Analysis endpoint timeout: 30 seconds

## Error Handling
All errors follow this format:
```json
{
    "detail": "string - Error description",
    "status_code": "number - HTTP status code"
}
```

## Best Practices
1. Always handle timeout errors gracefully
2. Implement exponential backoff for retries
3. Cache analysis results when possible
4. Validate URLs before sending to API

## Support
For API support or to report issues, please open a GitHub issue in the repository.