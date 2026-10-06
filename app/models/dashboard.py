from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class TopProduct(BaseModel):
    product_id: str
    name: str
    total_quantity: int
    total_revenue: float

class TopVendor(BaseModel):
    user_id: str
    name: str
    total_orders: int
    total_revenue: float

class RecentOrder(BaseModel):
    order_id: str
    user_name: str
    total: float
    status: str
    created_at: datetime

class OrderStatusCount(BaseModel):
    status: str
    count: int

class PendingOrder(BaseModel):
    order_id: str
    user_name: str
    status: str
    created_at: datetime
    total: float

# NOUVELLES DONNÉES POUR GRAPHIQUES
class RevenueDataPoint(BaseModel):
    date: str  # YYYY-MM-DD
    revenue: float
    orders_count: int

class CategorySales(BaseModel):
    category_name: str
    total_sales: float
    product_count: int
    percentage: float

class UserGrowth(BaseModel):
    date: str
    new_clients: int
    new_vendors: int
    total_users: int

class GeographicSales(BaseModel):
    region: str
    sales_count: int
    revenue: float

class CostRevenueDataPoint(BaseModel):
    date: str  # YYYY-MM-DD
    revenue: float
    cost: float
    profit: float
    margin_percent: float

class RefundStats(BaseModel):
    total_refunds: int
    total_refunded_amount: float
    pending_refunds: int
    approved_refunds: int
    rejected_refunds: int
    processed_refunds: int

class InventoryStats(BaseModel):
    total_products: int
    low_stock_count: int
    out_of_stock_count: int
    total_stock_value: float
    low_stock_percentage: float

class StockUpdate(BaseModel):
    stock: int = Field(..., ge=0, description="Nouveau niveau de stock")

class InventoryAlert(BaseModel):
    product_id: str
    product_name: str
    current_stock: int
    low_stock_threshold: int
    seller_id: str

class AdminDashboardResponse(BaseModel):
    # KPIs principaux
    total_revenue: float
    total_orders: int
    total_customers: int
    total_vendors: int
    total_products: int
    commission_collected: float

    # PHASE 7 - Nouveaux KPIs coûts/marges et remboursements
    total_cost: float = 0.0
    gross_profit: float = 0.0
    gross_margin_percent: float = 0.0
    refunds_count: int = 0
    refunds_total_amount: float = 0.0
    low_stock_products: int = 0
    low_stock_threshold: float = 0.0
    out_of_stock_count: int = 0

    # Croissance (vs période précédente)
    revenue_growth: float  # Pourcentage
    orders_growth: float
    customers_growth: float

    # Nouveaux champs demandés
    total_revenue_semaine: float
    pourcentage_revenue_semaine: float
    total_visiteurs: int
    total_visiteurs_semaine: int
    pourcentage_visiteurs_semaine: float
    pourcentage_visiteur_total: float
    prix_total_rembourse: float  # Alias pour refunds_total_amount
    revenus_par_categorie: Dict[str, float]
    revenus_par_categorie_percent: Dict[str, float]
    top_categorie: Optional[str]
    top_categorie_revenue: Optional[float]
    total_commande_semaine: int
    pourcentage_commande_semaine: float

    # Statistiques journalières et hebdomadaires
    total_orders_today: int
    total_orders_week: int
    total_revenue_today: float
    total_revenue_week: float

    # Données pour graphiques
    revenue_evolution: List[RevenueDataPoint]  # 30 derniers jours
    cost_revenue_evolution: List[CostRevenueDataPoint] = []  # Évolution revenus vs coûts
    sales_by_category: List[CategorySales]
    user_growth: List[UserGrowth]  # 12 derniers mois
    geographic_sales: List[GeographicSales]

    # Stats remboursements et inventaire
    refund_stats: RefundStats
    inventory_alerts: List[InventoryAlert] = []

    # Données existantes
    top_products: List[TopProduct]
    top_vendors: List[TopVendor]
    recent_orders: List[RecentOrder]
    orders_by_status: List[OrderStatusCount]
    pending_orders: List[PendingOrder]

class VendorDashboardResponse(BaseModel):
    total_revenue: float
    total_orders: int
    total_products: int
    top_products: List[TopProduct]
    recent_orders: List[RecentOrder]
    orders_by_status: List[OrderStatusCount]
    average_order_value: float
    pending_orders: List[PendingOrder]

    # Statistiques journalières et hebdomadaires
    total_orders_today: int
    total_orders_week: int
    total_revenue_today: float
    total_revenue_week: float

    # Statistiques mensuelles
    total_orders_month: int
    total_revenue_month: float

    # Nouveaux champs d'inventaire
    low_stock_threshold: float = 0.0
    out_of_stock_count: int = 0
