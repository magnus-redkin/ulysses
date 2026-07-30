from fastapi import Header, HTTPException
from app.config import settings

async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != settings.HOST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key
