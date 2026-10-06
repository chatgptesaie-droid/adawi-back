from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
import pandas as pd
from datetime import datetime, timedelta
from app.api.auth import get_current_user
from app.models.user import UserPublic
from app.services.dashboard_service import dashboard_service

router = APIRouter(prefix="/admin/export", tags=["admin_export"])

async def require_admin(current_user: UserPublic = Depends(get_current_user)):
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs et vendeurs")
    return current_user

@router.get("/rapports")
async def export_admin_rapports(
    date_range: str = Query("30-days"),
    admin=Depends(require_admin)
):
    now = datetime.utcnow()
    if date_range == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == "7-days":
        start_date = now - timedelta(days=7)
    elif date_range == "30-days":
        start_date = now - timedelta(days=30)
    elif date_range == "90-days":
        start_date = now - timedelta(days=90)
    elif date_range == "year":
        start_date = now - timedelta(days=365)
    else:
        start_date = now - timedelta(days=30)

    # Récupérer les données du dashboard global
    dashboard_data = await dashboard_service.get_admin_dashboard()

    # Calculer le nombre total de produits vendus dans la période
    pipeline_ventes = [
        {"$match": {"payment_status": "effectue", "created_at": {"$gte": start_date}}},
        {"$unwind": "$items"},
        {"$group": {"_id": None, "total_vendus": {"$sum": "$items.quantity"}}}
    ]
    ventes_result = await dashboard_service.orders_collection.aggregate(pipeline_ventes).to_list(1)
    total_produits_vendus = ventes_result[0]["total_vendus"] if ventes_result else 0

    # Calculer le nombre total de nouveaux clients dans la période
    total_nouveaux_clients = await dashboard_service.users_collection.count_documents({"role": "client", "created_at": {"$gte": start_date}})

    # Calculer le nombre total de commandes dans la période
    total_orders_period = await dashboard_service.orders_collection.count_documents({"payment_status": "effectue", "created_at": {"$gte": start_date}})

    # Calculer le revenu total dans la période
    pipeline_revenue = [
        {"$match": {"payment_status": "effectue", "created_at": {"$gte": start_date}}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$total"}}}
    ]
    revenue_result = await dashboard_service.orders_collection.aggregate(pipeline_revenue).to_list(1)
    total_revenue_period = revenue_result[0]["total_revenue"] if revenue_result else 0

    # Construire les données pour export
    data = {
        "Total Orders": [total_orders_period],
        "Total Revenue": [total_revenue_period],
        "Total Customers": [dashboard_data.total_customers],
        "Total Products": [dashboard_data.total_products],
        "Orders Growth": [dashboard_data.orders_growth],
        "Revenue Growth": [dashboard_data.revenue_growth],
        "Customers Growth": [dashboard_data.customers_growth],
        "Commission Collected": [dashboard_data.commission_collected],
        "Total Products Sold": [total_produits_vendus],
        "Total New Clients": [total_nouveaux_clients]
    }

    df = pd.DataFrame(data)

    # Exporter en Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Rapports')
    output.seek(0)

    filename = f"admin_rapports_{date_range}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }

    return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers=headers)
