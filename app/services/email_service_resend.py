import os
from resend import Emails
from email.message import EmailMessage
from app.core.config import settings

resend_client = Emails()
resend_client.api_key = settings.RESEND_API_KEY 

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "onboarding@resend.dev")
vendor_email = os.getenv("vendor_email", "onboarding@resend.dev")

# For production, use verified domains only
# Gmail domains require verification in Resend dashboard
# Use onboarding@resend.dev for testing or verify your domain

# Override for production - use verified domain
# ADMIN_EMAIL = "noreply@yourverifieddomain.com"  # Replace with your verified domain

async def send_status_email(to_email, subject, body):
    try:
        response = resend_client.send(
            {
                "from": ADMIN_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": body,
            }
        )
        print(f"Email sent successfully to {to_email}, response: {response}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

async def send_admin_email(subject, body):
    await send_status_email(ADMIN_EMAIL, subject, body)

async def send_vendor_email(vendor_email, subject, body):
    await send_status_email(vendor_email, subject, body)

async def send_email(blog, product, subscribers):
    subject = f"Nouvel article de blog : {blog.title}"

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
            .blog-image {{ max-width: 100%; height: auto; border-radius: 8px; margin: 20px 0; }}
            .product-section {{ background-color: #f9f9f9; padding: 20px; margin: 20px 0; border-radius: 8px; }}
            .product-image {{ max-width: 200px; height: auto; border-radius: 8px; float: left; margin-right: 20px; }}
            .product-info {{ overflow: hidden; }}
            .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            .clear {{ clear: both; }}
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

                {f'<img src="{blog.cover_image}" alt="{blog.title}" class="blog-image" />' if blog.cover_image else ''}

                <p>{blog.excerpt or blog.content[:200]}...</p>

                {f'''
                <div class="product-section">
                    <h3>Produit associé</h3>
                    <div class="product-info">
                        {f'<img src="{product.images[0] if product.images else ""}" alt="{product.name}" class="product-image" />' if product and product.images else ''}
                        <h4>{product.name if product else ""}</h4>
                        <p>{product.description[:150] + "..." if product and product.description else ""}</p>
                        <p><strong>Prix: {product.price if product else ""} FCFA</strong></p>
                    </div>
                    <div class="clear"></div>
                </div>
                ''' if product else ''}

                <p style="text-align: center;">
                    <a href="https://yt-adawi-q3qi.vercel.app/blog" class="button">Lire l'article complet</a>
                </p>
            </div>
            <div class="footer">
                <p>Vous recevez cet email car vous êtes abonné à notre newsletter.</p>
            </div>
        </div>
    </body>
    </html>
    """

    for subscriber in subscribers:
        try:
            response = resend_client.send(
                {
                    "from": ADMIN_EMAIL,
                    "to": [subscriber['email']],
                    "subject": subject,
                    "html": body,
                }
            )
            print(f"Email envoyé avec succès à {subscriber['email']}, response: {response}")
        except Exception as e:
            print(f"Erreur lors de l'envoi d'email à {subscriber['email']}: {e}")

async def send_product_notification_email(product, subscribers):
    subject = f"Nouveau produit : {product.name}"

    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Nouveau produit : {product.name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .product-image {{ max-width: 100%; height: auto; border-radius: 8px; margin: 20px 0; }}
            .product-details {{ background-color: #f9f9f9; padding: 20px; margin: 20px 0; border-radius: 8px; }}
            .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Nouveau produit disponible !</h1>
            </div>
            <div class="content">
                <p>Bonjour,</p>
                <p>Un nouveau produit a été ajouté à notre catalogue :</p>

                {f'<img src="{product.images[0]}" alt="{product.name}" class="product-image" />' if product.images else ''}

                <div class="product-details">
                    <h2>{product.name}</h2>
                    <p>{product.description}</p>
                    <p><strong>Prix: {product.price} FCFA</strong></p>
                    {f'<p><strong>Catégorie: {product.category}</strong></p>' if hasattr(product, 'category') and product.category else ''}
                </div>

                <p style="text-align: center;">
                    <a href="https://yt-adawi-q3qi.vercel.app/products/{product.id}" class="button">Voir le produit</a>
                </p>
            </div>
            <div class="footer">
                <p>Vous recevez cet email car vous êtes abonné à notre newsletter.</p>
                <p><a href="https://yt-adawi-q3qi.vercel.app/unsubscribe">Se désabonner</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    for subscriber in subscribers:
        try:
            response = resend_client.send(
                {
                    "from": ADMIN_EMAIL,
                    "to": [subscriber['email']],
                    "subject": subject,
                    "html": body,
                }
            )
            print(f"Email de nouveau produit envoyé avec succès à {subscriber['email']}, response: {response}")
        except Exception as e:
            print(f"Erreur lors de l'envoi d'email à {subscriber['email']}: {e}")
