from fastapi import APIRouter, HTTPException, Depends, Query, Response
from typing import Optional
from datetime import datetime, timedelta
import csv
import io
from app.api.auth import get_current_user
from app.models.user import UserPublic
from app.db.mongo import db
from app.models.order import PaymentStatus

router = APIRouter(prefix="/admin/export", tags=["export"])

@router.get("/sales")
async def export_sales_csv(
    range_days: int = Query(30, ge=1, le=365, description="Nombre de jours à exporter"),
    current_user: UserPublic = Depends(get_current_user)
):
    """Export CSV des ventes (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        # Période d'export
        start_date = datetime.utcnow() - timedelta(days=range_days)
        
        # Récupérer les commandes payées
        cursor = db.orders.find({
            "payment_status": PaymentStatus.effectue.value,
            "created_at": {"$gte": start_date}
        }).sort("created_at", -1)
        
        # Créer le CSV en mémoire
        output = io.StringIO()
        writer = csv.writer(output)
        
        # En-têtes
        writer.writerow([
            "Date",
            "Commande ID",
            "Client ID", 
            "Client",
            "Produit ID",
            "Produit",
            "Quantité",
            "Prix unitaire",
            "Total ligne",
            "Total commande",
            "Statut"
        ])
        
        # Données
        async for order in cursor:
            # Récupérer le client
            try:
                user = await db.users.find_one({"_id": order["user_id"]})
                user_name = user.get("full_name", "Client") if user else "Client"
            except:
                user_name = "Client"
            
            # Écrire une ligne par produit de la commande
            for item in order.get("items", []):
                writer.writerow([
                    order["created_at"].strftime("%Y-%m-%d %H:%M"),
                    str(order["_id"]),
                    str(order["user_id"]),
                    user_name,
                    item.get("product_id", ""),
                    item.get("name", "Produit"),
                    item.get("quantity", 0),
                    item.get("price", 0),
                    item.get("price", 0) * item.get("quantity", 0),
                    order.get("total", 0),
                    order.get("status", "")
                ])
        
        # Préparer la réponse
        output.seek(0)
        csv_content = output.getvalue()
        output.close()
        
        filename = f"sales_export_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

@router.get("/products")
async def export_products_csv(
    current_user: UserPublic = Depends(get_current_user)
):
    """Export CSV des produits (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        # Récupérer tous les produits
        cursor = db.products.find({}).sort("created_at", -1)
        
        # Créer le CSV en mémoire
        output = io.StringIO()
        writer = csv.writer(output)
        
        # En-têtes
        writer.writerow([
            "Produit ID",
            "Nom",
            "Description",
            "Prix de vente",
            "Prix de revient",
            "Marge",
            "Marge %",
            "Catégorie ID",
            "Vendeur ID",
            "Stock",
            "Seuil stock bas",
            "Tailles",
            "Couleurs",
            "Tags",
            "Actif",
            "Date création"
        ])
        
        # Données
        async for product in cursor:
            try:
                price = product.get("price", 0)
                cost = product.get("cost_price", 0)
                margin = price - cost
                margin_percent = (margin / price * 100) if price > 0 else 0
                
                writer.writerow([
                    str(product["_id"]),
                    product.get("name", ""),
                    product.get("description", ""),
                    price,
                    cost,
                    margin,
                    f"{margin_percent:.2f}%",
                    product.get("category_id", ""),
                    product.get("seller_id", ""),
                    product.get("stock", 0),
                    product.get("low_stock_threshold", 0),
                    ", ".join(product.get("sizes", [])),
                    ", ".join(product.get("colors", [])),
                    ", ".join(product.get("tags", [])),
                    "Oui" if product.get("is_active", False) else "Non",
                    product.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d %H:%M")
                ])
            except Exception:
                continue  # Ignorer les produits avec des données invalides
        
        # Préparer la réponse
        output.seek(0)
        csv_content = output.getvalue()
        output.close()
        
        filename = f"products_export_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")

@router.get("/refunds")
async def export_refunds_csv(
    current_user: UserPublic = Depends(get_current_user)
):
    """Export CSV des remboursements (admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        # Récupérer tous les remboursements
        cursor = db.refunds.find({}).sort("created_at", -1)
        
        # Créer le CSV en mémoire
        output = io.StringIO()
        writer = csv.writer(output)
        
        # En-têtes
        writer.writerow([
            "Remboursement ID",
            "Commande ID",
            "Client ID",
            "Client",
            "Montant",
            "Raison",
            "Statut",
            "Commentaire",
            "Commentaire admin",
            "Date création",
            "Date mise à jour"
        ])
        
        # Données
        async for refund in cursor:
            try:
                # Récupérer le client
                user = await db.users.find_one({"_id": refund["user_id"]})
                user_name = user.get("full_name", "Client") if user else "Client"
                
                writer.writerow([
                    str(refund["_id"]),
                    refund.get("order_id", ""),
                    str(refund["user_id"]),
                    user_name,
                    refund.get("amount", 0),
                    refund.get("reason", ""),
                    refund.get("status", ""),
                    refund.get("comment", ""),
                    refund.get("admin_comment", ""),
                    refund.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
                    refund.get("updated_at", datetime.utcnow()).strftime("%Y-%m-%d %H:%M")
                ])
            except Exception:
                continue
        
        # Préparer la réponse
        output.seek(0)
        csv_content = output.getvalue()
        output.close()
        
        filename = f"refunds_export_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'export: {str(e)}")
