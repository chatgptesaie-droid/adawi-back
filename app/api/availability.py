"""
API endpoints pour la gestion des disponibilités et créneaux horaires
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.availability import (
    Availability, AvailabilityCreate, AvailabilityUpdate,
    DailySchedule, TimeSlot, AvailableSlot
)
from app.models.user import UserPublic
from app.services.availability_service import AvailabilityService
# Import exceptions from the service module
from app.services.availability_service import (
    AvailabilityError, ValidationError, DatabaseError, ConfigurationError
)

router = APIRouter()
security = HTTPBearer()

logger = logging.getLogger(__name__)

availability_service = AvailabilityService()

from app.api.auth import get_current_user_dependency

async def get_current_user(user: UserPublic = Depends(get_current_user_dependency)):
    """Récupérer l'utilisateur actuel depuis le token JWT via la vraie logique"""
    # Convertir l'objet UserPublic en dictionnaire pour la compatibilité
    return {
        "id": user.id,  # Already a string in UserPublic model
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,  # Use full_name instead of first_name/last_name
        "is_active": user.is_active
    }

# Routes pour les configurations de disponibilité

@router.post("/availability", response_model=Availability)
async def create_availability(
    availability_data: AvailabilityCreate,
    current_user: dict = Depends(get_current_user)
):
    """Créer une configuration de disponibilité"""
    try:
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(
                status_code=403,
                detail="Seuls les administrateurs et vendeurs peuvent créer des configurations"
            )

        availability = await availability_service.create_availability(
            availability_data,
            current_user["id"]
        )

        return availability

    except HTTPException:
        raise
    except ValidationError as e:
        logger.warning(f"Erreur de validation lors de la création: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Erreur de base de données lors de la création: {e}")
        raise HTTPException(status_code=500, detail="Erreur de base de données")
    except ConfigurationError as e:
        logger.error(f"Erreur de configuration lors de la création: {e}")
        raise HTTPException(status_code=500, detail="Erreur de configuration")
    except AvailabilityError as e:
        logger.error(f"Erreur de disponibilité lors de la création: {e}")
        raise HTTPException(status_code=500, detail="Erreur de service de disponibilité")
    except Exception as e:
        logger.error(f"Erreur inattendue lors de la création de la configuration: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.get("/availability", response_model=List[Availability])
async def get_availabilities(
    active_only: bool = Query(True, description="Uniquement les configurations actives"),
    current_user: dict = Depends(get_current_user)
):
    """Récupérer les configurations de disponibilité"""
    try:
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        availabilities = await availability_service.get_availabilities(
            vendor_id=None,
            active_only=active_only
        )

        return availabilities

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des configurations: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.get("/availability/{availability_id}", response_model=Availability)
async def get_availability(
    availability_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupérer une configuration spécifique"""
    try:
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        availability = await availability_service.get_availability_by_id(availability_id)

        if not availability:
            raise HTTPException(status_code=404, detail="Configuration non trouvée")

        return availability

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la configuration {availability_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.put("/availability/{availability_id}", response_model=Availability)
async def update_availability(
    availability_id: str,
    update_data: AvailabilityUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Mettre à jour une configuration de disponibilité"""
    try:
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        updated_availability = await availability_service.update_availability(
            availability_id,
            update_data,
            current_user["id"]
        )

        if not updated_availability:
            raise HTTPException(status_code=404, detail="Configuration non trouvée")

        return updated_availability

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la configuration {availability_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.delete("/availability/{availability_id}")
async def delete_availability(
    availability_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Supprimer une configuration de disponibilité"""
    try:
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

        success = await availability_service.delete_availability(availability_id)

        if not success:
            raise HTTPException(status_code=404, detail="Configuration non trouvée")

        return {"message": "Configuration supprimée avec succès"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de la configuration {availability_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

# Routes pour les créneaux disponibles

@router.get("/availability/slots", response_model=List[AvailableSlot])
async def get_available_slots(
    start_date: datetime = Query(..., description="Date de début"),
    end_date: datetime = Query(..., description="Date de fin")
):
    """Récupérer les créneaux disponibles pour une période"""
    try:
        # S'assurer que les dates ont un timezone
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        # Limiter la période à 90 jours maximum
        if (end_date - start_date).days > 90:
            raise HTTPException(
                status_code=400,
                detail="La période ne peut pas dépasser 90 jours"
            )

        # La date de début doit être dans le futur
        now_utc = datetime.now(timezone.utc)
        if start_date < now_utc:
            start_date = now_utc

        slots = await availability_service.get_available_slots(
            start_date,
            end_date,
            None
        )

        return slots

    except HTTPException:
        raise
    except ValidationError as e:
        logger.warning(f"Erreur de validation lors de la récupération des créneaux: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConfigurationError as e:
        logger.error(f"Erreur de configuration lors de la récupération des créneaux: {e}")
        raise HTTPException(status_code=500, detail="Erreur de configuration")
    except DatabaseError as e:
        logger.error(f"Erreur de base de données lors de la récupération des créneaux: {e}")
        raise HTTPException(status_code=500, detail="Erreur de base de données")
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des créneaux: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@router.get("/availability/check")
async def check_slot_availability(
    date: datetime = Query(..., description="Date et heure du rendez-vous"),
    duration_minutes: int = Query(60, description="Durée en minutes")
):
    """Vérifier la disponibilité d'un créneau spécifique"""
    try:
        # S'assurer que la date a un timezone
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)

        is_available = await availability_service.check_slot_availability(
            date,
            duration_minutes,
            None
        )

        return {
            "available": is_available,
            "date": date.isoformat(),
            "duration_minutes": duration_minutes
        }

    except ValidationError as e:
        logger.warning(f"Erreur de validation lors de la vérification de disponibilité: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConfigurationError as e:
        logger.error(f"Erreur de configuration lors de la vérification de disponibilité: {e}")
        raise HTTPException(status_code=500, detail="Erreur de configuration")
    except DatabaseError as e:
        logger.error(f"Erreur de base de données lors de la vérification de disponibilité: {e}")
        raise HTTPException(status_code=500, detail="Erreur de base de données")
    except Exception as e:
        logger.error(f"Erreur lors de la vérification de disponibilité: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

# Route pour créer une configuration par défaut

@router.post("/availability/default", response_model=Availability)
async def create_default_availability(
    current_user: dict = Depends(get_current_user)
):
    """Créer une configuration de disponibilité par défaut"""
    try:
        if current_user["role"] not in ["admin", "vendeur"]:
            raise HTTPException(
                status_code=403,
                detail="Seuls les administrateurs et vendeurs peuvent créer des configurations"
            )

        availability = await availability_service.create_default_availability(
            current_user["id"]
        )

        return availability

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la création de la configuration par défaut: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

# Routes pour les templates de planning

@router.get("/availability/templates")
async def get_schedule_templates():
    """Récupérer les templates de planning disponibles"""
    templates = {
        "standard": {
            "name": "Planning Standard",
            "description": "Lundi-Vendredi 8h-17h, Samedi 8h-12h",
            "weekly_schedule": [
                {
                    "day_of_week": 0,
                    "is_working_day": True,
                    "time_slots": [
                        {"start_time": "08:00", "end_time": "09:00", "is_available": True},
                        {"start_time": "09:00", "end_time": "10:00", "is_available": True},
                        {"start_time": "10:00", "end_time": "11:00", "is_available": True},
                        {"start_time": "11:00", "end_time": "12:00", "is_available": True},
                        {"start_time": "13:00", "end_time": "14:00", "is_available": True},
                        {"start_time": "14:00", "end_time": "15:00", "is_available": True},
                        {"start_time": "15:00", "end_time": "16:00", "is_available": True},
                        {"start_time": "16:00", "end_time": "17:00", "is_available": True}
                    ]
                },
                {
                    "day_of_week": 1,
                    "is_working_day": True,
                    "time_slots": [
                        {"start_time": "08:00", "end_time": "09:00", "is_available": True},
                        {"start_time": "09:00", "end_time": "10:00", "is_available": True},
                        {"start_time": "10:00", "end_time": "11:00", "is_available": True},
                        {"start_time": "11:00", "end_time": "12:00", "is_available": True},
                        {"start_time": "13:00", "end_time": "14:00", "is_available": True},
                        {"start_time": "14:00", "end_time": "15:00", "is_available": True},
                        {"start_time": "15:00", "end_time": "16:00", "is_available": True},
                        {"start_time": "16:00", "end_time": "17:00", "is_available": True}
                    ]
                },
                {
                    "day_of_week": 2,
                    "is_working_day": True,
                    "time_slots": [
                        {"start_time": "08:00", "end_time": "09:00", "is_available": True},
                        {"start_time": "09:00", "end_time": "10:00", "is_available": True},
                        {"start_time": "10:00", "end_time": "11:00", "is_available": True},
                        {"start_time": "11:00", "end_time": "12:00", "is_available": True},
                        {"start_time": "13:00", "end_time": "14:00", "is_available": True},
                        {"start_time": "14:00", "end_time": "15:00", "is_available": True},
                        {"start_time": "15:00", "end_time": "16:00", "is_available": True},
                        {"start_time": "16:00", "end_time": "17:00", "is_available": True}
                    ]
                },
                {
                    "day_of_week": 3,
                    "is_working_day": True,
                    "time_slots": [
                        {"start_time": "08:00", "end_time": "09:00", "is_available": True},
                        {"start_time": "09:00", "end_time": "10:00", "is_available": True},
                        {"start_time": "10:00", "end_time": "11:00", "is_available": True},
                        {"start_time": "11:00", "end_time": "12:00", "is_available": True},
                        {"start_time": "13:00", "end_time": "14:00", "is_available": True},
                        {"start_time": "14:00", "end_time": "15:00", "is_available": True},
                        {"start_time": "15:00", "end_time": "16:00", "is_available": True},
                        {"start_time": "16:00", "end_time": "17:00", "is_available": True}
                    ]
                },
                {
                    "day_of_week": 4,
                    "is_working_day": True,
                    "time_slots": [
                        {"start_time": "08:00", "end_time": "09:00", "is_available": True},
                        {"start_time": "09:00", "end_time": "10:00", "is_available": True},
                        {"start_time": "10:00", "end_time": "11:00", "is_available": True},
                        {"start_time": "11:00", "end_time": "12:00", "is_available": True},
                        {"start_time": "13:00", "end_time": "14:00", "is_available": True},
                        {"start_time": "14:00", "end_time": "15:00", "is_available": True},
                        {"start_time": "15:00", "end_time": "16:00", "is_available": True},
                        {"start_time": "16:00", "end_time": "17:00", "is_available": True}
                    ]
                },
                {
                    "day_of_week": 5,
                    "is_working_day": True,
                    "time_slots": [
                        {"start_time": "08:00", "end_time": "09:00", "is_available": True},
                        {"start_time": "09:00", "end_time": "10:00", "is_available": True},
                        {"start_time": "10:00", "end_time": "11:00", "is_available": True},
                        {"start_time": "11:00", "end_time": "12:00", "is_available": True}
                    ]
                },
                {
                    "day_of_week": 6,
                    "is_working_day": False,
                    "time_slots": []
                }
            ]
        }
    }

    return templates