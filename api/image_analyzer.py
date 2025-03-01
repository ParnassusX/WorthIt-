from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import logging
import httpx
from typing import Dict, Any
import io
import base64

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Vision API endpoint for image analysis
VISION_API_URL = "https://api-inference.huggingface.co/models/google/vit-base-patch16-224"

async def extract_product_info_from_image(image_data: bytes) -> Dict[str, Any]:
    """Extract product information from an image using a vision model"""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        logger.warning("No Hugging Face token found. Using mock data for image analysis.")
        # Return mock data for testing
        return {
            "title": "Sample Product from Image",
            "price": "€99.99",
            "description": "This is a sample product detected from an image upload.",
            "reviews": ["Great product", "Works well", "Good value"],
            "url": "https://example.com/product"
        }
    
    # Convert image to base64 for API request
    encoded_image = base64.b64encode(image_data).decode('utf-8')
    
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {"inputs": encoded_image}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(VISION_API_URL, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            
            # Process the vision model response
            # In a real implementation, you would extract product details from the vision model output
            # For now, we'll return mock data
            return {
                "title": "Product Detected in Image",
                "price": "€129.99",
                "description": "This product was detected from your uploaded image. In a production environment, we would extract real product details.",
                "reviews": ["Sample review 1", "Sample review 2"],
                "url": "https://example.com/detected-product"
            }
    except Exception as e:
        logger.error(f"Vision API error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

@router.post("/analyze-image")
async def analyze_image(image: UploadFile = File(...)):
    """Analyze a product from an uploaded image"""
    try:
        # Read the image file
        image_data = await image.read()
        
        if not image_data:
            raise HTTPException(status_code=400, detail="Empty image file")
        
        # Extract product information from the image
        product_data = await extract_product_info_from_image(image_data)
        
        # For now, return mock analysis results
        # In a production environment, you would use the extracted product data
        # to perform a real analysis similar to the URL-based analysis
        return {
            "title": product_data["title"],
            "price": product_data["price"],
            "value_score": 7.5,  # Mock value score
            "sentiment_score": 4.0,  # Mock sentiment score
            "pros": ["Quality construction", "Good features", "Reasonable price"],
            "cons": ["Limited availability", "Some features missing", "Could be improved"],
            "recommendation": "Worth it!",
            "analysis": "Pros:\n- Quality construction\n- Good features\n- Reasonable price\n\nCons:\n- Limited availability\n- Some features missing\n- Could be improved"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in image analysis: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")