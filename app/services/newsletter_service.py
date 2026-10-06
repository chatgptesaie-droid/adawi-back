from app.db.mongo import db
from datetime import datetime
from app.models.newsletter import NewsletterSubscriber
from app.services.email_service import send_status_email

class NewsletterService:
    def __init__(self):
        self.collection = db.newsletter_subscribers

    async def subscribe(self, name: str, email: str) -> bool:
        # Vérifie si l'email existe déjà
        exists = await self.collection.find_one({"email": email})
        if exists:
            return False
        subscriber = {
            "name": name,
            "email": email,
            "subscribed_at": datetime.utcnow()
        }
        await self.collection.insert_one(subscriber)
        # Envoi email de bienvenue
        subject = "Bienvenue à la newsletter Showroom !"
        body = f"Bonjour {name},\n\nMerci de vous être abonné à notre newsletter. Vous recevrez les nouveautés et offres en avant-première !"
        await send_status_email(email, subject, body)
        return True

    async def send_to_all(self, subject: str, body: str):
        cursor = self.collection.find({})
        async for sub in cursor:
            await send_status_email(sub["email"], subject, body)

newsletter_service = NewsletterService()
