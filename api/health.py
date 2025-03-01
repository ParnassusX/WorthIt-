from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring deployment status"""
    return {"status": "ok", "service": "WorthIt! API", "version": "1.0.0"}