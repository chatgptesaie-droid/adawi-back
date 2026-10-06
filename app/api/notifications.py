from fastapi import APIRouter, Depends
from app.services.notification_service import notification_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
from typing import List
from app.models.notification import Notification
from pydantic import BaseModel

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("/", response_model=List[Notification])
async def get_notifications(current_user: UserPublic = Depends(get_current_user)):
    if current_user.role in ["admin", "vendeur"]:
        user_id = "staff"
    else:
        user_id = current_user.id
    return await notification_service.get_notifications(user_id)

class MessageResponse(BaseModel):
    message: str

@router.post("/mark_read/{notif_id}", response_model=MessageResponse)
async def mark_notification_read(notif_id: str, current_user: UserPublic = Depends(get_current_user)):
    await notification_service.mark_as_read(notif_id)
    return {"message": "Notification marquée comme lue"}

@router.get("/{notif_id}/details", response_model=Notification)
async def get_notification_details(notif_id: str, current_user: UserPublic = Depends(get_current_user)):
    """Récupérer les détails d'une notification et la marquer automatiquement comme lue"""
    if current_user.role in ["admin", "vendeur"]:
        user_id = "staff"
    else:
        user_id = current_user.id

    notification = await notification_service.get_notification_details(notif_id, user_id)
    if not notification:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Notification non trouvée")

    return notification
