from fastapi import APIRouter, HTTPException, Depends, Request, Query
from typing import Optional
from app.models.analytics import AnalyticsTrack, VisitorStats, AnalyticsOverview
from app.services.analytics_service import analytics_service
from app.api.auth import get_current_user_optional, get_current_user
from app.models.user import UserPublic

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.post("/track")
async def track_page_view(
    data: AnalyticsTrack,
    request: Request,
    current_user: Optional[UserPublic] = Depends(get_current_user_optional)
):
    """Enregistre une vue de page (endpoint pixel)"""
    # Récupérer l'IP du client
    client_ip = request.client.host
    if hasattr(request, 'headers') and 'x-forwarded-for' in request.headers:
        client_ip = request.headers['x-forwarded-for'].split(',')[0].strip()
    
    user_id = current_user.id if current_user else None
    
    success = await analytics_service.track_page_view(data, client_ip, user_id)
    
    if success:
        return {"status": "ok"}
    else:
        raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement")

@router.get("/visitors", response_model=VisitorStats)
async def get_visitor_stats(
    range_days: int = Query(7, ge=1, le=365, description="Nombre de jours à analyser"),
    current_user: UserPublic = Depends(get_current_user)
):
    """Statistiques des visiteurs (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    return await analytics_service.get_visitor_stats(range_days)

@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    current_user: UserPublic = Depends(get_current_user)
):
    """Aperçu des analytics pour le dashboard admin"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    return await analytics_service.get_analytics_overview()

# Endpoint stub pour les chiffres si trop lourd à implémenter maintenant
@router.get("/stub")
async def get_analytics_stub():
    """Données factices pour l'analytics si pas encore implémenté"""
    return {
        "visitors_today": 147,
        "visitors_week": 892,
        "visitors_month": 3420,
        "page_views_today": 423,
        "page_views_week": 2156,
        "page_views_month": 8934,
        "avg_session_time": 4.2,
        "bounce_rate": 34.5,
        "top_pages": [
            {"path": "/", "views": 1245},
            {"path": "/products", "views": 892},
            {"path": "/categories", "views": 567},
            {"path": "/about", "views": 234},
            {"path": "/contact", "views": 189}
        ],
        "traffic_sources": [
            {"source": "direct", "visits": 1456},
            {"source": "google.com", "visits": 892},
            {"source": "facebook.com", "visits": 234},
            {"source": "instagram.com", "visits": 156}
        ]
    }
