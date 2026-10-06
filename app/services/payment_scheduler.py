"""
Service de planification pour les vérifications de paiement périodiques
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from bson import ObjectId
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.mongo import db
from app.core.config import settings
from app.core.emails_utils import notify_admin_of_new_invoice, send_payment_email
from app.services.order_service import order_service

logger = logging.getLogger(__name__)

class PaymentScheduler:
    """Service de planification pour les vérifications de paiement"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    async def start_scheduler(self):
        """Démarre le planificateur"""
        if not self.is_running:
            # Planifier la vérification des paiements toutes les 50 secondes
            self.scheduler.add_job(
                self.check_pending_payments,
                trigger=IntervalTrigger(seconds=50),
                id='check_pending_payments',
                name='Vérification des paiements en attente',
                replace_existing=True
            )

            self.scheduler.start()
            self.is_running = True
            logger.info("🕐 Planificateur de paiement démarré - vérification toutes les 10 secondes")

    async def stop_scheduler(self):
        """Arrête le planificateur"""
        if self.is_running:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("🕐 Planificateur de paiement arrêté")

    async def check_pending_payments(self):
        """Vérifie le statut des paiements en attente auprès de PayGate"""
        try:
            logger.info("🔍 Début de la vérification des paiements en attente...")

            # Récupérer toutes les factures en attente, en cours, ou avec statut_non_reconnu
            # (y compris les anciens pour rattraper les paiements manqués)
            five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)

            # Récupérer les factures à vérifier
            pending_factures = await db.factures.find({
                "$or": [
                    {"status": {"$in": ["en attente", "en cours"]}},
                    {
                        "status": {"$in": ["statut_non_reconnu", "erreur"]},
                        "updated_at": {"$gte": five_minutes_ago}
                    },
                    # INCLURE les factures "payée" qui ont des commandes avec payment_status "en_attente"
                    # pour corriger les cas où la facture a été mise à jour mais pas la commande
                    {
                        "status": "payée",
                        "order_id": {"$exists": True, "$ne": None}
                    }
                ]
            }).to_list(length=None)

            # Filtrer pour ne garder que les factures "payée" dont la commande n'est pas encore payée
            filtered_factures = []
            for facture in pending_factures:
                if facture.get("status") == "payée" and facture.get("order_id"):
                    # Vérifier si la commande liée a encore payment_status "en_attente"
                    order = await db.orders.find_one({"_id": facture["order_id"]})
                    if order and order.get("payment_status") == "en_attente":
                        logger.info(f"🔍 Facture {facture.get('tx_reference')} payée mais commande {facture['order_id']} en attente - à corriger")
                        filtered_factures.append(facture)
                    # else: commande déjà payée, ignorer cette facture
                else:
                    # Factures en attente normale
                    filtered_factures.append(facture)

            pending_factures = filtered_factures

            logger.info(f"📋 {len(pending_factures)} factures en attente trouvées")

            # Log détaillé des factures trouvées pour debug
            for i, facture in enumerate(pending_factures):
                logger.info(f"📄 Facture {i+1}: tx_reference='{facture.get('tx_reference')}', status='{facture.get('status')}', order_id='{facture.get('order_id')}', age={(datetime.utcnow() - facture.get('created_at')).total_seconds():.1f}s")

            for facture in pending_factures:
                try:
                    await self._check_single_payment(facture)
                    # Petite pause pour éviter de surcharger PayGate
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"❌ Erreur lors de la vérification de la facture {facture.get('tx_reference')}: {e}")

            logger.info("✅ Vérification des paiements terminée")

        except Exception as e:
            logger.error(f"❌ Erreur générale lors de la vérification des paiements: {e}")

    async def _check_single_payment(self, facture: Dict[str, Any]):
        """Vérifie le statut d'un paiement spécifique"""
        identifier = facture.get("tx_reference")
        if not identifier:
            logger.warning(f"⚠️ Facture {facture.get('_id')} sans tx_reference")
            return

        # CAS SPÉCIAL: Si la facture est déjà "payée" mais que la commande n'est pas mise à jour
        # (dû à un callback PayGate ou une mise à jour manuelle), traiter directement comme paiement réussi
        if facture.get("status") == "payée" and facture.get("order_id"):
            logger.info(f"🔄 Facture {identifier} déjà payée - vérification si commande liée doit être mise à jour")

            # Vérifier si la commande liée a encore payment_status "en_attente"
            order = await db.orders.find_one({"_id": facture["order_id"]})
            if order and order.get("payment_status") == "en_attente":
                logger.info(f"🎯 Commande {facture['order_id']} en attente malgré facture payée - correction nécessaire")

                # Simuler un résultat PayGate réussi pour déclencher _handle_successful_payment
                fake_paygate_result = {
                    "status": "0",
                    "tx_reference": facture.get("payment_reference") or identifier
                }

                await self._handle_successful_payment(facture, fake_paygate_result)
                return
            else:
                logger.info(f"ℹ️ Commande {facture['order_id']} déjà mise à jour ou inexistante - rien à faire")
                return

        # Vérifier si la facture est très récente (moins de 30 secondes)
        # pour éviter de l'interroger trop tôt chez PayGate
        created_at = facture.get("created_at")
        if created_at:
            age_seconds = (datetime.utcnow() - created_at).total_seconds()
            if age_seconds < 60:  # Attendre au moins 30 secondes
                logger.debug(f"⏳ Facture {identifier} trop récente ({age_seconds:.1f}s), skip vérification")
                return

        try:
            # Appeler l'API PayGate pour vérifier le statut
            url = "https://paygateglobal.com/api/v2/status"
            payload = {
                "auth_token": settings.API_KEY_PAYGATE,
                "identifier": identifier
            }

            logger.info(f"🔍 Vérification PayGate pour {identifier}...")
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            paygate_status = str(result.get("status", ""))
            logger.info(f"📊 Statut PayGate pour {identifier}: {paygate_status} (réponse complète: {result})")

            # Log détaillé pour diagnostiquer les statuts inconnus
            if paygate_status not in ["0", "2", "4", "6"]:
                logger.warning(f"⚠️ Statut PayGate inconnu: {paygate_status} pour {identifier}")
                logger.warning(f"🔍 Réponse PayGate complète: {result}")
                # Essayer quand même de traiter comme paiement réussi si c'est un statut positif
                if paygate_status in ["00", "000", "1", "3", "200", "201", "202"]:  # Statuts potentiellement positifs
                    logger.info(f"🎯 Tentative de traitement comme paiement réussi malgré statut inconnu: {paygate_status}")
                    paygate_status = "0"  # Forcer comme réussi
                elif paygate_status in ["400", "401", "402", "403", "404"]:  # Statuts d'erreur
                    logger.info(f"❌ Tentative de traitement comme paiement annulé malgré statut inconnu: {paygate_status}")
                    paygate_status = "6"  # Forcer comme annulé
                else:
                    # Pour les statuts vraiment inconnus, ne pas traiter comme paiement réussi
                    # Laisser le statut comme "statut_non_reconnu" pour éviter les faux positifs
                    logger.warning(f"⚠️ Statut {paygate_status} non reconnu, laissé tel quel - pas de traitement automatique")
                    # Ne pas forcer paygate_status = "0"
            else:
                logger.info(f"✅ Statut PayGate reconnu: {paygate_status} pour {identifier}")

            # Mapping des statuts PayGate
            status_mapping = {
                "0": "payée",
                "2": "en cours",
                "4": "expirée",
                "6": "annulée"
            }

            # Pour les statuts inconnus, utiliser "statut_non_reconnu" au lieu de "erreur"
            # pour éviter de confondre les vrais erreurs avec les statuts non reconnus
            new_status = status_mapping.get(paygate_status, "statut_non_reconnu")

            # Gérer les actions selon le nouveau statut AVANT de mettre à jour la facture
            logger.info(f"🔍 Vérification statut PayGate: '{paygate_status}' pour facture {identifier}")

            # Vérifier si c'est un paiement réussi (seulement statut "0")
            is_successful_payment = False
            if paygate_status == "0":
                is_successful_payment = True
                logger.info(f"🎯 PAIEMENT RÉUSSI DÉTECTÉ: paygate_status='{paygate_status}' == '0', is_successful_payment=True")

            logger.info(f"🔍 État final pour {identifier}: paygate_status='{paygate_status}', is_successful_payment={is_successful_payment}, new_status='{new_status}', current_status='{facture.get('status')}'")

            if is_successful_payment:
                logger.info(f"🎯 Paiement réussi détecté pour facture {identifier}, appel de _handle_successful_payment")
                await self._handle_successful_payment(facture, result)
            elif paygate_status == "6":  # Paiement annulé
                logger.info(f"❌ Paiement annulé détecté pour facture {identifier}, annulation de la commande")
                await self._handle_cancelled_payment(facture, result)
            elif new_status != facture.get("status"):
                # Pour les autres changements de statut (expiré, en cours, etc.)
                logger.info(f"📧 Changement de statut détecté pour {identifier}: {facture.get('status')} -> {new_status}")
                await self._handle_status_change(facture, new_status)
            else:
                logger.info(f"ℹ️ Aucun changement nécessaire pour {identifier} (statut identique)")

            # Mettre à jour la facture si le statut a changé
            if new_status != facture.get("status"):
                update_data = {"status": new_status, "updated_at": datetime.utcnow()}

                if result.get("tx_reference"):
                    update_data["payment_reference"] = result["tx_reference"]

                await db.factures.update_one(
                    {"_id": facture["_id"]},
                    {"$set": update_data}
                )

                logger.info(f"✅ Facture {identifier} mise à jour: {facture.get('status')} -> {new_status}")
            else:
                logger.debug(f"ℹ️ Aucun changement pour la facture {identifier}")

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur réseau lors de la vérification de {identifier}: {e}")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification de {identifier}: {e}")

    async def _handle_successful_payment(self, facture: Dict[str, Any], paygate_result: Dict[str, Any]):
        """Gère les actions après un paiement réussi"""
        try:
            # Récupérer l'utilisateur
            user = await db.users.find_one({"_id": ObjectId(facture["user_id"])})
            if not user:
                logger.warning(f"⚠️ Utilisateur {facture['user_id']} non trouvé pour la facture {facture.get('tx_reference')}")
                return

            # Mettre à jour le statut de paiement de la commande liée - FAIRE ÇA EN PREMIER
            logger.info(f"🔍 Vérification commande liée - order_id présent: {'order_id' in facture}, valeur: {facture.get('order_id')}")

            updated_order = None
            if "order_id" in facture and facture["order_id"]:
                logger.info(f"🎯 Commande trouvée: {facture['order_id']}, mise à jour du statut de paiement et du statut de la commande...")
                payment_method = f"{facture.get('network', '').lower()}"
                logger.info(f"💳 Méthode de paiement: {payment_method}")
                logger.info(f"👤 User ID facture: {facture['user_id']}, Order ID: {facture['order_id']}")

                try:
                    # Met à jour le statut de paiement ET le statut de la commande via pay_order
                    updated_order = await order_service.pay_order(
                        facture["order_id"],
                        True,
                        user_id=facture["user_id"],
                        payment_method=payment_method,
                        send_email=False,
                    )

                    if updated_order:
                        logger.info(f"✅ Commande {facture['order_id']} mise à jour avec succès (statut de paiement et statut commande)")
                        logger.info(f"📊 Détails commande mise à jour: payment_status={updated_order.payment_status}, status={updated_order.status}")
                    else:
                        logger.error(f"❌ Échec mise à jour commande {facture['order_id']} - pay_order a retourné None")

                except Exception as e:
                    logger.error(f"❌ Erreur lors de la mise à jour de la commande {facture['order_id']}: {e}")
                    logger.error(f"🔍 Traceback complet: {str(e)}")
            else:
                logger.warning(f"⚠️ Aucune commande liée trouvée pour la facture {facture.get('tx_reference')}")
                logger.warning(f"📋 Contenu facture: {facture}")

            if not facture.get("order_id") or updated_order:
                try:
                    await send_payment_email(
                        email=user.get("email"),
                        amount=facture["amount"],
                        payment_method=facture.get("network", ""),
                        reference=paygate_result.get("tx_reference") or facture.get("tx_reference"),
                        status="réussi"
                    )
                    logger.info(f"✅ Email de confirmation envoyé à {user.get('email')}")
                except Exception as e:
                    logger.error(f"❌ Erreur envoi email client: {e}")
                    logger.warning("⚠️ Mise à jour commande réussie malgré l'erreur email")
            else:
                logger.warning(
                    "Email de succès non envoyé: la mise à jour de la commande %s a échoué",
                    facture.get("order_id"),
                )

            # Envoyer notification admin (ne pas bloquer la mise à jour si ça échoue)
            try:
                await notify_admin_of_new_invoice(
                    db=db,
                    user_name=f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
                    amount=facture["amount"],
                    email=user.get("email"),
                    identifier=facture.get("tx_reference"),
                    status="payée"
                )
                logger.info("✅ Notification admin envoyée")
            except Exception as e:
                logger.error(f"❌ Erreur notification admin: {e}")
                logger.warning("⚠️ Mise à jour commande réussie malgré l'erreur notification admin")

            logger.info(f"🎉 Traitement complet du paiement réussi pour {facture.get('tx_reference')}")

        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement du paiement réussi: {e}")

    async def _handle_cancelled_payment(self, facture: Dict[str, Any], paygate_result: Dict[str, Any]):
        """Gère les actions après un paiement annulé"""
        try:
            # Récupérer l'utilisateur
            user = await db.users.find_one({"_id": ObjectId(facture["user_id"])})
            if not user:
                logger.warning(f"⚠️ Utilisateur {facture['user_id']} non trouvé pour la facture {facture.get('tx_reference')}")
                return

            # Annuler la commande liée - FAIRE ÇA EN PREMIER
            if "order_id" in facture and facture["order_id"]:
                try:
                    await order_service.pay_order(
                        facture["order_id"],
                        False,  # success = False pour annuler
                        user_id=facture["user_id"],
                        send_email=False,
                    )
                    logger.info(f"✅ Commande {facture['order_id']} annulée suite au paiement annulé")
                except Exception as e:
                    logger.error(f"❌ Erreur lors de l'annulation de la commande {facture['order_id']}: {e}")

            # Envoyer email d'annulation au client (ne pas bloquer si ça échoue)
            try:
                await send_payment_email(
                    email=user.get("email"),
                    amount=facture["amount"],
                    payment_method=facture.get("network", ""),
                    reference=paygate_result.get("tx_reference") or facture.get("tx_reference"),
                    status="annulée"
                )
                logger.info(f"✅ Email d'annulation envoyé à {user.get('email')}")
            except Exception as e:
                logger.error(f"❌ Erreur envoi email d'annulation: {e}")
                logger.warning("⚠️ Annulation commande réussie malgré l'erreur email")

            # Envoyer notification admin (ne pas bloquer si ça échoue)
            try:
                await notify_admin_of_new_invoice(
                    db=db,
                    user_name=f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
                    amount=facture["amount"],
                    email=user.get("email"),
                    identifier=facture.get("tx_reference"),
                    status="annulée"
                )
                logger.info("✅ Notification admin d'annulation envoyée")
            except Exception as e:
                logger.error(f"❌ Erreur notification admin d'annulation: {e}")
                logger.warning("⚠️ Annulation commande réussie malgré l'erreur notification admin")

            logger.info(f"🎉 Traitement complet du paiement annulé pour {facture.get('tx_reference')}")

        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement du paiement annulé: {e}")

    async def _handle_status_change(self, facture: Dict[str, Any], new_status: str):
        """Gère les notifications pour changement de statut de facture"""
        try:
            identifier = facture.get("tx_reference")
            logger.info(f"📧 Notification changement statut facture {identifier}: {facture.get('status')} -> {new_status}")

            # Récupérer l'utilisateur
            user = await db.users.find_one({"_id": ObjectId(facture["user_id"])})
            if not user:
                logger.warning(f"⚠️ Utilisateur {facture['user_id']} non trouvé pour la facture {identifier}")
                return

            user_email = user.get("email")
            if not user_email:
                logger.warning(f"⚠️ Email non trouvé pour l'utilisateur {facture['user_id']}")
                return

            # Envoyer notification admin
            try:
                user_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip() or "Utilisateur"
                await notify_admin_of_new_invoice(
                    db=db,
                    user_name=user_name,
                    amount=facture["amount"],
                    email=user_email,
                    identifier=identifier,
                    status=new_status
                )
                logger.info(f"✅ Notification admin envoyée pour changement statut {identifier}")
            except Exception as e:
                logger.error(f"❌ Erreur notification admin: {e}")

            # Envoyer email client selon le statut
            try:
                if new_status == "expirée":
                    await send_payment_email(
                        email=user_email,
                        amount=facture["amount"],
                        payment_method=facture.get("network", ""),
                        reference=identifier,
                        status="expirée"
                    )
                elif new_status == "annulée":
                    await send_payment_email(
                        email=user_email,
                        amount=facture["amount"],
                        payment_method=facture.get("network", ""),
                        reference=identifier,
                        status="annulée"
                    )
                logger.info(f"✅ Email client envoyé pour statut {new_status}")
            except Exception as e:
                logger.error(f"❌ Erreur envoi email client: {e}")

        except Exception as e:
            logger.error(f"❌ Erreur générale lors du traitement du changement de statut: {e}")

# Instance globale du planificateur
payment_scheduler = PaymentScheduler()
