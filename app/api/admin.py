from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import Optional, List
from bson import ObjectId
from datetime import datetime, timedelta
from app.models.admin import (
    AdminSettings, AdminSettingsUpdate, UserAdminUpdateRole, UserAdminBan, AdminUserCreate
)
from app.models.user import UserPublic, UserCreate
from app.models.order import Measurements, Address
from app.models.product import ProductSize
from app.services.user_service import user_service
from app.services.admin_service import admin_service
from app.api.auth import get_current_user
from app.services.dashboard_service_fixed import dashboard_service_fixed as dashboard_service
from app.models.dashboard import AdminDashboardResponse
from fastapi.responses import JSONResponse
import cloudinary.uploader
import asyncio
import json
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])

async def require_admin(current_user: UserPublic = Depends(get_current_user)):
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs et vendeurs")
    return current_user

@router.get("/users", response_model=List[UserPublic])
async def list_users(role: Optional[str] = Query(None), q: Optional[str] = Query(None), skip: int = 0, limit: int = 50, include_deleted: bool = False, admin=Depends(require_admin)):
    users = await user_service.list_users(role=role, q=q, skip=skip, limit=limit)
    if not include_deleted:
        users = [u for u in users if not u.is_deleted]
    return users

@router.get("/users/{user_id}", response_model=UserPublic)
async def get_user(user_id: str, admin=Depends(require_admin)):
    user = await user_service.get_user_public_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user

@router.post("/users", response_model=UserPublic)
async def create_user(user_data: AdminUserCreate, admin=Depends(require_admin)):
    """Créer un nouvel utilisateur (réservé aux admins)"""
    try:
        # Mapper les données du modal vers UserCreate
        user_create = UserCreate(
            email=user_data.email,
            full_name=user_data.name,
            role=user_data.role,
            password=user_data.password,
            is_active=user_data.status == "Actif"
        )
        new_user = await user_service.create_user(user_create)
        return new_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/users/{user_id}/role", response_model=UserPublic)
async def update_user_role(user_id: str, data: UserAdminUpdateRole, admin=Depends(require_admin)):
    user = await user_service.update_role(user_id, data.role)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user

@router.patch("/users/{user_id}/ban", response_model=UserPublic)
async def ban_user(user_id: str, data: UserAdminBan, admin=Depends(require_admin)):
    user = await user_service.ban_user(user_id, data.ban)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    ok = await user_service.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {"soft_deleted": True}

@router.get("/settings", response_model=AdminSettings)
async def get_settings(admin=Depends(require_admin)):
    return await admin_service.get_settings()

@router.put("/settings", response_model=AdminSettings)
async def update_settings(data: AdminSettingsUpdate, admin=Depends(require_admin)):
    return await admin_service.update_settings(data)

@router.get("/stats/commission")
async def get_commission(admin=Depends(require_admin)):
    total = await admin_service.compute_commission_collected()
    return {"commission_collected": total}

@router.get("/stats/categories")
async def get_top_categories(limit: int = Query(10, ge=1, le=50), admin=Depends(require_admin)):
    """Top catégories avec agrégation réelle"""
    return await admin_service.get_top_categories(limit)

@router.get("/stats/commission/detail")
async def get_commission_detail(admin=Depends(require_admin)):
    """Commission détaillée par vendeur"""
    return await admin_service.get_commission_by_vendor()

@router.get("/stats/margins")
async def get_margin_stats(admin=Depends(require_admin)):
    """Statistiques de marges globales"""
    return await admin_service.get_margin_stats()

