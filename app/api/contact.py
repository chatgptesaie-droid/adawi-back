from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from app.services.contact_service import contact_service

router = APIRouter(prefix="/contact", tags=["contact"])

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    message: str

class ContactResponse(BaseModel):
    success: bool
    message: str

@router.post("/", response_model=ContactResponse)
async def send_message(data: ContactRequest):
    await contact_service.save_message(data.name, data.email, data.message)
    return {"success": True, "message": "Message envoyé avec succès !"}
