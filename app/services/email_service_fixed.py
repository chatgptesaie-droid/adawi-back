import os
import aiosmtplib
from email.message import EmailMessage
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

SMTP_HOST = settings.SMTP_HOST
SMTP_PORT = settings.SMTP_PORT
SMTP_USER = settings.SMTP_USER
SMTP_PASS = settings.SMTP_PASS
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "marcusgigoh@gmail.com")
vendor_email = os.getenv("vendor_email", "marcusgigoh@gmail.com")
async def send_status_email(to_email, subject, body):
    """Send email with timeout and error handling"""
    try:
        message = EmailMessage()
        message["From"] = SMTP_USER
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            use_tls=True,
            start_tls=False,
            timeout=50  # 10 second timeout
        )
        logger.info(f"Email sent successfully to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        # Don't raise exception - email failure shouldn't break the app

async def send_admin_email(subject, body):
    await send_status_email(ADMIN_EMAIL, subject, body)

async def send_vendor_email(vendor_email, subject, body):
    await send_status_email(vendor_email, subject, body)

async def send_email(blog, product, subscribers):
    """Envoie un email HTML à chaque abonné avec le titre du blog, un extrait et le produit associé."""
    subject = f"Nouvel article de blog : {blog.title}"

    # Créer le contenu HTML de l'email
    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{blog.title}</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{blog.title}</h1>
            </div>
            <div class="content">
                <p>Bonjour,</p>
                <p>Un nouvel article a été publié sur notre blog :</p>
                <h2>{blog.title}</h2>
                <p>{blog.excerpt or blog.content[:200]}...</p>
                <p style="text-align: center;">
                    <a href="https://yt-adawi-q3qi.vercel.app/blog{blog.slug}" class="button">Lire l'article complet</a>
                </p>
            </div>
            <div class="footer">
                <p>Vous recevez cet email car vous êtes abonné à notre newsletter.</p>
                <p><a href="http://localhost:5173/unsubscribe">Se désabonner</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    for subscriber in subscribers:
        try:
            message = EmailMessage()
            message["From"] = SMTP_USER
            message["To"] = subscriber['email']
            message["Subject"] = subject
            message.set_content(body, subtype='html')

            await aiosmtplib.send(
                message,
                hostname=SMTP_HOST,
                port=SMTP_PORT,
                username=SMTP_USER,
                password=SMTP_PASS,
                use_tls=True,
                start_tls=False,
                timeout=50
            )
            logger.info(f"Email envoyé avec succès à {subscriber['email']}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi d'email à {subscriber['email']}: {e}")
