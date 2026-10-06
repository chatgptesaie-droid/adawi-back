from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form, Request
from typing import List, Optional
from pydantic import BaseModel
from app.models.order import OrderCreate, OrderPublic, OrderStatus, PaymentStatus, StatusLog, OrderTrackingResponse, OrderItem, Address, CustomOrderCreate, Measurements
from app.models.product import ProductSize
from app.services.order_service import order_service
from app.services.cart_service import cart_service
from app.services.product_service import product_service
from app.services.promotion_service import promotion_service
from app.api.auth import get_current_user
from app.models.user import UserPublic
from bson import ObjectId
from app.db.mongo import db
from app.api.paiement import create_facture
from app.models.facture import FactureBase
from app.core.emails_utils import notify_admin_of_new_invoice
# from app.services.moneyfusion_service import moneyfusion_service
from datetime import datetime
import json
import os
import uuid
import cloudinary
import cloudinary.uploader
from app.core.config import settings
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

async def upload_images_to_cloudinary(images: List[UploadFile], folder: str = "products") -> List[str]:
    """Upload des images vers Cloudinary et retourne les URLs."""
    image_urls = []
    for image in images:
        if image.filename and image.content_type and image.content_type.startswith('image/'):
            try:
                # Lire le contenu du fichier
                contents = await image.read()

                # Upload vers Cloudinary
                upload_result = cloudinary.uploader.upload(
                    contents,
                    folder=folder,
                    public_id=image.filename.split('.')[0],  # Nom sans extension
                    overwrite=True,
                    resource_type="image"
                )

                image_urls.append(upload_result['secure_url'])
                logger.info(f"Image uploadée vers Cloudinary: {upload_result['secure_url']}")

            except Exception as e:
                logger.error(f"Erreur upload Cloudinary pour {image.filename}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Erreur upload image {image.filename}: {str(e)}")
        elif image.filename:
            raise HTTPException(status_code=400, detail=f"Fichier {image.filename} n'est pas une image")

    return image_urls

router = APIRouter(prefix="/orders", tags=["orders"])

class CheckoutResponse(BaseModel):
    order: OrderPublic
    payment_url: Optional[str] = None
    identifier: Optional[str] = None

async def get_discounted_prices_for_cart_items(cart_items):
    """
    Récupère les prix réduits en temps réel pour les items du panier
    """
    discounted_items = []

    for item in cart_items:
        try:
            # Récupérer le produit avec son prix réduit
            product = await product_service.get_product_with_discount(item.product_id)

            if product and product.get("discounted_price") is not None:
                # Utiliser le prix réduit
                item.price = product["discounted_price"]
                print(f"💰 Prix réduit appliqué: {item.product_id} - {product['discounted_price']} FCFA")
            else:
                # Utiliser le prix original si pas de réduction
                if hasattr(product, 'price') and product.get('price'):
                    item.price = product['price']
                print(f"💰 Prix original conservé: {item.product_id} - {item.price} FCFA")

            discounted_items.append(item)

        except Exception as e:
            print(f"⚠️ Erreur lors de la récupération du prix réduit pour {item.product_id}: {e}")
            # Garder le prix original en cas d'erreur
            discounted_items.append(item)

    return discounted_items

