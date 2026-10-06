from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from app.models.content import (
    PagePublic, FAQPublic, FAQCategory, SizeChartPublic,
    PostPublic, PostSummary, PostStatus
)
from app.services.content_service import content_service
from app.api.auth import get_current_user_optional
from app.models.user import UserPublic

router = APIRouter(prefix="/content", tags=["content"])

# === PAGES PUBLIQUES ===

@router.get("/pages/{slug}", response_model=PagePublic)
async def get_page(
    slug: str,
    current_user: Optional[UserPublic] = Depends(get_current_user_optional)
):
    """Récupérer une page par son slug"""
    page = await content_service.get_page_by_slug(slug, increment_views=True)
    if not page:
        raise HTTPException(status_code=404, detail="Page non trouvée")
    
    # Seules les pages publiées sont visibles publiquement
    if page.status != "published" and (not current_user or current_user.role not in ["admin", "vendeur"]):
        raise HTTPException(status_code=404, detail="Page non trouvée")
    
    return page

@router.get("/pages", response_model=List[PagePublic])
async def get_pages(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    current_user: Optional[UserPublic] = Depends(get_current_user_optional)
):
    """Récupérer la liste des pages publiées"""
    # Seules les pages publiées pour le public
    status_filter = None if (current_user and current_user.role in ["admin", "vendeur"]) else "published"

    pages = await content_service.get_pages(
        status=status_filter,
        skip=skip,
        limit=limit
    )

    # Filtrer les pages publiées si pas admin/vendeur
    if not current_user or current_user.role not in ["admin", "vendeur"]:
        pages = [p for p in pages if p.status == "published"]
    
    return pages

# === FAQ PUBLIQUES ===

@router.get("/faq", response_model=List[FAQPublic])
async def get_faqs(
    category: Optional[FAQCategory] = Query(None, description="Filtrer par catégorie"),
    featured: bool = Query(False, description="Seulement les questions mises en avant")
):
    """Récupérer les FAQs"""
    return await content_service.get_faqs(
        category=category,
        featured_only=featured
    )

@router.get("/faq/categories", response_model=List[dict])
async def get_faq_categories():
    """Récupérer toutes les catégories de FAQ avec descriptions"""
    categories = []
    descriptions = {
        "general": "Questions générales sur le site",
        "commande": "Passer et suivre une commande",
        "livraison": "Modalités et délais de livraison",
        "retour": "Retours et échanges",
        "paiement": "Modes de paiement et facturation",
        "compte": "Gestion du compte utilisateur",
        "produit": "Questions sur les produits"
    }
    
    for category in FAQCategory:
        categories.append({
            "value": category.value,
            "label": category.value.title(),
            "description": descriptions.get(category.value, "")
        })
    
    return categories

# Route publique manquante pour consulter les guides des tailles
@router.get("/size-charts", response_model=List[SizeChartPublic])
async def get_public_size_charts():
    """Récupère tous les guides des tailles (public)."""
    try:
        size_charts = await content_service.get_size_charts()
        return size_charts
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération des guides")

# Optionnel : Route pour un guide spécifique
@router.get("/size-charts/{chart_id}", response_model=SizeChartPublic)
async def get_public_size_chart(chart_id: str):
    """Récupère un guide des tailles spécifique (public)."""
    size_chart = await content_service.get_size_chart(chart_id)
    if not size_chart:
        raise HTTPException(status_code=404, detail="Guide des tailles non trouvé")
    return size_chart

# === GUIDE DES TAILLES ===

@router.get("/size-guide", response_model=List[SizeChartPublic])
async def get_size_guide():
    """Récupérer le guide des tailles"""
    return await content_service.get_size_charts()

# === BLOG PUBLIC ===

@router.get("/blog/status", response_model=List[str])
async def get_blog_statuses():
    """Récupérer tous les statuts de blog disponibles"""
    return [status.value for status in PostStatus]

@router.get("/blog/posts", response_model=List[PostSummary])
async def get_blog_posts(
    tags: Optional[str] = Query(None, description="Tags séparés par des virgules"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    current_user: Optional[UserPublic] = Depends(get_current_user_optional)
):
    """Récupérer la liste des posts de blog"""
    # Convertir les tags en liste
    tags_list = None
    if tags:
        tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    
    # Seuls les posts publiés pour le public
    status_filter = None if (current_user and current_user.role in ["admin", "vendeur"]) else PostStatus.published
    
    posts = await content_service.get_posts(
        status=status_filter,
        tags=tags_list,
        skip=skip,
        limit=limit
    )
    
    return posts

@router.get("/blog/posts/{slug}", response_model=PostPublic)
async def get_blog_post(
    slug: str,
    current_user: Optional[UserPublic] = Depends(get_current_user_optional)
):
    """Récupérer un post de blog par son slug"""
    post = await content_service.get_post_by_slug(slug, increment_views=True)
    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")
    
    # Seuls les posts publiés sont visibles publiquement
    if post.status != "published" and (not current_user or current_user.role not in ["admin", "vendeur"]):
        raise HTTPException(status_code=404, detail="Article non trouvé")
    
    return post

@router.get("/blog/tags", response_model=List[str])
async def get_blog_tags():
    """Récupérer tous les tags utilisés dans le blog"""
    # Agrégation pour récupérer tous les tags uniques
    pipeline = [
        {"$match": {"status": "published"}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags"}},
        {"$sort": {"_id": 1}}
    ]
    
    tags = []
    async for tag_doc in content_service.posts_collection.aggregate(pipeline):
        if tag_doc["_id"]:  # Ignorer les tags vides
            tags.append(tag_doc["_id"])
    
    return tags

# === PAGES PRÉDÉFINIES UTILES ===

@router.get("/policies/shipping")
async def get_shipping_policy():
    """Politique de livraison (page prédéfinie ou dynamique)"""
    page = await content_service.get_page_by_slug("politique-livraison")
    if page and page.status == "published":
        return {"content": page.body_html, "updated_at": page.updated_at}
    
    # Page par défaut si pas encore créée
    return {
        "content": """
        <h2>Politique de Livraison</h2>
        <p>Nous livrons dans toute la France métropolitaine.</p>
        <ul>
            <li><strong>Livraison standard</strong> : 3-5 jours ouvrés (2000 fcfa)</li>
            <li><strong>Livraison express</strong> : 24-48h (3000 fcfa)</li>
            <li><strong>Livraison gratuite</strong> : dès 25000 fcfa d'achat</li>
        </ul>
        <p>Les colis sont expédiés sous 24h (jours ouvrés).</p>
        """,
        "updated_at": None
    }

@router.get("/policies/returns")
async def get_returns_policy():
    """Politique de retours (page prédéfinie ou dynamique)"""
    page = await content_service.get_page_by_slug("politique-retours")
    if page and page.status == "published":
        return {"content": page.body_html, "updated_at": page.updated_at}
    
    # Page par défaut
    return {
        "content": """
        <h2>Politique de Retours</h2>
        <p>Vous disposez de <strong>30 jours</strong> pour retourner vos articles.</p>
        <h3>Conditions</h3>
        <ul>
            <li>Articles non portés et dans leur état d'origine</li>
            <li>Étiquettes attachées</li>
            <li>Emballage d'origine</li>
        </ul>
        <h3>Procédure</h3>
        <p>1. Créez une demande de retour dans votre espace client</p>
        <p>2. Imprimez l'étiquette de retour gratuite</p>
        <p>3. Remboursement sous 5-7 jours après réception</p>
        """,
        "updated_at": None
    }
