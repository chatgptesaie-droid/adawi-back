from datetime import datetime, timedelta
from typing import Optional
import hashlib
from app.db.mongo import db
from app.models.analytics import PageView, AnalyticsTrack, VisitorStats, AnalyticsOverview

class AnalyticsService:
    def __init__(self):
        self.collection = db.page_views

    def _hash_ip(self, ip: str) -> str:
        """Hash IP pour la confidentialité"""
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

    async def track_page_view(
        self, 
        data: AnalyticsTrack, 
        ip: str, 
        user_id: Optional[str] = None
    ) -> bool:
        """Enregistre une vue de page"""
        try:
            page_view = {
                "ip_hash": self._hash_ip(ip),
                "path": data.path,
                "user_id": user_id,
                "user_agent": data.user_agent,
                "referrer": data.referrer,
                "timestamp": datetime.utcnow()
            }
            
            await self.collection.insert_one(page_view)
            return True
        except Exception:
            return False

    async def get_visitor_stats(self, range_days: int = 7) -> VisitorStats:
        """Récupère les statistiques de visiteurs pour une période"""
        try:
            start_date = datetime.utcnow() - timedelta(days=range_days)
            
            # Total des vues de pages
            page_views = await self.collection.count_documents({
                "timestamp": {"$gte": start_date}
            })
            
            # Visiteurs uniques (basé sur ip_hash)
            unique_visitors_pipeline = [
                {"$match": {"timestamp": {"$gte": start_date}}},
                {"$group": {"_id": "$ip_hash"}},
                {"$count": "unique_count"}
            ]
            
            unique_result = await self.collection.aggregate(unique_visitors_pipeline).to_list(1)
            unique_visitors = unique_result[0]["unique_count"] if unique_result else 0
            
            # Pages les plus visitées
            top_pages_pipeline = [
                {"$match": {"timestamp": {"$gte": start_date}}},
                {"$group": {"_id": "$path", "views": {"$sum": 1}}},
                {"$sort": {"views": -1}},
                {"$limit": 10}
            ]
            
            top_pages = []
            async for page in self.collection.aggregate(top_pages_pipeline):
                top_pages.append({
                    "path": page["_id"],
                    "views": page["views"]
                })
            
            return VisitorStats(
                total_visitors=unique_visitors,
                unique_visitors=unique_visitors,
                page_views=page_views,
                avg_session_time=0.0,  # TODO: implémenter le calcul réel
                bounce_rate=0.0,       # TODO: implémenter le calcul réel
                top_pages=top_pages
            )
            
        except Exception:
            # Retourner des données par défaut en cas d'erreur
            return VisitorStats(
                total_visitors=0,
                unique_visitors=0,
                page_views=0,
                top_pages=[]
            )

    async def get_analytics_overview(self) -> AnalyticsOverview:
        """Récupère un aperçu des analytics pour différentes périodes"""
        try:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=7)
            month_start = now - timedelta(days=30)
            
            # Visiteurs aujourd'hui
            visitors_today = len(await self.collection.distinct("ip_hash", {
                "timestamp": {"$gte": today_start}
            }))
            
            # Visiteurs cette semaine
            visitors_week = len(await self.collection.distinct("ip_hash", {
                "timestamp": {"$gte": week_start}
            }))
            
            # Visiteurs ce mois
            visitors_month = len(await self.collection.distinct("ip_hash", {
                "timestamp": {"$gte": month_start}
            }))
            
            # Vues de pages par période
            page_views_today = await self.collection.count_documents({
                "timestamp": {"$gte": today_start}
            })
            
            page_views_week = await self.collection.count_documents({
                "timestamp": {"$gte": week_start}
            })
            
            page_views_month = await self.collection.count_documents({
                "timestamp": {"$gte": month_start}
            })
            
            # Pages les plus visitées (mois)
            top_pages_pipeline = [
                {"$match": {"timestamp": {"$gte": month_start}}},
                {"$group": {"_id": "$path", "views": {"$sum": 1}}},
                {"$sort": {"views": -1}},
                {"$limit": 10}
            ]
            
            top_pages = []
            async for page in self.collection.aggregate(top_pages_pipeline):
                top_pages.append({
                    "path": page["_id"],
                    "views": page["views"]
                })
            
            # Sources de trafic (basé sur referrer)
            traffic_sources_pipeline = [
                {"$match": {
                    "timestamp": {"$gte": month_start},
                    "referrer": {"$exists": True, "$ne": None, "$ne": ""}
                }},
                {"$group": {"_id": "$referrer", "visits": {"$sum": 1}}},
                {"$sort": {"visits": -1}},
                {"$limit": 5}
            ]
            
            traffic_sources = []
            async for source in self.collection.aggregate(traffic_sources_pipeline):
                traffic_sources.append({
                    "source": source["_id"],
                    "visits": source["visits"]
                })
            
            return AnalyticsOverview(
                visitors_today=visitors_today,
                visitors_week=visitors_week,
                visitors_month=visitors_month,
                page_views_today=page_views_today,
                page_views_week=page_views_week,
                page_views_month=page_views_month,
                top_pages=top_pages,
                traffic_sources=traffic_sources
            )
            
        except Exception:
            # Retourner des données par défaut
            return AnalyticsOverview(
                visitors_today=0,
                visitors_week=0,
                visitors_month=0,
                page_views_today=0,
                page_views_week=0,
                page_views_month=0,
                top_pages=[],
                traffic_sources=[]
            )

analytics_service = AnalyticsService()