# Nouveau endpoint pour récupérer les données des rapports admin
@router.get("/rapports")
async def get_admin_rapports(
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

    # Calculer le nombre total de clients actifs dans la période (commandes + versements)
    # Récupérer les user_ids des commandes
    order_user_ids = await dashboard_service.orders_collection.distinct("user_id", {"payment_status": "effectue", "created_at": {"$gte": start_date}})
    # Récupérer les user_ids des versements payés
    installment_user_ids = await dashboard_service.payment_installments_collection.distinct("user_id", {"status": "paid", "paid_at": {"$gte": start_date}})
    # Combiner et compter les uniques
    all_user_ids = set(order_user_ids + installment_user_ids)
    total_nouveaux_clients = len(all_user_ids)

    # Calculer le nombre total de commandes dans la période
    total_orders_period = await dashboard_service.orders_collection.count_documents({"payment_status": "effectue", "created_at": {"$gte": start_date}})

    # Calculer le nombre total de commandes en versements dans la période
    total_installment_orders = await dashboard_service.orders_collection.count_documents({
        "payment_status": "effectue",
        "payment_type": "installments",
        "created_at": {"$gte": start_date}
    })

    # Calculer le nombre total de versements payés dans la période
    installments_count = await dashboard_service.payment_installments_collection.count_documents({"status": "paid", "paid_at": {"$gte": start_date}})

    # Ajouter les versements payés au total des commandes
    total_orders_period += installments_count

    # Calculer le revenu total dans la période (commandes complètes + versements payés)
    pipeline_revenue = [
        {"$match": {
            "payment_status": "effectue",
            "created_at": {"$gte": start_date},
            "$or": [
                {"payment_type": {"$ne": "installments"}},
                {"payment_type": {"$exists": False}}
            ]
        }},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$total"}}}
    ]
    revenue_result = await dashboard_service.orders_collection.aggregate(pipeline_revenue).to_list(1)
    gross_revenue = revenue_result[0]["total_revenue"] if revenue_result else 0

    # Ajouter les versements payés dans la période
    installments_pipeline = [
        {"$match": {"status": "paid", "paid_at": {"$gte": start_date}}},
        {"$group": {"_id": None, "total": {"$sum": "$paid_amount"}}}
    ]
    installments_result = await dashboard_service.payment_installments_collection.aggregate(installments_pipeline).to_list(1)
    total_installments_paid = installments_result[0]["total"] if installments_result else 0

    total_revenue_period = gross_revenue + total_installments_paid

    # Construire la réponse enrichie
    response = {
        "total_orders": total_orders_period,
        "total_revenue": total_revenue_period,
        "total_customers": dashboard_data.total_customers,
        "total_products": dashboard_data.total_products,
        "orders_growth": dashboard_data.orders_growth,
        "revenue_growth": dashboard_data.revenue_growth,
        "customers_growth": dashboard_data.customers_growth,
        "commission_collected": dashboard_data.commission_collected,
        "total_produits_vendus": total_produits_vendus,
        "total_nouveaux_clients": total_nouveaux_clients
    }
    return JSONResponse(response)

# Endpoint pour récupérer les ventes paginées avec filtre date
@router.get("/rapports/ventes")
async def get_admin_ventes(
    page: int = Query(1, ge=1),
    items_per_page: int = Query(10, ge=1, le=100),
    date_range: str = Query("30-days"),
    admin=Depends(require_admin)
):
    # Calculer la date de début selon date_range
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

    skip = (page - 1) * items_per_page

    # Pipeline d'agrégation pour récupérer les ventes
    pipeline = [
        {"$match": {"payment_status": "effectue", "created_at": {"$gte": start_date}}},
        {"$sort": {"created_at": -1}},
        {"$skip": skip},
        {"$limit": items_per_page}
    ]

    orders_cursor = dashboard_service.orders_collection.aggregate(pipeline)
    ventes = []
    async for order in orders_cursor:
        # Récupérer le nom du client
        client_name = ""
        if order.get("user_id"):
            try:
                # user_id peut être un ObjectId ou une string
                user_id = order["user_id"]
                if isinstance(user_id, str):
                    try:
                        user_id = ObjectId(user_id)
                    except:
                        pass
                user = await dashboard_service.users_collection.find_one({"_id": user_id})
                if user:
                    client_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    if not client_name:
                        client_name = user.get('email', '')
            except:
                client_name = "Client inconnu"

        # Vérifier si c'est une commande en versements
        if order.get("payment_type") == "installments":
            # Pour les commandes en versements, récupérer les paiements effectués
            order_id = str(order["_id"])
            paid_installments = await dashboard_service.payment_installments_collection.find({
                "order_id": order_id,
                "status": "paid"
            }).sort("paid_at", 1).to_list(None)

            # Pour chaque versement payé, créer une entrée
            for installment in paid_installments:
                ventes.append({
                    "date": installment["paid_at"].strftime("%Y-%m-%d") if installment.get("paid_at") else order["created_at"].strftime("%Y-%m-%d"),
                    "produit": f"{order.get('items', [{}])[0].get('name', 'Produit')} - Versement {installment.get('installment_number', 0)}",
                    "client": client_name,
                    "quantite": 1,
                    "montant": installment.get("paid_amount", 0)
                })
        else:
            # Pour les commandes normales, extraire les items
            for item in order.get("items", []):
                ventes.append({
                    "date": order["created_at"].strftime("%Y-%m-%d"),
                    "produit": item.get("name", ""),
                    "client": client_name,
                    "quantite": item.get("quantity", 0),
                    "montant": item.get("price", 0) * item.get("quantity", 0)
                })

    # Récupérer les paiements d'échéances (installments) payés dans la période
    pipeline_installments = [
        {"$match": {"status": "paid", "paid_at": {"$gte": start_date}}},
        {"$lookup": {
            "from": "orders",
            "localField": "order_id",
            "foreignField": "_id",
            "as": "order"
        }},
        {"$unwind": "$order"},
        {"$sort": {"paid_at": -1}},
        {"$skip": skip},
        {"$limit": items_per_page}
    ]

    installments_cursor = dashboard_service.payment_installments_collection.aggregate(pipeline_installments)
    async for installment in installments_cursor:
        # Récupérer le nom du client
        client_name = ""
        user_id = installment["order"].get("user_id")
        if user_id:
            try:
                if isinstance(user_id, str):
                    try:
                        user_id = ObjectId(user_id)
                    except:
                        pass
                user = await dashboard_service.users_collection.find_one({"_id": user_id})
                if user:
                    client_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    if not client_name:
                        client_name = user.get('email', '')
            except:
                client_name = "Client inconnu"

        ventes.append({
            "date": installment["paid_at"].strftime("%Y-%m-%d") if installment.get("paid_at") else "",
            "produit": "Paiement échéance",
            "client": client_name,
            "quantite": 1,
            "montant": installment.get("paid_amount", 0)
        })

    # Total des ventes pour pagination (ordre + échéances)
    total_orders = await dashboard_service.orders_collection.count_documents({"payment_status": "effectue", "created_at": {"$gte": start_date}})
    total_installments = await dashboard_service.payment_installments_collection.count_documents({"status": "paid", "paid_at": {"$gte": start_date}})
    total_ventes = total_orders + total_installments
    total_pages = (total_ventes + items_per_page - 1) // items_per_page

    return JSONResponse({
        "page": page,
        "items_per_page": items_per_page,
        "total_pages": total_pages,
        "total_items": total_ventes,
        "ventes": ventes
    })

# Endpoint pour récupérer les produits avec calculs corrects
@router.get("/rapports/produits")
async def get_admin_produits(admin=Depends(require_admin)):
    # D'abord, récupérer tous les produits qui ont été vendus via agrégation
    pipeline_produits_vendus = [
        {"$match": {"payment_status": "effectue"}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"$toString": "$items.product_id"},
            "total_vendus": {"$sum": "$items.quantity"},
            "total_revenus": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
            "dernier_prix": {"$last": "$items.price"},
            "nom_produit": {"$last": "$items.name"}
        }}
    ]

    produits_vendus_result = await dashboard_service.orders_collection.aggregate(pipeline_produits_vendus).to_list(None)

    produits_data = []

    # Pour chaque produit qui a été vendu, récupérer ses infos détaillées
    for produit_vendu in produits_vendus_result:
        product_id_str = produit_vendu["_id"]

        # Essayer de trouver le produit dans la collection products
        try:
            product_obj_id = ObjectId(product_id_str)
            product_details = await dashboard_service.products_collection.find_one({"_id": product_obj_id})
        except:
            product_details = None

        # Utiliser les données du produit si trouvé, sinon utiliser celles de la commande
        nom = product_details.get("name", produit_vendu.get("nom_produit", "Produit inconnu")) if product_details else produit_vendu.get("nom_produit", "Produit inconnu")
        stock = product_details.get("stock", 0) if product_details else 0
        statut = "En stock" if stock > 0 else "Rupture"

        produits_data.append({
            "nom": nom,
            "stock": stock,
            "vendus": produit_vendu["total_vendus"],
            "revenus": produit_vendu["total_revenus"],
            "statut": statut
        })

    # Trier par revenus décroissants
    produits_data.sort(key=lambda x: x["revenus"], reverse=True)

    return JSONResponse(produits_data)

