from app.db.mongo import db
from datetime import datetime
from app.models.contact import ContactMessage
from app.services.email_service import send_status_email

ADMIN_EMAIL = "marcusgigoh@gmail.com"

class ContactService:
    def __init__(self):
        self.collection = db.contact_messages

    async def save_message(self, name: str, email: str, message: str):
        msg = {
            "name": name,
            "email": email,
            "message": message,
            "sent_at": datetime.utcnow()
        }
        await self.collection.insert_one(msg)
        # Envoi d'email à l'admin
        subject = f"Nouveau message de contact de {name}"
        body = f"Nom: {name}\nEmail: {email}\nMessage:\n{message}"
        await send_status_email(ADMIN_EMAIL, subject, body)
        return True

contact_service = ContactService()