# Créer une commande (checkout) avec paiement PayGate
@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    address: Address,
    background_tasks: BackgroundTasks,
    phone_number: str = Query(..., description="Numéro de téléphone pour le paiement"),
    network: str = Query(..., description="Réseau mobile (FLOOZ, TMONEY, etc.)"),
    current_user: UserPublic = Depends(get_current_user)
):
    # Récupérer le panier de l'utilisateur
    cart = await cart_service.get_cart(user_id=current_user.id)
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Le panier est vide")

    # Valider et nettoyer les items du panier avant transformation
    valid_items = []
    for item in cart.items:
        # Vérifier que l'item a un prix valide
        if not hasattr(item, 'price') or item.price is None or item.price <= 0:
            print(f"⚠️ Item avec prix invalide supprimé: {item.product_id}")
            continue

        # Vérifier que la quantité est valide
        if not hasattr(item, 'quantity') or item.quantity is None or item.quantity <= 0:
            print(f"⚠️ Item avec quantité invalide supprimé: {item.product_id}")
            continue

        # Vérifier que le product_id est valide (24 caractères hexadécimaux)
        if not hasattr(item, 'product_id') or not item.product_id or len(item.product_id) != 24:
            print(f"⚠️ Item avec product_id invalide supprimé: {item.product_id}")
            continue

        # Vérifier que tous les caractères sont hexadécimaux
        try:
            int(item.product_id, 16)
        except ValueError:
            print(f"⚠️ Item avec product_id non-hexadécimal supprimé: {item.product_id}")
            continue

        valid_items.append(item)

    if not valid_items:
        raise HTTPException(status_code=400, detail="Aucun item valide dans le panier. Veuillez vérifier vos articles.")

    # Récupérer les prix réduits en temps réel avant transformation
    valid_items = await get_discounted_prices_for_cart_items(valid_items)

    # Transformer en OrderItem avec gestion d'erreur
    order_items = []
    for item in valid_items:
        try:
            order_item = OrderItem(**item.dict())
            order_items.append(order_item)
        except Exception as e:
            print(f"⚠️ Erreur lors de la transformation de l'item {item.product_id}: {e}")
            continue

    if not order_items:
        raise HTTPException(status_code=500, detail="Erreur lors du traitement des articles du panier.")

    # Calculer le total avec gestion d'erreur
    try:
        total = sum(item.price * item.quantity for item in order_items)
        if total <= 0:
            raise HTTPException(status_code=400, detail="Le total de la commande doit être supérieur à 0.")
    except Exception as e:
        print(f"⚠️ Erreur lors du calcul du total: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors du calcul du total de la commande.")
    
    # Créer la commande
    order_data = OrderCreate(
        items=order_items,
        address=address,
        total=total,
        customer_phone=phone_number,
    )
    new_order = await order_service.create_order(current_user.id, order_data)
    
    # Créer la facture PayGate liée à la commande
    facture_data = FactureBase(
        phone_number=phone_number,
        amount=int(total),  # PayGate attend un entier
        network=network,
        order_id=new_order.id  # Lier la facture à la commande
    )
    
    # Créer la facture et obtenir l'URL de paiement
    payment_result = await create_facture(facture_data, current_user.id)
    
    # Notification admin de la nouvelle commande et facture
    user_name = f"{getattr(current_user, 'prenom', '')} {getattr(current_user, 'nom', '')}".strip() or "Utilisateur"
    background_tasks.add_task(
        notify_admin_of_new_invoice,
        db=db,
        user_name=user_name,
        amount=int(total),
        email=current_user.email,
        identifier=payment_result["identifier"],
        status="créée"
    )

    
    
    # Dans le endpoint /checkout, remplacer la section commentée par :
    try:
        from app.core.emails_utils import send_payment_email
        logger.info(f"Envoi email création commande à {current_user.email} pour référence {payment_result['identifier']}")
        background_tasks.add_task(
            send_payment_email,
            email=current_user.email,
            amount=int(total),
            payment_method=network,
            reference=payment_result["identifier"],
            status="créée"
        )
        logger.info(f"Email création commande programmé pour {current_user.email}")
    except Exception as e:
        logger.error(f"Erreur programmation email client pour checkout classique: {e}")

    # # Envoyer email client de confirmation création commande (synchrone pour éviter les problèmes de background tasks)
    # import logging
    # try:
    #     from app.core.emails_utils import send_payment_email
    #     logging.info(f"Envoi email création commande à {current_user.email} pour référence {payment_result['identifier']}")
    #     await send_payment_email(
    #         email=current_user.email,
    #         amount=int(total),
    #         payment_method=network,
    #         reference=payment_result["identifier"],
    #         status="créée"
    #     )
    #     logging.info(f"Email création commande envoyé avec succès à {current_user.email}")
    # except Exception as e:
    #     # Log l'erreur mais ne bloque pas la commande
    #     logging.error(f"Erreur envoi email client pour checkout classique: {e}")
    
    # Vider le panier
    await cart_service.clear_cart(user_id=current_user.id)
    
    return CheckoutResponse(
        order=new_order,
        payment_url=payment_result["payment_url"],
        identifier=payment_result["identifier"]
    )

