from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class PageView(BaseModel):
    ip_hash: str
    path: str
    user_id: Optional[str] = None
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    timestamp: datetime

class AnalyticsTrack(BaseModel):
    path: str
    user_agent: Optional[str] = None
    referrer: Optional[str] = None

class VisitorStats(BaseModel):
    total_visitors: int
    unique_visitors: int
    page_views: int
    avg_session_time: float = 0.0
    bounce_rate: float = 0.0
    top_pages: List[dict] = []

class AnalyticsOverview(BaseModel):
    visitors_today: int
    visitors_week: int
    visitors_month: int
    page_views_today: int
    page_views_week: int
    page_views_month: int
    top_pages: List[dict]
    traffic_sources: List[dict]
