from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form, BackgroundTasks
from typing import Optional, List
from datetime import datetime
import asyncio
from bson import ObjectId
from app.models.content import (
    PageCreate, PageUpdate, PagePublic, PageStatus,
    FAQCreate, FAQUpdate, FAQPublic, FAQCategory,
    SizeChartCreate, SizeChartUpdate, SizeChartPublic,
    PostCreate, PostUpdate, PostPublic, PostSummary, PostStatus,
    ContentOverview
)
from app.services.content_service import content_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
import cloudinary
import cloudinary.uploader
from app.core.config import settings

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

router = APIRouter(prefix="/admin/content", tags=["admin-content"])

async def require_admin(current_user: UserPublic = Depends(get_current_user)):
    """Vérifier les permissions admin/vendeur"""
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs et vendeurs")
    return current_user

# === GESTION DES PAGES ===

@router.post("/pages", response_model=PagePublic)
async def create_page(
    page: PageCreate,
    admin: UserPublic = Depends(require_admin)
):
    """Créer une nouvelle page"""
    try:
        return await content_service.create_page(page, admin.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pages", response_model=List[PagePublic])
async def get_all_pages(
    status: Optional[PageStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer toutes les pages (admin)"""
    return await content_service.get_pages(status=status, skip=skip, limit=limit)

@router.get("/pages/{slug}", response_model=PagePublic)
async def get_page_admin(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer une page (admin)"""
    page = await content_service.get_page_by_slug(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page non trouvée")
    return page

@router.put("/pages/{slug}", response_model=PagePublic)
async def update_page(
    slug: str,
    update: PageUpdate,
    admin: UserPublic = Depends(require_admin)
):
    """Mettre à jour une page"""
    result = await content_service.update_page(slug, update, admin.id)
    if not result:
        raise HTTPException(status_code=404, detail="Page non trouvée")
    return result

@router.delete("/pages/{slug}")
async def delete_page(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Supprimer une page"""
    success = await content_service.delete_page(slug)
    if not success:
        raise HTTPException(status_code=404, detail="Page non trouvée")
    return {"message": "Page supprimée avec succès"}

# === GESTION DES FAQ ===

@router.post("/faq", response_model=FAQPublic)
async def create_faq(
    faq: FAQCreate,
    admin: UserPublic = Depends(require_admin)
):
    """Créer une nouvelle FAQ"""
    return await content_service.create_faq(faq)

@router.get("/faq", response_model=List[FAQPublic])
async def get_all_faqs(
    category: Optional[FAQCategory] = Query(None),
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer toutes les FAQs (admin)"""
    return await content_service.get_faqs(category=category)

@router.get("/faq/{faq_id}", response_model=FAQPublic)
async def get_faq_admin(
    faq_id: str,
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer une FAQ (admin)"""
    faq = await content_service.get_faq(faq_id)
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")
    return faq

@router.put("/faq/{faq_id}", response_model=FAQPublic)
async def update_faq(
    faq_id: str,
    update: FAQUpdate,
    admin: UserPublic = Depends(require_admin)
):
    """Mettre à jour une FAQ"""
    result = await content_service.update_faq(faq_id, update)
    if not result:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")
    return result

@router.delete("/faq/{faq_id}")
async def delete_faq(
    faq_id: str,
    admin: UserPublic = Depends(require_admin)
):
    """Supprimer une FAQ"""
    success = await content_service.delete_faq(faq_id)
    if not success:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")
    return {"message": "FAQ supprimée avec succès"}

# === GESTION DES GUIDES TAILLES ===

@router.post("/size-charts", response_model=SizeChartPublic)
async def create_size_chart(
    chart: SizeChartCreate,
    admin: UserPublic = Depends(require_admin)
):
    """Créer un nouveau guide des tailles"""
    return await content_service.create_size_chart(chart)

@router.get("/size-charts", response_model=List[SizeChartPublic])
async def get_all_size_charts(
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer tous les guides des tailles (admin)"""
    return await content_service.get_size_charts()

# === GESTION DU BLOG ===

async def upload_blog_image_background(post_id: str, image_data: bytes, filename: str, content_type: str):
    """Background task to upload blog post cover image and update post document"""
    print(f"🚀 Starting background upload for post {post_id}, filename: {filename}")
    try:
        if image_data and filename and content_type and content_type.startswith('image/'):
            print(f"📊 Image data received, size: {len(image_data)} bytes")

            print(f"☁️ Uploading to Cloudinary for post {post_id}")
            upload_result = cloudinary.uploader.upload(
                image_data,
                folder="blog_images",
                public_id=f"{filename.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                overwrite=False,
                resource_type="image",
                quality="auto"
            )
            cover_image_url = upload_result['secure_url']
            print(f"✅ Cloudinary upload successful for post {post_id}, URL: {cover_image_url}")

            # Update the post document with the cover image URL using async MongoDB operation
            print(f"💾 Updating post document {post_id} with cover image URL")
            from app.db.mongo import db
            result = await db.posts.update_one(
                {"_id": ObjectId(post_id)},
                {"$set": {"cover_image": cover_image_url}}
            )
            print(f"✅ Post document update result for {post_id}: modified_count={result.modified_count}")

            if result.modified_count == 0:
                print(f"⚠️ Warning: No document was updated for post {post_id}. Post may not exist.")
            else:
                print(f"✅ Post document updated successfully for post {post_id}")
        else:
            print(f"❌ Invalid image data for post {post_id}: filename={filename}, content_type={content_type}, has_data={bool(image_data)}")
    except Exception as e:
        print(f"❌ Error uploading blog image {filename} for post {post_id}: {str(e)}")
        import traceback
        print(f"🔍 Traceback: {traceback.format_exc()}")

@router.post("/blog/posts", response_model=PostPublic)
async def create_blog_post(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    excerpt: str = Form(...),
    content: str = Form(...),
    status: PostStatus = Form(...),
    tags: List[str] = Form([]),
    cover_image: UploadFile = File(None),
    admin: UserPublic = Depends(require_admin)
):
    """Créer un nouveau post de blog avec image de couverture en background"""
    try:
        # Générer un slug à partir du titre
        import re

        try:
            from unidecode import unidecode
            slug = unidecode(title).lower()
        except ImportError:
            slug = title.lower()

        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = re.sub(r'^-+|-+$', '', slug)
        slug = slug[:100]

        # Créer l'objet PostCreate sans cover_image initialement
        post_data = PostCreate(
            title=title,
            slug=slug,
            excerpt=excerpt,
            content=content,
            status=status,
            tags=tags,
            cover_image=None
        )

        new_post = await content_service.create_post(post_data, admin.id)

        # If cover_image provided, upload synchronously and update post
        print(f"🔍 Checking cover_image: {cover_image}")
        if cover_image:
            print(f"📸 Cover image provided for post {new_post.id}, uploading synchronously")
            image_data = await cover_image.read()
            print(f"📖 Read {len(image_data)} bytes of image data")

            # Upload synchronously
            try:
                if image_data and cover_image.filename and cover_image.content_type and cover_image.content_type.startswith('image/'):
                    print(f"📊 Image data received, size: {len(image_data)} bytes")

                    print(f"☁️ Uploading to Cloudinary for post {new_post.id}")
                    upload_result = cloudinary.uploader.upload(
                        image_data,
                        folder="blog_images",
                        public_id=f"{cover_image.filename.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        overwrite=False,
                        resource_type="image",
                        quality="auto"
                    )
                    cover_image_url = upload_result['secure_url']
                    print(f"✅ Cloudinary upload successful for post {new_post.id}, URL: {cover_image_url}")

                    # Update the post document with the cover image URL
                    print(f"💾 Updating post document {new_post.id} with cover image URL")
                    from app.db.mongo import db
                    result = await db.posts.update_one(
                        {"_id": ObjectId(new_post.id)},
                        {"$set": {"cover_image": cover_image_url}}
                    )
                    print(f"✅ Post document update result for {new_post.id}: modified_count={result.modified_count}")

                    if result.modified_count == 0:
                        print(f"⚠️ Warning: No document was updated for post {new_post.id}. Post may not exist.")
                    else:
                        print(f"✅ Post document updated successfully for post {new_post.id}")
                        # Update the returned post object
                        new_post.cover_image = cover_image_url
                else:
                    print(f"❌ Invalid image data for post {new_post.id}: filename={cover_image.filename}, content_type={cover_image.content_type}, has_data={bool(image_data)}")
            except Exception as e:
                print(f"❌ Error uploading blog image {cover_image.filename} for post {new_post.id}: {str(e)}")
                import traceback
                print(f"🔍 Traceback: {traceback.format_exc()}")
        else:
            print(f"❌ No cover image provided for post {new_post.id}")

        # Si le post est publié, envoyer un email aux abonnés après l'upload de l'image
        if status == PostStatus.published:
            try:
                from app.services.email_service_enhanced import send_email
                from app.services.newsletter_service import newsletter_service

                # Récupérer tous les abonnés
                subscribers = []
                cursor = newsletter_service.collection.find({})
                async for subscriber in cursor:
                    subscribers.append(subscriber)

                # Envoyer l'email à tous les abonnés avec le post complet (avec cover_image)
                await send_email(new_post, None, subscribers)
                print(f"✅ Email sent for published post {new_post.id} with cover image")
            except Exception as e:
                print(f"❌ Error sending email for post {new_post.id}: {e}")

        return new_post
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/blog/posts", response_model=List[PostSummary])
async def get_all_blog_posts(
    status: Optional[PostStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer tous les posts de blog (admin)"""
    return await content_service.get_posts(status=status, skip=skip, limit=limit)

@router.get("/blog/posts/{slug}", response_model=PostPublic)
async def get_blog_post_admin(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Récupérer un post de blog (admin)"""
    post = await content_service.get_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    return post

@router.put("/blog/posts/{slug}", response_model=PostPublic)
async def update_blog_post(
    slug: str,
    background_tasks: BackgroundTasks,
    title: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    status: Optional[PostStatus] = Form(None),
    tags: Optional[List[str]] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    admin: UserPublic = Depends(require_admin)
):
    """Mettre à jour un post de blog avec image de couverture optionnelle en background"""
    try:
        existing_post = await content_service.get_post_by_slug(slug)
        if not existing_post:
            raise HTTPException(status_code=404, detail="Article non trouvé")

        cover_image_url = existing_post.cover_image

        # If cover_image provided, read the file and add background task to upload and update post
        if cover_image:
            image_data = await cover_image.read()
            background_tasks.add_task(upload_blog_image_background, existing_post.id, image_data, cover_image.filename, cover_image.content_type)

        update_data = {}

        if title is not None:
            update_data["title"] = title
        if excerpt is not None:
            update_data["excerpt"] = excerpt
        if content is not None:
            update_data["content"] = content
        if status is not None:
            update_data["status"] = status
        if tags is not None:
            update_data["tags"] = tags
        if cover_image_url is not None:
            update_data["cover_image"] = cover_image_url

        if title and title != existing_post.title:
            import re
            try:
                from unidecode import unidecode
                new_slug = unidecode(title).lower()
            except ImportError:
                new_slug = title.lower()

            new_slug = re.sub(r'[^a-z0-9]+', '-', new_slug)
            new_slug = re.sub(r'^-+|-+$', '', new_slug)
            new_slug = new_slug[:100]
            update_data["slug"] = new_slug

        update_data["updated_at"] = datetime.utcnow()

        if status == PostStatus.published and not existing_post.published_at:
            update_data["published_at"] = datetime.utcnow()

        result = await content_service.posts_collection.update_one(
            {"slug": slug},
            {"$set": update_data}
        )

        if result.modified_count:
            updated_slug = update_data.get("slug", slug)
            return await content_service.get_post_by_slug(updated_slug)
        else:
            raise HTTPException(status_code=404, detail="Article non trouvé")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/blog/posts/{slug}")
async def delete_blog_post(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Supprimer un post de blog (soft delete)"""
    from datetime import datetime

    result = await content_service.posts_collection.update_one(
        {"slug": slug},
        {"$set": {"deleted_at": datetime.now()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    return {"message": "Article marqué comme supprimé avec succès"}

@router.delete("/blog/posts/{slug}/hard-delete")
async def hard_delete_blog_post(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Supprimer un post de blog (hard delete)"""
    success = await content_service.hard_delete_post(slug)
    if not success:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    return {"message": "Article supprimé définitivement avec succès"}

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image to Cloudinary and return its public URL"""
    try:
        # Read file content
        contents = await file.read()

        # Upload to Cloudinary in a thread to avoid blocking the event loop
        upload_result = await asyncio.wait_for(
            asyncio.to_thread(
                cloudinary.uploader.upload,
                contents,
                folder="blog_images",
                public_id=f"{file.filename.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                overwrite=False,
                resource_type="image",
                quality="auto"
            ),
            timeout=60.0  # 60 seconds timeout
        )

        await file.close()

        return {"url": upload_result["secure_url"], "filename": file.filename}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=500, detail="Upload timeout: l'upload a pris trop de temps")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {str(e)}")

# === APERÇU DU CONTENU ===

@router.get("/overview", response_model=ContentOverview)
async def get_content_overview(
    admin: UserPublic = Depends(require_admin)
):
    """Aperçu du contenu pour le dashboard admin"""
    return await content_service.get_content_overview()

# === UTILITAIRES ===

@router.post("/pages/{slug}/publish")
async def publish_page(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Publier une page"""
    from app.models.content import PageUpdate, PageStatus

    result = await content_service.update_page(
        slug,
        PageUpdate(status=PageStatus.published),
        admin.id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Page non trouvée")
    return {"message": "Page publiée avec succès", "page": result}

@router.post("/blog/posts/{slug}/publish")
async def publish_blog_post(
    slug: str,
    admin: UserPublic = Depends(require_admin)
):
    """Publier un post de blog"""
    from app.models.content import PostUpdate, PostStatus
    from datetime import datetime
    from app.services.email_service_enhanced import send_email
    from app.services.newsletter_service import newsletter_service

    # Mise à jour directe
    update_data = {
        "status": PostStatus.published.value,
        "updated_at": datetime.utcnow()
    }

    # Définir published_at si pas encore défini
    existing_post = await content_service.get_post_by_slug(slug)
    if existing_post and not existing_post.published_at:
        update_data["published_at"] = datetime.utcnow()

    result = await content_service.posts_collection.update_one(
        {"slug": slug},
        {"$set": update_data}
    )

    if result.modified_count:
        updated_post = await content_service.get_post_by_slug(slug)

        # Envoyer un email aux abonnés si le post est publié
        if updated_post and updated_post.status == PostStatus.published:
            try:
                # Récupérer tous les abonnés
                subscribers = []
                cursor = newsletter_service.collection.find({})
                async for subscriber in cursor:
                    subscribers.append(subscriber)

                # Envoyer l'email à tous les abonnés
                await send_email(updated_post, None, subscribers)
            except Exception as e:
                print(f"Erreur lors de l'envoi d'email aux abonnés: {e}")

        return {"message": "Article publié avec succès", "post": updated_post}
    else:
        raise HTTPException(status_code=404, detail="Article non trouvé")
