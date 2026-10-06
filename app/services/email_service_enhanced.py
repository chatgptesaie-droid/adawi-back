import os
import aiosmtplib
import aiohttp
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.message import EmailMessage
from app.core.config import settings

SMTP_HOST = settings.SMTP_HOST
SMTP_PORT = settings.SMTP_PORT
SMTP_USER = settings.SMTP_USER
SMTP_PASS = settings.SMTP_PASS
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "marcusgigoh@gmail.com")
vendor_email = os.getenv("vendor_email", "marcusgigoh@gmail.com")
async def send_status_email(to_email, subject, body):
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
        timeout=50
    )

async def send_admin_email(subject, body):
    await send_status_email(ADMIN_EMAIL, subject, body)

async def send_vendor_email(vendor_email, subject, body):
    await send_status_email(vendor_email, subject, body)

async def send_email(blog, product, subscribers):
    """Envoie un email HTML à chaque abonné avec le titre du blog, un extrait et le produit associé."""
    subject = f"Nouvel article de blog : {blog.title}"

    # Fonction pour télécharger une image
    async def download_image(url):
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.read()
                        print(f"Image téléchargée avec succès depuis {url}, taille: {len(data)} bytes")
                        return data
                    else:
                        print(f"Erreur HTTP {response.status} lors du téléchargement de {url}")
        except Exception as e:
            print(f"Erreur lors du téléchargement de l'image {url}: {e}")
        return None

    # Télécharger les images
    blog_image_data = await download_image(blog.cover_image) if blog.cover_image else None
    product_image_data = await download_image(product.images[0]) if product and product.images else None

    print(f"Blog image data: {blog_image_data is not None}, Product image data: {product_image_data is not None}")

    # Créer le contenu HTML de l'email
    html_content = f"""
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

                {f'<img src="cid:blog_image" alt="{blog.title}" class="blog-image" />' if blog_image_data else ''}

                <p>{blog.excerpt or blog.content[:200]}...</p>

                {f'''
                <div class="product-section">
                    <h3>Produit associé</h3>
                    <div class="product-info">
                        {f'<img src="cid:product_image" alt="{product.name}" class="product-image" />' if product_image_data else ''}
                        <h4>{product.name if product else ""}</h4>
                        <p>{product.description[:150] + "..." if product and product.description else ""}</p>
                        <p><strong>Prix: {product.price if product else ""} FCFA</strong></p>
                    </div>
                    <div class="clear"></div>
                </div>
                ''' if product else ''}

                <p style="text-align: center;">
                    <a href="https://yt-adawi-q3qi.vercel.app/blog{blog.slug}" class="button">Lire l'article complet</a>
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
            # Créer un message multipart
            message = MIMEMultipart('related')
            message["From"] = SMTP_USER
            message["To"] = subscriber['email']
            message["Subject"] = subject

            # Ajouter le contenu HTML
            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)

            # Attacher l'image du blog si elle existe
            if blog_image_data:
                try:
                    # Détecter le type d'image depuis les premiers bytes
                    if blog_image_data.startswith(b'\xff\xd8'):
                        subtype = 'jpeg'
                    elif blog_image_data.startswith(b'\x89PNG'):
                        subtype = 'png'
                    elif blog_image_data.startswith(b'GIF'):
                        subtype = 'gif'
                    else:
                        subtype = 'jpeg'  # fallback

                    blog_image = MIMEImage(blog_image_data, _subtype=subtype)
                    blog_image.add_header('Content-ID', '<blog_image>')
                    blog_image.add_header('Content-Disposition', 'inline', filename=f'blog_image.{subtype}')
                    message.attach(blog_image)
                    print(f"Image du blog attachée avec succès (type: {subtype})")
                except Exception as e:
                    print(f"Erreur lors de l'attachement de l'image du blog: {e}")

            # Attacher l'image du produit si elle existe
            if product_image_data:
                try:
                    # Détecter le type d'image depuis les premiers bytes
                    if product_image_data.startswith(b'\xff\xd8'):
                        subtype = 'jpeg'
                    elif product_image_data.startswith(b'\x89PNG'):
                        subtype = 'png'
                    elif product_image_data.startswith(b'GIF'):
                        subtype = 'gif'
                    else:
                        subtype = 'jpeg'  # fallback

                    product_image = MIMEImage(product_image_data, _subtype=subtype)
                    product_image.add_header('Content-ID', '<product_image>')
                    product_image.add_header('Content-Disposition', 'inline', filename=f'product_image.{subtype}')
                    message.attach(product_image)
                    print(f"Image du produit attachée avec succès (type: {subtype})")
                except Exception as e:
                    print(f"Erreur lors de l'attachement de l'image du produit: {e}")

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
            print(f"Email envoyé avec succès à {subscriber['email']}")
        except Exception as e:
            print(f"Erreur lors de l'envoi d'email à {subscriber['email']}: {e}")

async def send_product_notification_email(product, subscribers):
    """Envoie un email HTML pour notifier d'un nouveau produit"""
    subject = f"Nouveau produit : {product.name}"

    # Fonction pour télécharger une image
    async def download_image(url):
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception as e:
            print(f"Erreur lors du téléchargement de l'image {url}: {e}")
        return None

    # Télécharger l'image du produit
    product_image_data = await download_image(product.images[0]) if product.images else None

    # Créer le contenu HTML de l'email
    html_content = f"""
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

                {f'<img src="cid:product_image" alt="{product.name}" class="product-image" />' if product_image_data else ''}

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
            # Créer un message multipart
            message = MIMEMultipart('related')
            message["From"] = SMTP_USER
            message["To"] = subscriber['email']
            message["Subject"] = subject

            # Ajouter le contenu HTML
            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)

            # Attacher l'image du produit si elle existe
            if product_image_data:
                product_image = MIMEImage(product_image_data)
                product_image.add_header('Content-ID', '<product_image>')
                product_image.add_header('Content-Disposition', 'inline', filename='product_image.jpg')
                message.attach(product_image)

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
            print(f"Email de nouveau produit envoyé avec succès à {subscriber['email']}")
        except Exception as e:
            print(f"Erreur lors de l'envoi d'email à {subscriber['email']}: {e}")
