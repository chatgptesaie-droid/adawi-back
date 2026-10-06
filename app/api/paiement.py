from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Optional
import requests
from urllib.parse import quote
from bson import ObjectId

from app.db.mongo import db
from app.api.auth import get_current_user
from app.core.emails_utils import notify_admin_of_new_invoice, send_payment_email
from app.models.facture import FactureBase, FactureInDB
from app.models.user import UserInDB
from app.core.config import settings
from app.services.order_service import order_service
# from app.services.moneyfusion_service import moneyfusion_service

class PaymentResponse(BaseModel):
    identifier: str
    payment_url: str
    status: str

from pydantic import BaseModel, Field

class PayGateCallback(BaseModel):
    status: Optional[str] = "0"  # Valeur par défaut "0" (succès)
    tx_reference: Optional[str] = None
    identifier: str
    amount: Optional[int] = None
    phone_number: Optional[str] = None
    network: Optional[str] = None
    payment_reference: Optional[str] = None
    datetime: Optional[str] = None
    payment_method: Optional[str] = None



router = APIRouter(tags=["paiements"], prefix="/paiements")

async def create_facture(data: FactureBase, user_id: str):
    """Créer une facture et initier le paiement PayGate"""
    tx_ref = str(uuid4())
    identifier = f"INV-{tx_ref}"

    # Ajouter une description par défaut
    description = f"Paiement de {data.amount} FCFA"

    redirect_url = "http://localhost:5173/boutique"  # Corrigé avec le protocole https://
    
    
    # Générer l'URL de paiement PayGate avec tous les paramètres requis
    base_url = f"https://paygateglobal.com/v1/page?token={settings.API_KEY_PAYGATE}&amount={data.amount}&description={description}&identifier={identifier}&url={redirect_url}&phone={data.phone_number}&network={data.network}"
    
    # Ajouter les paramètres optionnels
    params = []
    if data.phone_number:
        params.append(f"phone={data.phone_number}")
    if data.network:
        params.append(f"network={data.network}")
    
 
    params.append(f"description={description}")
    # URL de redirection après paiement (vers le frontend)
   
    params.append(f"url={quote(redirect_url)}")  # Utiliser 'url' au lieu de 'return_url' pour PayGate
    
    # Callback URL (backend)
    # callback_url = "https://showroom-backend-2x3g.onrender.com/paiements/callback"
    # params.append(f"callback_url={quote(callback_url)}")

    # Construire l'URL finale
    if params:
        payment_url = f"{base_url}&{'&'.join(params)}"
    else:
        payment_url = base_url
    
    # Créer la facture avec statut "en attente" et lien vers la commande
    facture_data = {
        "phone_number": data.phone_number,
        "amount": data.amount,
        "network": data.network,
        "tx_reference": identifier,
        "status": "en attente",
        "user_id": user_id,
        "order_id": data.order_id,  # Lien vers la commande
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    # Insérer dans MongoDB
    result = await db.factures.insert_one(facture_data)
    facture_data["id"] = str(result.inserted_id)

    return {
        "facture": facture_data,
        "payment_url": payment_url,
        "identifier": identifier
    }

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=PaymentResponse)
async def create_new_facture(
    facture_data: FactureBase,
    background_tasks: BackgroundTasks,
    current_user: UserInDB = Depends(get_current_user)
):
    """Créer une nouvelle facture et retourner les infos de paiement"""
    try:
        result = await create_facture(facture_data, current_user.id)
        
        # Notification admin en arrière-plan
        user_name = f"{getattr(current_user, 'prenom', '')} {getattr(current_user, 'nom', '')}".strip() or "Utilisateur"
        
        background_tasks.add_task(
            notify_admin_of_new_invoice,
            db=db,
            user_name=user_name,
            amount=facture_data.amount,
            email=current_user.email,
            identifier=result["identifier"]
        )

        return PaymentResponse(
            identifier=result["identifier"],
            payment_url=result["payment_url"],
            status="en attente"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# @router.post("/callback")
# async def payment_callback(request: Request):
#     """Callback PayGate - gère JSON, form-urlencoded et body brut avec logging détaillé"""
#     try:
#         # Capturer les headers et le body brut pour debug
#         headers = dict(request.headers)
#         content_type = headers.get('content-type', '').lower()
#         raw_body = await request.body()

#         print("=== CALLBACK PAYGATE REÇU ===")
#         print(f"Content-Type: {content_type}")
#         print(f"Raw body: {raw_body.decode() if raw_body else 'Empty'}")
#         print(f"Headers: {headers}")

#         callback_data = None

#         if 'application/json' in content_type:
#             # Format JSON
#             try:
#                 json_data = await request.json()
#                 print(f"✅ JSON parsé: {json_data}")
#                 callback_data = PayGateCallback(**json_data)
#             except Exception as e:
#                 print(f"❌ Erreur parsing JSON: {e}")
#                 return {"message": "Callback reçu mais erreur parsing JSON", "status": "error", "error": str(e)}

#         elif 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type:
#             # Format Form-Data
#             try:
#                 form_data = await request.form()
#                 print(f"✅ Form data parsé: {dict(form_data)}")

#                 # Créer l'objet PayGateCallback à partir du form
#                 callback_data = PayGateCallback(
#                     status=form_data.get('status'),
#                     identifier=form_data.get('identifier'),
#                     tx_reference=form_data.get('tx_reference'),
#                     amount=form_data.get('amount'),
#                     phone_number=form_data.get('phone_number'),
#                     network=form_data.get('network'),
#                     payment_reference=form_data.get('payment_reference'),
#                     datetime=form_data.get('datetime'),
#                     payment_method=form_data.get('payment_method')
#                 )
#             except Exception as e:
#                 print(f"❌ Erreur parsing Form-Data: {e}")
#                 return {"message": "Callback reçu mais erreur parsing Form-Data", "status": "error", "error": str(e)}

#         else:
#             # Format inconnu - fallback : tenter de parser le raw body
#             try:
#                 if not raw_body:
#                     print("ℹ️ Body vide reçu - probablement un test ou ping PayGate")
#                     print(f"Headers détaillés: {headers}")
#                     print(f"Method: {request.method}")
#                     print(f"URL: {request.url}")
#                     print(f"Query params: {dict(request.query_params)}")

#                     # Vérifier s'il y a des données dans les query parameters (certains providers les envoient ainsi)
#                     query_params = dict(request.query_params)
#                     if query_params:
#                         print(f"🔍 Tentative parsing query params: {query_params}")
#                         try:
#                             callback_data = PayGateCallback(**query_params)
#                             print("✅ Callback parsé depuis query params")
#                         except Exception as qp_e:
#                             print(f"❌ Impossible de parser query params: {qp_e}")
#                             return {
#                                 "message": "Callback reçu (body vide) - vérifiez les logs pour détails",
#                                 "status": "empty_body",
#                                 "headers": headers,
#                                 "query_params": query_params
#                             }
#                     else:
#                         return {
#                             "message": "Callback reçu (body vide) - probablement un ping PayGate",
#                             "status": "empty_body",
#                             "headers": headers
#                         }

#                 text = raw_body.decode()
#                 print(f"🔄 Tentative parsing raw body: '{text}'")

#                 # Essayer de parser comme form-urlencoded
#                 if '=' in text:
#                     # Parser les paires clé=valeur
#                     parsed = {}
#                     for pair in text.split('&'):
#                         if '=' in pair:
#                             key, value = pair.split('=', 1)
#                             parsed[key] = value

#                     print(f"✅ Raw body parsé comme form: {parsed}")
#                     callback_data = PayGateCallback(**parsed)

#                 else:
#                     # Essayer JSON comme dernier recours
#                     try:
#                         json_data = await request.json()
#                         print(f"✅ Raw body parsé comme JSON: {json_data}")
#                         callback_data = PayGateCallback(**json_data)
#                     except:
#                         print("❌ Impossible de parser le raw body")
#                         return {"message": "Callback reçu mais format non reconnu", "status": "unparsed", "raw_body": text}

#             except Exception as e:
#                 print(f"❌ Erreur parsing fallback: {e}")
#                 return {"message": "Callback reçu mais erreur parsing", "status": "error", "error": str(e)}

#         # Traiter les données callback
#         print(f"Données parsées: {callback_data.dict()}")
#         print(f"Recherche facture avec identifier: '{callback_data.identifier}' et tx_reference: '{callback_data.tx_reference}'")

#         # Chercher la facture par tx_reference ou identifier
#         query = {
#             "$or": [
#                 {"tx_reference": str(callback_data.identifier)},
#                 {"tx_reference": str(callback_data.tx_reference)}
#             ]
#         }
#         print(f"Requête MongoDB: {query}")

#         facture = await db.factures.find_one(query)
#         if not facture:
#             print(f"Facture non trouvée pour identifier: '{callback_data.identifier}' ou tx_reference: '{callback_data.tx_reference}'")

#             # Debug: Lister toutes les factures pour voir ce qui existe
#             all_factures = await db.factures.find().to_list(length=10)
#             print(f"Factures existantes dans la base:")
#             for f in all_factures:
#                 print(f"  - tx_reference: '{f.get('tx_reference')}', id: {f.get('_id')}")

#             # IMPORTANT: Retourner 200 OK même si facture non trouvée pour éviter les retry loops de PayGate
#             print("⚠️ Facture non trouvée, mais on retourne 200 OK pour éviter les retry PayGate")
#             return {"message": "Callback reçu mais facture non trouvée", "status": "facture_not_found"}

#         print(f"Facture trouvée: {facture['_id']}, tx_reference: '{facture.get('tx_reference')}'")

#         # Mise à jour du statut selon le code PayGate
#         status_mapping = {
#             "0": "payée",
#             "2": "en cours",
#             "4": "expirée",
#             "6": "annulée"
#         }

#         new_status = status_mapping.get(str(callback_data.status), "erreur")

#         # Mise à jour de la facture
#         update_data = {"status": new_status, "updated_at": datetime.utcnow()}

#         # Vérifier que les données ne sont pas "string" avant de les mettre à jour
#         if callback_data.tx_reference and callback_data.tx_reference != "string":
#             update_data["payment_reference"] = callback_data.tx_reference
#         if callback_data.amount and callback_data.amount != "string":
#             update_data["amount"] = callback_data.amount
#         if callback_data.phone_number and callback_data.phone_number != "string":
#             update_data["phone_number"] = callback_data.phone_number
#         if callback_data.network and callback_data.network != "string":
#             update_data["network"] = callback_data.network
#         if callback_data.payment_reference and callback_data.payment_reference != "string":
#             update_data["payment_reference"] = callback_data.payment_reference
#         if callback_data.datetime and callback_data.datetime != "string":
#             update_data["payment_datetime"] = callback_data.datetime
#         if callback_data.payment_method and callback_data.payment_method != "string":
#             update_data["payment_method"] = callback_data.payment_method

#         await db.factures.update_one(
#             {"_id": facture["_id"]},
#             {"$set": update_data}
#         )

#         # Envoyer notification si paiement réussi
#         if callback_data.status == "0":  # Paiement réussi
#             user = await db.users.find_one({"_id": ObjectId(facture["user_id"])})
#             if user:
#                 # Notification client
#                 await send_payment_email(
#                     email=user.get("email"),
#                     amount=facture["amount"],
#                     payment_method=facture.get("network", ""),
#                     reference=callback_data.tx_reference or callback_data.identifier,
#                     status="réussi"
#                 )
#                 # Notification admin
#                 await notify_admin_of_new_invoice(
#                     db=db,
#                     user_name=f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
#                     amount=facture["amount"],
#                     email=user.get("email"),
#                     identifier=callback_data.identifier,
#                     status="payée"
#                 )

#             # Mettre à jour le statut de paiement de la commande liée avec la méthode de paiement
#             if "order_id" in facture and facture["order_id"]:
#                 # Définir la méthode de paiement selon le réseau utilisé
#                 payment_method = f"mobile_money_{facture.get('network', '').lower()}"
#                 await order_service.pay_order(
#                     facture["order_id"],
#                     True,
#                     user_id=facture["user_id"],
#                     payment_method=payment_method
#                 )

#         return {"message": "Callback traité avec succès", "status": new_status}

#     except Exception as e:
#         # IMPORTANT: Toujours retourner 200 OK même en cas d'erreur pour éviter les retry loops de PayGate
#         print(f"Erreur dans le callback: {e}")
#         return {"message": "Callback reçu mais erreur de traitement", "status": "error", "error": str(e)}

# # Debug endpoint pour capturer le format exact de PayGate





#     @router.post("/callback-debug")
#     async def payment_callback_debug(request: Request):
#         """Endpoint de debug pour capturer exactement ce que PayGate envoie"""
#         print("=== CALLBACK PAYGATE DEBUG ===")

#     try:
#         # Capturer les headers
#         headers = dict(request.headers)
#         print("Headers:", headers)
#         print("Content-Type:", headers.get('content-type', 'Unknown'))

#         # Capturer le body brut (limité à 2000 caractères pour éviter les logs trop gros)
#         body = await request.body()
#         raw_body = body.decode()[:2000] if body else "Empty"
#         if body and len(body) > 2000:
#             raw_body += "... (tronqué)"
#         print("Raw body:", raw_body)

#         # Déterminer le format et parser en conséquence
#         content_type = headers.get('content-type', '').lower()

#         if 'application/json' in content_type:
#             # Format JSON
#             try:
#                 data_json = await request.json()
#                 print("JSON reçu:", data_json)

#                 # Créer l'objet PayGateCallback à partir du JSON
#                 data = PayGateCallback(**data_json)
#                 print("Data dict:", data.dict())

#                 return {
#                     "message": "Callback debug JSON reçu",
#                     "status": "ok",
#                     "format": "json",
#                     "content_type": content_type,
#                     "payload": data.dict(),
#                     "raw_body": raw_body
#                 }
#             except Exception as e:
#                 print(f"Erreur parsing JSON: {e}")
#                 return {
#                     "message": "Callback reçu mais erreur parsing JSON",
#                     "status": "ok",
#                     "format": "json",
#                     "error": str(e),
#                     "raw_body": raw_body
#                 }

#         elif 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type:
#             # Format Form-Data
#             try:
#                 form_data = await request.form()
#                 print("Form data reçu:", dict(form_data))

#                 # Créer l'objet PayGateCallback à partir du form
#                 data = PayGateCallback(
#                     status=form_data.get('status'),
#                     identifier=form_data.get('identifier'),
#                     tx_reference=form_data.get('tx_reference'),
#                     amount=form_data.get('amount'),
#                     phone_number=form_data.get('phone_number'),
#                     network=form_data.get('network'),
#                     payment_reference=form_data.get('payment_reference'),
#                     datetime=form_data.get('datetime'),
#                     payment_method=form_data.get('payment_method')
#                 )
#                 print("Data dict:", data.dict())

#                 return {
#                     "message": "Callback debug Form-Data reçu",
#                     "status": "ok",
#                     "format": "form-data",
#                     "content_type": content_type,
#                     "payload": data.dict(),
#                     "raw_body": raw_body
#                 }
#             except Exception as e:
#                 print(f"Erreur parsing Form-Data: {e}")
#                 return {
#                     "message": "Callback reçu mais erreur parsing Form-Data",
#                     "status": "ok",
#                     "format": "form-data",
#                     "error": str(e),
#                     "raw_body": raw_body
#                 }

#         else:
#             # Format inconnu
#             print(f"Format inconnu: {content_type}")
#             return {
#                 "message": "Callback reçu - format inconnu détecté",
#                 "status": "ok",
#                 "content_type": content_type,
#                 "raw_body": raw_body,
#                 "headers": headers
#             }

#     except Exception as e:
#         # Catch-all pour éviter tout 500 qui pourrait faire boucler PayGate
#         print(f"Erreur générale dans callback-debug: {e}")
#         return {
#             "message": "Callback reçu mais erreur générale",
#             "status": "ok",
#             "error": str(e)
#         }




# @router.post("/callback")
# async def payment_callback(data: PayGateCallback, request: Request):
#     """Callback PayGate - reçoit la confirmation de paiement et met à jour la facture"""
#     try:
#         print("\n========== CALLBACK PAYGATE REÇU ==========")
#         print(f"⏰ Reçu à: {datetime.utcnow().isoformat()}")
#         print(f"📩 Headers: {dict(request.headers)}")
#         print(f"📦 Payload brut: {await request.body()}")
#         print(f"✅ Données parsées: {data.dict()}")


@router.get("/status/{identifier}")
async def check_status(identifier: str):
    """Vérifier manuellement le statut d'un paiement auprès de PayGate"""
    url = "https://paygateglobal.com/api/v2/status"
    payload = {
        "auth_token": settings.API_KEY_PAYGATE,
        "identifier": identifier
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur PayGate: {str(e)}")

    # Mise à jour de la facture
    facture = await db.factures.find_one({"tx_reference": identifier})
    if facture:
        status_mapping = {
            "0": "payée",
            "2": "en cours",
            "4": "expirée",
            "6": "annulée"
        }

        # Pour les statuts inconnus, utiliser "statut_non_reconnu" au lieu de "erreur"
        # pour éviter de confondre les vrais erreurs avec les statuts non reconnus
        new_status = status_mapping.get(str(result.get("status")), "statut_non_reconnu")
        
        update_data = {"status": new_status, "updated_at": datetime.utcnow()}
        if result.get("tx_reference"):
            update_data["payment_reference"] = result["tx_reference"]
            
        await db.factures.update_one(
            {"_id": facture["_id"]},
            {"$set": update_data}
        )

    return {
        "identifier": identifier,
        "paygate_status": result.get("status"),
        "local_status": new_status if facture else "non trouvé",
        "tx_reference": result.get("tx_reference")
    }

@router.get("/check-balance")
async def check_balance():
    """Vérifier le solde de Flooz et TMoney"""
    url = "https://paygateglobal.com/api/v1/check-balance"
    payload = {
        "auth_token": settings.API_KEY_PAYGATE
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        print(f"Réponse PayGate check-balance: {result}")
    except Exception as e:
        print(f"Erreur lors de la vérification du solde: {e}")
        raise HTTPException(status_code=502, detail=f"Erreur lors de la vérification du solde: {str(e)}")

    return {
        "flooz": result.get("flooz"),
        "tmoney": result.get("tmoney")
    }

@router.get("/local-status/{identifier}")
async def check_local_status(identifier: str):
    """Vérifier le statut local d'un paiement dans la base de données"""
    facture = await db.factures.find_one({"tx_reference": identifier})
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvée")

    return {
        "identifier": identifier,
        "status": facture["status"],
        "amount": facture["amount"],
        "phone_number": facture["phone_number"],
        "network": facture["network"],
        "created_at": facture["created_at"],
        "updated_at": facture["updated_at"]
    }

class MoneyFusionPaymentRequest(BaseModel):
    order_id: str
    phone_number: str
    amount: int
    network: str = "mobile"  # mobile pour MoneyFusion
    client_name: str

# @router.post("/moneyfusion", status_code=status.HTTP_201_CREATED)
# async def create_moneyfusion_payment(
#     payment_data: MoneyFusionPaymentRequest,
#     current_user: UserInDB = Depends(get_current_user)
# ):
#     """Créer un paiement MoneyFusion"""
#     try:
#         # Récupérer les détails de la commande
#         order = await db.orders.find_one({"_id": ObjectId(payment_data.order_id)})
#         if not order:
#             raise HTTPException(status_code=404, detail="Commande non trouvée")

#         # Formater les articles pour MoneyFusion
#         articles = moneyfusion_service.format_articles_from_order(order)

#         # URL de retour après paiement
#         return_url = f"https://yt-adawi-q3qi.vercel.app/payment-confirmation"

#         # Créer le paiement MoneyFusion
#         payment_result = await moneyfusion_service.create_payment(
#             total_price=payment_data.amount,
#             articles=articles,
#             phone_number=payment_data.phone_number,
#             client_name=payment_data.client_name,
#             user_id=current_user.id,
#             order_id=payment_data.order_id,
#             return_url=return_url
#         )

#         if not payment_result.get("statut"):
#             raise HTTPException(status_code=400, detail=payment_result.get("message", "Erreur MoneyFusion"))

#         # Créer la facture dans la base de données
#         facture_data = {
#             "phone_number": payment_data.phone_number,
#             "amount": payment_data.amount,
#             "network": payment_data.network,
#             "tx_reference": payment_result.get("token"),
#             "status": "en attente",
#             "user_id": current_user.id,
#             "order_id": payment_data.order_id,
#             "payment_provider": "moneyfusion",
#             "created_at": datetime.utcnow(),
#             "updated_at": datetime.utcnow()
#         }

#         result = await db.factures.insert_one(facture_data)
#         facture_data["id"] = str(result.inserted_id)

#         return {
#             "identifier": payment_result.get("token"),
#             "payment_url": payment_result.get("url"),
#             "status": "en attente",
#             "facture_id": facture_data["id"]
#         }

#     except Exception as e:
#         print(f"Erreur création paiement MoneyFusion: {e}")
#         raise HTTPException(status_code=400, detail=str(e))