# Créer une commande sur mesure (checkout custom) avec paiement PayGate
@router.post("/checkout-custom", response_model=CheckoutResponse)
async def checkout_custom(
    background_tasks: BackgroundTasks,
    description: str = Form(..., description="Description du vêtement souhaité"),
    measurements: Optional[str] = Form(None, description="Mesures en JSON (optionnel si sauvegardé dans le profil)"),
    current_size: Optional[str] = Form(None, description="Taille actuelle (XS, S, M, L, XL, XXL) (optionnel si sauvegardé dans le profil)"),
    delivery_type: str = Form(..., pattern="^(pickup|delivery)$", description="Type de livraison: pickup ou delivery"),
    delivery_date: str = Form(..., description="Date de livraison YYYY-MM-DD"),
    address: Optional[str] = Form(None, description="Adresse en JSON si delivery (optionnel si sauvegardé dans le profil)"),
    phone_number: str = Query(..., description="Numéro de téléphone pour le paiement"),
    network: str = Query(..., description="Réseau mobile (FLOOZ, TMONEY, etc.)"),
    photos: List[UploadFile] = File(None, description="Photos uploadées (multiple)(optionnel si sauvegardé dans le profil)"),
    current_user: UserPublic = Depends(get_current_user)
):
    from app.services.user_service import user_service

    # Pré-remplir mesures, taille, adresse et photos depuis le profil utilisateur si non fournies
    user_profile = None
    measurements_provided = bool(measurements and measurements.strip())
    if not measurements or measurements.strip() == "":
        user_profile = await user_service.get_user_by_id(current_user.id)
        if user_profile and user_profile.measurements:
            measurements = json.dumps(user_profile.measurements.dict())
        else:
            raise HTTPException(status_code=400, detail="Mesures requises - veuillez les fournir ou les sauvegarder dans votre profil")

    if not current_size or current_size.strip() == "":
        if not user_profile:
            user_profile = await user_service.get_user_by_id(current_user.id)
        if user_profile and user_profile.size:
            current_size = user_profile.size.value
        else:
            raise HTTPException(status_code=400, detail="Taille requise - veuillez la fournir ou la sauvegarder dans votre profil")

    # Pré-remplir adresse depuis le profil utilisateur si non fournie et si livraison
    address_obj = None
    if delivery_type == "delivery":
        if not address or address.strip() == "":
            if not user_profile:
                user_profile = await user_service.get_user_by_id(current_user.id)
            if user_profile and hasattr(user_profile, "address") and user_profile.address:
                address_obj = user_profile.address
                address = json.dumps(address_obj.dict())
            else:
                raise HTTPException(status_code=400, detail="Adresse requise pour la livraison - veuillez la fournir ou la sauvegarder dans votre profil")
        else:
            try:
                address_data = json.loads(address)
                address_obj = Address(**address_data)
            except:
                raise HTTPException(status_code=400, detail="Adresse invalide")
    else:
        address_obj = None

    # Pré-remplir photos depuis le profil utilisateur si non fournies
    photo_urls = []
    if photos is None or len(photos) == 0:
        if not user_profile:
            user_profile = await user_service.get_user_by_id(current_user.id)
        if user_profile and user_profile.photo:
            photo_urls = user_profile.photo
    else:
        # Uploader les photos vers Cloudinary
        if photos:
            # Limiter à 5 photos maximum
            if len(photos) > 5:
                raise HTTPException(status_code=400, detail="Maximum 5 photos autorisées")
            try:
                photo_urls = await upload_images_to_cloudinary(photos, "products/custom-orders")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload des photos: {str(e)}")

    # Récupérer le panier de l'utilisateur
    cart = await cart_service.get_cart(user_id=current_user.id)
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Le panier est vide")

    # Valider et nettoyer les items du panier avant transformation
    valid_items = []
    for item in cart.items:
        # Vérifier que l'item a un prix valide
        if not hasattr(item, 'price') or item.price is None or item.price <= 0:
            print(f"⚠️ Item avec prix invalide supprimé: {item.product_id}")
            continue

        # Vérifier que la quantité est valide
        if not hasattr(item, 'quantity') or item.quantity is None or item.quantity <= 0:
            print(f"⚠️ Item avec quantité invalide supprimé: {item.product_id}")
            continue

        # Vérifier que le product_id est valide (24 caractères hexadécimaux)
        if not hasattr(item, 'product_id') or not item.product_id or len(item.product_id) != 24:
            print(f"⚠️ Item avec product_id invalide supprimé: {item.product_id}")
            continue

        # Vérifier que tous les caractères sont hexadécimaux
        try:
            int(item.product_id, 16)
        except ValueError:
            print(f"⚠️ Item avec product_id non-hexadécimal supprimé: {item.product_id}")
            continue

        valid_items.append(item)

    if not valid_items:
        raise HTTPException(status_code=400, detail="Aucun item valide dans le panier. Veuillez vérifier vos articles.")

    # Récupérer les prix réduits en temps réel avant transformation
    valid_items = await get_discounted_prices_for_cart_items(valid_items)

    # Transformer en OrderItem avec gestion d'erreur
    order_items = []
    for item in valid_items:
        try:
            order_item = OrderItem(**item.dict())
            order_items.append(order_item)
        except Exception as e:
            print(f"⚠️ Erreur lors de la transformation de l'item {item.product_id}: {e}")
            continue

    if not order_items:
        raise HTTPException(status_code=500, detail="Erreur lors du traitement des articles du panier.")

    # Calculer le total avec gestion d'erreur
    try:
        total = sum(item.price * item.quantity for item in order_items)
        if total <= 0:
            raise HTTPException(status_code=400, detail="Le total de la commande doit être supérieur à 0.")
    except Exception as e:
        print(f"⚠️ Erreur lors du calcul du total: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors du calcul du total de la commande.")

    # Parser les données JSON
    try:
        measurements_data = json.loads(measurements)
        measurements_obj = Measurements(**measurements_data)
    except:
        raise HTTPException(status_code=400, detail="Mesures invalides")

    if measurements_provided:
        await user_service.update_user_profile(
            current_user.id,
            measurements=measurements_obj
        )

    # Valider la taille actuelle
    try:
        # Gérer le cas où la taille est envoyée comme ["S"] au lieu de "S"
        if current_size.startswith('[') and current_size.endswith(']'):
            # Extraire la valeur entre crochets
            import ast
            size_list = ast.literal_eval(current_size)
            if isinstance(size_list, list) and len(size_list) == 1:
                current_size = size_list[0]
        current_size_obj = ProductSize(current_size)
    except (ValueError, SyntaxError):
        raise HTTPException(status_code=400, detail=f"Taille invalide: {current_size}. Valeurs acceptées: {[s.value for s in ProductSize]}")

    address_obj = None
    if delivery_type == "delivery":
        if not address:
            raise HTTPException(status_code=400, detail="Adresse requise pour la livraison")
        try:
            address_data = json.loads(address)
            address_obj = Address(**address_data)
        except:
            raise HTTPException(status_code=400, detail="Adresse invalide")

    # Valider la date de livraison (au moins 1 semaine à partir d'aujourd'hui)
    from datetime import timedelta

    # Vérifier que la date n'est pas un placeholder
    if delivery_date in ["YYYY-MM-DD", "string", ""]:
        raise HTTPException(
            status_code=400,
            detail="Veuillez fournir une date de livraison valide au format YYYY-MM-DD (ex: 2024-12-15)"
        )

    try:
        delivery_date_obj = datetime.fromisoformat(delivery_date).date()
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Format de date invalide: {delivery_date}. Utilisez le format YYYY-MM-DD (ex: 2024-12-15)"
        )

    today = datetime.now().date()
    min_delivery_date = today + timedelta(days=7)

    if delivery_date_obj < min_delivery_date:
        raise HTTPException(
            status_code=400,
            detail=f"La date de livraison doit être au moins 7 jours à partir d'aujourd'hui. Date minimale: {min_delivery_date}"
        )

    # Créer la commande sur mesure
    try:
        order_data = CustomOrderCreate(
            items=order_items,
            address=address_obj,
            total=total,
            customer_phone=phone_number,
            description=description,
            measurements=measurements_obj,
            photo_urls=photo_urls,
            current_size=current_size_obj,
            delivery_type=delivery_type,
            delivery_date=delivery_date_obj
        )
        new_order = await order_service.create_order(current_user.id, order_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création de la commande: {str(e)}")

    # Créer la facture PayGate liée à la commande
    facture_data = FactureBase(
        phone_number=phone_number,
        amount=int(total),
        network=network,
        order_id=new_order.id
    )

    # Créer la facture et obtenir l'URL de paiement
    payment_result = await create_facture(facture_data, current_user.id)

    # Log détaillé pour debug des commandes sur mesure
    print(f"🧵 COMMANDE SUR MESURE CRÉÉE:")
    print(f"   📦 Order ID: {new_order.id}")
    print(f"   💰 Amount: {total}")
    print(f"   📱 Phone: {phone_number}")
    print(f"   🌐 Network: {network}")
    print(f"   🧾 Facture ID: {payment_result['facture']['id']}")
    print(f"   🔗 Tx Reference: {payment_result['facture']['tx_reference']}")
    print(f"   📊 Status: {payment_result['facture']['status']}")
    print(f"   ⏰ Created At: {payment_result['facture']['created_at']}")

    # Notification admin
    user_name = f"{getattr(current_user, 'prenom', '')} {getattr(current_user, 'nom', '')}".strip() or "Utilisateur"
    background_tasks.add_task(
        notify_admin_of_new_invoice,
        db=db,
        user_name=user_name,
        amount=int(total),
        email=current_user.email,
        identifier=payment_result["identifier"],
        status="créée"
    )

    # Envoyer email client de confirmation création commande (synchrone)
    try:
        from app.core.emails_utils import send_payment_email
        await send_payment_email(
            email=current_user.email,
            amount=int(total),
            payment_method=network,
            reference=payment_result["identifier"],
            status="créée"
        )
    except Exception as e:
        # Log l'erreur mais ne bloque pas la commande
        print(f"Erreur envoi email client: {e}")

    # Vider le panier
    await cart_service.clear_cart(user_id=current_user.id)
    return CheckoutResponse(
        order=new_order,
        payment_url=payment_result["payment_url"],
        identifier=payment_result["identifier"]
    )

# Voir l'historique des commandes
@router.get("/", response_model=List[OrderPublic])
async def get_orders(
    status: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    date_min: Optional[str] = Query(None),
    date_max: Optional[str] = Query(None),
    current_user: UserPublic = Depends(get_current_user)
):
    return await order_service.get_orders_advanced(
        current_user=current_user,
        status=status,
        payment_status=payment_status,
        date_min=date_min,
        date_max=date_max
    )

# Voir le détail d'une commande
@router.get("/{order_id}", response_model=OrderPublic)
async def get_order(order_id: str, current_user: UserPublic = Depends(get_current_user)):
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    # Si client, il doit être propriétaire de la commande
    if current_user.role == "client" and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    # # Si vendeur, il doit avoir au moins un produit dans la commande
    # if current_user.role == "vendeur":
    #     for item in order.items:
    #         product = await db.products.find_one({"_id": ObjectId(item.product_id)})
    #         if product and product.get("seller_id") == current_user.id:
    #             break
    #     else:
    #         raise HTTPException(status_code=403, detail="Accès refusé")
    # # Si admin, accès total
    return order

# Changer le statut d'une commande (admin ou vendeur)
@router.put("/{order_id}/status", response_model=OrderPublic)
async def update_status(
    order_id: str,
    status: OrderStatus,
    comment: Optional[str] = Query(None, description="Commentaire ou motif du changement de statut"),
    current_user: UserPublic = Depends(get_current_user)
):
    if current_user.role not in ["admin", "vendeur"]:
        raise HTTPException(status_code=403, detail="Accès refusé")
    # Vérifier la transition de statut
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    allowed_transitions = {
        OrderStatus.en_cours: [OrderStatus.en_preparation, OrderStatus.boutique, OrderStatus.expediee, OrderStatus.annulee],
        OrderStatus.en_preparation: [OrderStatus.en_cours, OrderStatus.expediee, OrderStatus.annulee],
        OrderStatus.boutique: [OrderStatus.expediee, OrderStatus.livree, OrderStatus.annulee],  # Vente physique peut être expédiée ou livrée
        OrderStatus.expediee: [OrderStatus.livree, OrderStatus.annulee],
        OrderStatus.livree: [],
        OrderStatus.annulee: []
    }
    if status not in allowed_transitions[order.status]:
        raise HTTPException(status_code=400, detail=f"Transition de statut non autorisée depuis {order.status} vers {status}")
    updated_order = await order_service.update_status(order_id, status.value, comment=comment)
    if not updated_order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    return updated_order

# Simuler le paiement d'une commande
@router.post("/{order_id}/pay", response_model=OrderPublic)
async def pay_order(
    order_id: str,
    success: bool = Query(True, description="True pour paiement accepté, False pour refusé"),
    current_user: UserPublic = Depends(get_current_user)
):
    order = await order_service.get_order(order_id, user_id=current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    paid_order = await order_service.pay_order(order_id, success, user_id=current_user.id)
    return paid_order

# Consulter l'historique des statuts d'une commande
@router.get("/{order_id}/history", response_model=List[StatusLog])
async def get_status_history(order_id: str, current_user: UserPublic = Depends(get_current_user)):
    order = await order_service.get_order(order_id, user_id=current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    return order.status_history 

# Suivi de l'avancement d'une commande (tracking)
@router.get("/{order_id}/tracking", response_model=OrderTrackingResponse)
async def track_order(order_id: str, current_user: UserPublic = Depends(get_current_user)):
    order = await order_service.get_order(order_id, user_id=current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    # Définir les étapes principales
    steps_def = [
        (OrderStatus.en_cours, "Paiement accepté"),
        (OrderStatus.expediee, "Commande expédiée"),
        (OrderStatus.livree, "Commande livrée")
    ]
    # Construire les étapes atteintes
    reached_status = set([log.status for log in order.status_history])
    steps = []
    for status, label in steps_def:
        log = next((l for l in order.status_history if l.status == status), None)
        steps.append({
            "status": status,
            "label": label,
            "reached": log is not None,
            "date": log.changed_at if log else None
        })
    return OrderTrackingResponse(
        order_id=order.id,
        current_status=order.status,
        steps=steps,
        history=order.status_history
    )

# Vente physique (boutique) - accessible aux vendeurs et admins
@router.post("/physical-sale", response_model=CheckoutResponse)
async def physical_sale(
    background_tasks: BackgroundTasks,
    current_user: UserPublic = Depends(get_current_user)
):
    # Vérifier que l'utilisateur est vendeur ou admin
    if current_user.role not in ["vendeur", "admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé - réservé aux vendeurs et admins")

    # Récupérer le panier de l'utilisateur
    cart = await cart_service.get_cart(user_id=current_user.id)
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Le panier est vide")

    # Valider et nettoyer les items du panier avant transformation
    valid_items = []
    for item in cart.items:
        # Vérifier que l'item a un prix valide
        if not hasattr(item, 'price') or item.price is None or item.price <= 0:
            print(f"⚠️ Item avec prix invalide supprimé: {item.product_id}")
            continue

        # Vérifier que la quantité est valide
        if not hasattr(item, 'quantity') or item.quantity is None or item.quantity <= 0:
            print(f"⚠️ Item avec quantité invalide supprimé: {item.product_id}")
            continue

        # Vérifier que le product_id est valide (24 caractères hexadécimaux)
        if not hasattr(item, 'product_id') or not item.product_id or len(item.product_id) != 24:
            print(f"⚠️ Item avec product_id invalide supprimé: {item.product_id}")
            continue

        # Vérifier que tous les caractères sont hexadécimaux
        try:
            int(item.product_id, 16)
        except ValueError:
            print(f"⚠️ Item avec product_id non-hexadécimal supprimé: {item.product_id}")
            continue

        valid_items.append(item)

    if not valid_items:
        raise HTTPException(status_code=400, detail="Aucun item valide dans le panier. Veuillez vérifier vos articles.")

    # Récupérer les prix réduits en temps réel avant transformation
    valid_items = await get_discounted_prices_for_cart_items(valid_items)

    # Transformer en OrderItem avec gestion d'erreur
    order_items = []
    for item in valid_items:
        try:
            order_item = OrderItem(**item.dict())
            order_items.append(order_item)
        except Exception as e:
            print(f"⚠️ Erreur lors de la transformation de l'item {item.product_id}: {e}")
            continue

    if not order_items:
        raise HTTPException(status_code=500, detail="Erreur lors du traitement des articles du panier.")

    # Calculer le total avec gestion d'erreur
    try:
        total = sum(item.price * item.quantity for item in order_items)
        if total <= 0:
            raise HTTPException(status_code=400, detail="Le total de la commande doit être supérieur à 0.")
    except Exception as e:
        print(f"⚠️ Erreur lors du calcul du total: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors du calcul du total de la commande.")

    # Vérifier le stock avant de procéder
    for item in order_items:
        product = await db.products.find_one({"_id": ObjectId(item.product_id)})
        if not product or product.get("stock", 0) < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuffisant pour le produit {item.product_id}. Stock disponible: {product.get('stock', 0) if product else 0}"
            )

    # Créer la commande comme livrée avec paiement effectué
    order_data = OrderCreate(
        items=order_items,
        total=total,
        status=OrderStatus.livree,
        payment_status=PaymentStatus.effectue,  # Paiement considéré comme effectué
        payment_method="boutique"  # Méthode de paiement boutique
    )
    new_order = await order_service.create_order(current_user.id, order_data)

    # Décrémenter le stock immédiatement pour les ventes physiques
    for item in order_items:
        await db.products.update_one(
            {"_id": ObjectId(item.product_id)},
            {"$inc": {"stock": -item.quantity}}
        )

    # Vider le panier
    await cart_service.clear_cart(user_id=current_user.id)

    # Notification admin de la nouvelle vente physique
    # user_name = f"{getattr(current_user, 'prenom', '')} {getattr(current_user, 'nom', '')}".strip() or "Vendeur"
    # background_tasks.add_task(
    #     notify_admin_of_new_invoice,
    #     db=db,
    #     user_name=user_name,
    #     amount=int(total),
    #     email=current_user.email,
    #     identifier=f"PHYSICAL-{new_order.id[:8]}",
    #     status="boutique"
    # )

    return CheckoutResponse(
        order=new_order,
        payment_url=None,  # Pas d'URL de paiement pour les ventes physiques
        identifier=f"PHYSICAL-{new_order.id[:8]}"
    )

# Test endpoint pour vérifier l'envoi d'emails
@router.post("/test-email")
async def test_email(email: str = Query(..., description="Email de test")):
    """Test endpoint pour vérifier la configuration SMTP"""
    import logging
    try:
        from app.core.emails_utils import send_payment_email
        logging.info(f"Test envoi email à {email}")
        await send_payment_email(
            email=email,
            amount=1000,
            payment_method="TEST",
            reference="TEST-123",
            status="créée"
        )
        return {"message": f"Email de test envoyé à {email}"}
    except Exception as e:
        logging.error(f"Erreur test email: {e}")
