from fastapi import APIRouter, HTTPException, Depends
from app.models.dashboard import AdminDashboardResponse, VendorDashboardResponse
from app.services.dashboard_service_fixed import dashboard_service_fixed as dashboard_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
import aiosmtplib
from email.message import EmailMessage
from smtplib import SMTPException
from app.core.config import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/admin", response_model=AdminDashboardResponse)
async def get_admin_dashboard(current_user: UserPublic = Depends(get_current_user)):
    """Dashboard admin - Statistiques globales de la plateforme"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    return await dashboard_service.get_admin_dashboard() 

@router.get("/vendeur", response_model=VendorDashboardResponse)
async def get_vendor_dashboard(current_user: UserPublic = Depends(get_current_user)):
    """Dashboard vendeur - Statistiques spécifiques au vendeur connecté"""
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux vendeurs et administrateurs")

    return await dashboard_service.get_vendor_dashboard(current_user.id)

@router.get("/client")
async def get_client_dashboard(current_user: UserPublic = Depends(get_current_user)):
    """Dashboard client - Mesures et photo du profil"""
    if current_user.role != "client":
        raise HTTPException(status_code=403, detail="Accès réservé aux clients")

    return await dashboard_service.get_client_dashboard(current_user.id)

async def send_status_email(to_email, subject, body):
    message = EmailMessage()
    message["From"] = settings.SMTP_USER
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            use_tls=settings.SMTP_PORT == 465,
            start_tls=settings.SMTP_PORT == 587,
        )
    except SMTPException as e:
        print(f"Erreur SMTP lors de l'envoi de l'email: {e}")
