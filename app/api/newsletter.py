from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.services.newsletter_service import newsletter_service

router = APIRouter(prefix="/newsletter", tags=["newsletter"])

class SubscribeRequest(BaseModel):
    name: str
    email: EmailStr

class SubscribeResponse(BaseModel):
    success: bool
    message: str

@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(data: SubscribeRequest):
    ok = await newsletter_service.subscribe(data.name, data.email)
    if ok:
        return {"success": True, "message": "Inscription réussie !"}
    else:
        return {"success": False, "message": "Cet email est déjà inscrit."} 