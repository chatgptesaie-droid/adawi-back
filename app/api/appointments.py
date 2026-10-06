"""
API endpoints pour la gestion des rendez-vous
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.appointment import (
    Appointment, AppointmentCreate, AppointmentUpdate,
    AppointmentStatusUpdate
)
from app.models.availability import AvailableSlot
from app.services.appointment_service import AppointmentService
from app.services.availability_service import AvailabilityService
from app.services.email_service_enhanced import send_admin_email
from app.services.sms_service import send_customer_sms

router = APIRouter()
security = HTTPBearer()

logger = logging.getLogger(__name__)

appointment_service = AppointmentService()
availability_service = AvailabilityService()

from app.api.auth import get_current_user as auth_get_current_user

async def get_current_user_override(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Récupérer l'utilisateur actuel depuis le token JWT via la vraie logique"""
    user = await auth_get_current_user(credentials)
    # Convertir l'objet UserPublic en dictionnaire pour la compatibilité
    return {
        "id": str(user.id),  # Convertir en string si c'est un ObjectId
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,  # Use full_name instead of first_name/last_name
        "is_active": user.is_active
    }

# Remplacer la fonction simulée par la vraie fonction d'authentification
get_current_user = get_current_user_override
@router.post("/appointments", response_model=Appointment)
async def create_appointment(
    appointment_data: AppointmentCreate,
    current_user: dict = Depends(get_current_user)
):
    """Créer un nouveau rendez-vous"""
    try:
        print(f"DEBUG: Create appointment request by user: {current_user}")
        logger.debug(f"Creating appointment for user: {current_user['email']}")
        logger.debug(f"Appointment data: {appointment_data.dict()}")

        # Vérifier que la date est dans le futur
        now_utc = datetime.now(timezone.utc)
        appt_date = appointment_data.appointment_date

        logger.debug(f"Current time (UTC): {now_utc}")
        logger.debug(f"Appointment date (original): {appt_date}, tzinfo: {appt_date.tzinfo}")

        # S'assurer que la date a un timezone
        if appt_date.tzinfo is None:
            appt_date = appt_date.replace(tzinfo=timezone.utc)
            logger.debug(f"Appointment date (converted to UTC): {appt_date}")

        if appt_date <= now_utc:
            logger.warning(f"Appointment date in past: {appt_date} <= {now_utc}")
            raise HTTPException(
                status_code=400,
                detail="La date du rendez-vous doit être dans le futur"
            )

        # Vérifier la disponibilité
        logger.debug("Checking slot availability...")
        print("DEBUG: About to check slot availability")
        is_available = await availability_service.check_slot_availability(
            appointment_data.appointment_date,
            appointment_data.duration_minutes,
            None
        )
        print(f"DEBUG: Slot availability result: {is_available}")
        logger.debug(f"Slot available: {is_available}")

        if not is_available:
            raise HTTPException(
                status_code=400,
                detail="Ce créneau n'est pas disponible"
            )

        logger.debug("Creating appointment object...")
        print("DEBUG: About to create appointment")
        appointment = await appointment_service.create_appointment(
            appointment_data,
            current_user["id"]
        )
        print(f"DEBUG: Appointment created: {appointment}")

        logger.info(f"Appointment created successfully: {appointment.id}")
        return appointment

    except ValueError as e:
        logger.error(f"ValueError: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException as he:
        logger.error(f"HTTPException: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.get("/appointments", response_model=List[Appointment])
async def get_appointments(
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    start_date: Optional[datetime] = Query(None, description="Date de début"),
    end_date: Optional[datetime] = Query(None, description="Date de fin"),
    limit: int = Query(50, description="Nombre maximum de résultats"),
    skip: int = Query(0, description="Nombre de résultats à ignorer"),
    current_user: dict = Depends(get_current_user)
):
    """Récupérer les rendez-vous de l'utilisateur"""
    try:
        # Pour les clients, ne montrer que leurs propres rendez-vous
        # Pour les admins/vendeurs, montrer tous les rendez-vous
        user_id = None
        vendor_id = None

        if current_user["role"] == "client":
            user_id = current_user["id"]
        elif current_user["role"] in ["admin", "vendeur"]:
            # Les admins et vendeurs peuvent voir TOUS les rendez-vous
            # Aucun filtrage pour les vendeurs
            pass

        appointments = await appointment_service.get_appointments(
            user_id=user_id,
            vendor_id=vendor_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            skip=skip
        )

        return appointments

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des rendez-vous: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.get("/appointments/{appointment_id}", response_model=Appointment)
async def get_appointment(
    appointment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupérer un rendez-vous spécifique"""
    try:
        appointment = await appointment_service.get_appointment_by_id(appointment_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        # Vérifier les permissions
        if current_user["role"] == "client" and appointment.user_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        return appointment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du rendez-vous {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.put("/appointments/{appointment_id}", response_model=Appointment)
async def update_appointment(
    appointment_id: str,
    update_data: AppointmentUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Mettre à jour un rendez-vous"""
    try:
        # Vérifier que le rendez-vous existe
        appointment = await appointment_service.get_appointment_by_id(appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        # Vérifier les permissions
        if current_user["role"] == "client" and appointment.user_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        # Les clients ne peuvent pas changer certains champs
        if current_user["role"] == "client":
            # Les clients ne peuvent modifier que leurs notes
            client_only_fields = ["client_notes"]
            for field in update_data.dict(exclude_unset=True).keys():
                if field not in client_only_fields:
                    raise HTTPException(
                        status_code=403,
                        detail="Vous ne pouvez modifier que vos notes personnelles"
                    )

        updated_appointment = await appointment_service.update_appointment(
            appointment_id,
            update_data,
            current_user["id"]
        )

        if not updated_appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        return updated_appointment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour du rendez-vous {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.put("/appointments/{appointment_id}/status", response_model=Appointment)
async def update_appointment_status(
    appointment_id: str,
    status_update: AppointmentStatusUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Mettre à jour le statut d'un rendez-vous"""
    try:
        # Vérifier que le rendez-vous existe
        appointment = await appointment_service.get_appointment_by_id(appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        # Vérifier les permissions
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(
                status_code=403,
                detail="Seuls les administrateurs et vendeurs peuvent changer le statut"
            )

        success = await appointment_service.update_appointment_status(
            appointment_id,
            status_update,
            current_user["id"]
        )

        if not success:
            raise HTTPException(status_code=400, detail="Erreur lors de la mise à jour du statut")

        # Récupérer le rendez-vous mis à jour
        updated_appointment = await appointment_service.get_appointment_by_id(appointment_id)

        # Envoyer un email au client pour notifier le changement de statut
        try:
            status_messages = {
                "confirmé": "confirmé",
                "annulé": "annulé",
                "terminé": "marqué comme terminé",
                "en cours": "mis en cours"
            }
            status_text = status_messages.get(status_update.status, status_update.status)

            subject = f"Votre rendez-vous a été {status_text}"
            body = f"""
            Bonjour {updated_appointment.client_name},

            Votre rendez-vous a été {status_text}.

            Détails du rendez-vous :
            - Service : {updated_appointment.service_type}
            - Titre : {updated_appointment.title}
            - Date et heure : {updated_appointment.appointment_date.strftime('%d/%m/%Y %H:%M')}
            - Durée : {updated_appointment.duration_minutes} minutes

            {f"Notes : {status_update.notes}" if status_update.notes else ""}

            Cordialement,
            L'équipe Showroom
            """
            appointment_time = updated_appointment.appointment_date.strftime("%d/%m/%Y à %H:%M")
            await send_customer_sms(
                updated_appointment.client_phone,
                updated_appointment.client_name,
                f"Votre rendez-vous du {appointment_time} a été {status_text}.",
                event="appointment.status_changed",
            )
            await send_admin_email(updated_appointment.client_email, subject, body)
            logger.info(f"Email de notification de changement de statut envoyé au client pour le rendez-vous {appointment_id}")
        except Exception as email_error:
            logger.error(f"Erreur lors de l'envoi de l'email de changement de statut: {email_error}")
            # Ne pas échouer la requête pour autant

        return updated_appointment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour du statut: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.put("/appointments/{appointment_id}/cancel", response_model=Appointment)
async def cancel_appointment(
    appointment_id: str,
    cancel_reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Annuler un rendez-vous (client peut annuler ses propres rendez-vous)"""
    try:
        # Vérifier que le rendez-vous existe
        appointment = await appointment_service.get_appointment_by_id(appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Rendez-vous non trouvé")

        # Vérifier les permissions
        if current_user["role"] == "client" and appointment.user_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Vous ne pouvez annuler que vos propres rendez-vous")

        # Vérifier que le rendez-vous n'est pas déjà terminé ou annulé
        if appointment.status in ["terminé", "annulé"]:
            raise HTTPException(
                status_code=400,
                detail="Ce rendez-vous ne peut pas être annulé car il est déjà terminé ou annulé"
            )

        # Vérifier que le rendez-vous n'est pas dans le passé (avec une tolérance de 1 heure)
        now_utc = datetime.now(timezone.utc)
        if appointment.appointment_date.tzinfo is None:
            appt_date_utc = appointment.appointment_date.replace(tzinfo=timezone.utc)
        else:
            appt_date_utc = appointment.appointment_date

        if appt_date_utc < now_utc - timedelta(hours=1):
            raise HTTPException(
                status_code=400,
                detail="Ce rendez-vous ne peut pas être annulé car il est déjà passé"
            )

        # Créer la mise à jour du statut
        status_update = AppointmentStatusUpdate(
            status="annulé",
            notes=cancel_reason or "Annulé par le client"
        )

        success = await appointment_service.update_appointment_status(
            appointment_id,
            status_update,
            current_user["id"]
        )

        if not success:
            raise HTTPException(status_code=400, detail="Erreur lors de l'annulation du rendez-vous")

        # Récupérer le rendez-vous mis à jour
        updated_appointment = await appointment_service.get_appointment_by_id(appointment_id)

        await send_customer_sms(
            updated_appointment.client_phone,
            updated_appointment.client_name,
            f"Votre rendez-vous « {updated_appointment.title} » du {updated_appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')} a été annulé.",
            event="appointment.cancelled",
        )

        # Notifier les vendeurs/admins de l'annulation
        try:
            await appointment_service._notify_admins_appointment_cancelled(
                updated_appointment,
                current_user["full_name"] or current_user["email"]
            )
            logger.info(f"Notifications d'annulation envoyées pour le rendez-vous {appointment_id}")
        except Exception as notify_error:
            logger.error(f"Erreur lors de l'envoi des notifications d'annulation: {notify_error}")
            # Ne pas échouer la requête pour autant

        return updated_appointment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'annulation du rendez-vous {appointment_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

# Routes pour les créneaux disponibles

@router.get("/availability/slots", response_model=List[AvailableSlot])
async def get_available_slots(
    start_date: datetime = Query(..., description="Date de début"),
    end_date: datetime = Query(..., description="Date de fin"),
    vendor_id: Optional[str] = Query(None, description="ID du vendeur")
):
    """Récupérer les créneaux disponibles"""
    try:
        # Limiter la période à 90 jours maximum
        if (end_date - start_date).days > 90:
            raise HTTPException(
                status_code=400,
                detail="La période ne peut pas dépasser 90 jours"
            )

        # La date de début doit être dans le futur
        if start_date < datetime.utcnow():
            start_date = datetime.utcnow()

        slots = await availability_service.get_available_slots(
            start_date,
            end_date,
            None  # Tous les vendeurs pour les utilisateurs authentifiés
        )

        return slots

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des créneaux: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.get("/availability/check")
async def check_slot_availability(
    date: datetime = Query(..., description="Date et heure du rendez-vous"),
    duration_minutes: int = Query(60, description="Durée en minutes"),
    vendor_id: Optional[str] = Query(None, description="ID du vendeur")
):
    """Vérifier la disponibilité d'un créneau spécifique"""
    try:
        is_available = await availability_service.check_slot_availability(
            date,
            duration_minutes,
            None  # Tous les vendeurs pour les utilisateurs authentifiés
        )

        return {
            "available": is_available,
            "date": date.isoformat(),
            "duration_minutes": duration_minutes
        }

    except Exception as e:
        logger.error(f"Erreur lors de la vérification de disponibilité: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

    # Routes pour les statistiques (admin seulement)

@router.get("/appointments/stats/overview")
async def get_appointments_stats(
    current_user: dict = Depends(get_current_user)
):
    """Récupérer les statistiques des rendez-vous"""
    try:
        print(f"DEBUG: Stats request by user: {current_user}")
        logger.info(f"Stats request by user: {current_user['email']} (role: {current_user['role']})")

        if current_user["role"] not in ["admin", "vendeur"]:  # ← Correction ici
            logger.warning(f"Access denied for user {current_user['email']} with role {current_user['role']}")
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        # Statistiques générales
        logger.info("Fetching appointments for stats...")
        print("DEBUG: About to call appointment_service.get_appointments")
        total_appointments = await appointment_service.get_appointments(limit=1000)
        print(f"DEBUG: Got {len(total_appointments)} appointments")
        logger.info(f"Found {len(total_appointments)} appointments")

        stats = {
            "total": len(total_appointments),
            "by_status": {},
            "by_service_type": {},
            "upcoming": 0,
            "today": 0
        }

        today = datetime.now(timezone.utc).date()  # Utiliser timezone.utc
        tomorrow = today + timedelta(days=1)
        now_utc = datetime.now(timezone.utc)

        logger.info(f"Processing stats for date: {today}")

        for i, appointment in enumerate(total_appointments):
            try:
                # Par statut
                status = appointment.status
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

                # Par type de service
                service = appointment.service_type
                stats["by_service_type"][service] = stats["by_service_type"].get(service, 0) + 1

                # Prochains rendez-vous
                if appointment.appointment_date.tzinfo is None:
                    # Si la date n'a pas de timezone, on l'assume UTC
                    appt_date_utc = appointment.appointment_date.replace(tzinfo=timezone.utc)
                else:
                    appt_date_utc = appointment.appointment_date

                if appt_date_utc >= now_utc:
                    stats["upcoming"] += 1

                # Aujourd'hui
                if appointment.appointment_date.tzinfo is None:
                    # Si la date n'a pas de timezone, on l'assume UTC
                    appointment_date_utc = appointment.appointment_date.replace(tzinfo=timezone.utc)
                else:
                    appointment_date_utc = appointment.appointment_date

                # Convertir en date pour la comparaison
                appt_date_only = appointment_date_utc.date()
                if today <= appt_date_only < tomorrow:
                    stats["today"] += 1

                if i < 5:  # Log first 5 appointments for debugging
                    logger.debug(f"Appointment {i+1}: status={status}, service={service}, date={appointment.appointment_date}, tzinfo={appointment.appointment_date.tzinfo}")

            except Exception as e:
                logger.error(f"Error processing appointment {i}: {e}")
                logger.error(f"Appointment data: {appointment.dict() if hasattr(appointment, 'dict') else appointment}")
                raise

        logger.info(f"Stats calculated: {stats}")
        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des statistiques: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")
