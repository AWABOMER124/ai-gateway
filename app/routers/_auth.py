import os
from fastapi import Header, HTTPException, status


async def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    expected = os.getenv("GATEWAY_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="GATEWAY_API_KEY not configured on server")
    if x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