@router.put("/users/{user_id}/profile", response_model=UserPublic)
async def update_user_profile(
    user_id: str,
    measurements: Optional[str] = Form(None),
    size: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    photos: List[UploadFile] = File(None),
    admin=Depends(require_admin)
):
    """Mettre à jour le profil utilisateur (mesures, taille, photos, adresse) - réservé aux admins/vendeurs"""
    # Parser les mesures si fournies
    measurements_obj = None
    if measurements:
        try:
            measurements_data = json.loads(measurements)
            measurements_obj = Measurements(**measurements_data)
        except:
            raise HTTPException(status_code=400, detail="Format des mesures invalide")

    # Parser la taille
    size_obj = None
    if size:
        try:
            size_obj = ProductSize(size)
        except:
            raise HTTPException(status_code=400, detail="Taille invalide")

    # Parser l'adresse si fournie
    address_obj = None
    if address:
        try:
            address_data = json.loads(address)
            address_obj = Address(**address_data)
        except:
            raise HTTPException(status_code=400, detail="Format de l'adresse invalide")

    # Gérer l'upload des photos
    photo_urls = []
    if photos:
        for photo in photos[:5]:  # Limiter à 5 photos
            if photo.filename:
                try:
                    # Upload vers Cloudinary
                    upload_result = cloudinary.uploader.upload(
                        photo.file,
                        folder="user_profiles",
                        public_id=f"user_{user_id}_{photo.filename}",
                        resource_type="image"
                    )
                    photo_urls.append(upload_result["secure_url"])
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Erreur upload photo: {str(e)}")

    # Mettre à jour le profil
    user = await user_service.update_user_profile(
        user_id=user_id,
        measurements=measurements_obj,
        size=size_obj,
        address=address_obj,
        photo=photo_urls if photo_urls else None
    )
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user
