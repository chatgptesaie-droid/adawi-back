"""
Service de gestion des disponibilités et créneaux horaires
"""
import logging
from datetime import datetime, timedelta, time, timezone
from typing import List, Optional
from bson import ObjectId
from bson.errors import InvalidId

from app.db.mongo import db
from app.models.availability import (
    Availability, AvailabilityCreate, AvailabilityUpdate,
    DailySchedule, TimeSlot, AvailableSlot
)

logger = logging.getLogger(__name__)

class AvailabilityError(Exception):
    """Exception de base pour les erreurs de disponibilité"""
    pass

class ValidationError(AvailabilityError):
    """Erreur de validation des données"""
    pass

class DatabaseError(AvailabilityError):
    """Erreur de base de données"""
    pass

class ConfigurationError(AvailabilityError):
    """Erreur de configuration"""
    pass

class AvailabilityService:
    """Service pour gérer les disponibilités"""

    async def create_availability(
        self,
        availability_data: AvailabilityCreate,
        created_by: str
    ) -> Availability:
        """Créer une configuration de disponibilité"""
        try:
            logger.info(f"🔧 Creating availability configuration: {availability_data.name} by {created_by}")

            # Validation des données
            if not availability_data.weekly_schedule:
                raise ValidationError("Le planning hebdomadaire est requis")

            # S'assurer qu'il y a 7 jours dans la semaine
            if len(availability_data.weekly_schedule) != 7:
                raise ValidationError("Le planning doit contenir 7 jours (0-6)")

            # Valider chaque jour
            for i, day_schedule in enumerate(availability_data.weekly_schedule):
                if day_schedule.day_of_week != i:
                    raise ValidationError(f"Le jour {i} a un numéro de jour incorrect: attendu {i}, reçu {day_schedule.day_of_week}")

            availability = Availability(
                **availability_data.dict(),
                created_by=created_by
            )

            logger.debug(f"📝 Availability data: {availability_data.dict()}")

            result = await db.availabilities.insert_one(availability.dict(by_alias=True))
            availability.id = str(result.inserted_id)

            logger.info(f"✅ Configuration de disponibilité créée: {availability.id}")
            return availability

        except ValidationError:
            # Re-lever les erreurs de validation sans modification
            raise
        except Exception as e:
            logger.error(f"❌ Erreur inattendue lors de la création de la configuration: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Traceback complet: {traceback.format_exc()}")
            raise DatabaseError(f"Impossible de créer la configuration de disponibilité: {str(e)}")

    async def get_availabilities(
        self,
        vendor_id: Optional[str] = None,
        active_only: bool = True
    ) -> List[Availability]:
        """Récupérer les configurations de disponibilité"""
        try:
            logger.info(f"🔍 Récupération des configurations de disponibilité (vendor_id: {vendor_id}, active_only: {active_only})")

            query = {}
            if vendor_id:
                query["vendor_id"] = vendor_id
            if active_only:
                query["is_active"] = True

            availabilities = await db.availabilities.find(query)\
                .sort("created_at", -1)\
                .to_list(length=None)

            logger.info(f"✅ {len(availabilities)} configurations trouvées")
            return [Availability(**avail) for avail in availabilities]

        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des configurations: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            raise DatabaseError(f"Impossible de récupérer les configurations de disponibilité: {str(e)}")

    async def get_availability_by_id(self, availability_id: str) -> Optional[Availability]:
        """Récupérer une configuration par ID"""
        try:
            logger.debug(f"🔍 Récupération de la configuration {availability_id}")

            if not availability_id or not availability_id.strip():
                raise ValidationError("L'ID de la configuration est requis")

            try:
                availability = await db.availabilities.find_one({"_id": ObjectId(availability_id)})
            except InvalidId:
                raise ValidationError(f"Format d'ID invalide: {availability_id}")

            if availability:
                logger.debug(f"✅ Configuration trouvée: {availability.get('name', 'N/A')}")
                return Availability(**availability)

            logger.warning(f"⚠️ Configuration non trouvée: {availability_id}")
            return None

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération de la configuration {availability_id}: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            raise DatabaseError(f"Impossible de récupérer la configuration {availability_id}: {str(e)}")

    async def update_availability(
        self,
        availability_id: str,
        update_data: AvailabilityUpdate,
        updated_by: str
    ) -> Optional[Availability]:
        """Mettre à jour une configuration de disponibilité"""
        try:
            logger.info(f"🔧 Mise à jour de la configuration {availability_id} par {updated_by}")

            if not availability_id or not availability_id.strip():
                raise ValidationError("L'ID de la configuration est requis")

            # Vérifier que la configuration existe
            existing = await self.get_availability_by_id(availability_id)
            if not existing:
                raise ValidationError(f"Configuration non trouvée: {availability_id}")

            update_dict = update_data.dict(exclude_unset=True)
            update_dict["updated_at"] = datetime.now(timezone.utc)

            logger.debug(f"📝 Données de mise à jour: {update_dict}")

            try:
                await db.availabilities.update_one(
                    {"_id": ObjectId(availability_id)},
                    {"$set": update_dict}
                )
            except InvalidId:
                raise ValidationError(f"Format d'ID invalide: {availability_id}")

            updated = await self.get_availability_by_id(availability_id)
            logger.info(f"✅ Configuration mise à jour: {updated.name if updated else 'N/A'}")
            return updated

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors de la mise à jour de la configuration {availability_id}: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            raise DatabaseError(f"Impossible de mettre à jour la configuration {availability_id}: {str(e)}")

    async def delete_availability(self, availability_id: str) -> bool:
        """Supprimer une configuration de disponibilité"""
        try:
            logger.info(f"🗑️ Suppression de la configuration {availability_id}")

            if not availability_id or not availability_id.strip():
                raise ValidationError("L'ID de la configuration est requis")

            # Vérifier que la configuration existe
            existing = await self.get_availability_by_id(availability_id)
            if not existing:
                raise ValidationError(f"Configuration non trouvée: {availability_id}")

            # Désactiver plutôt que supprimer pour conserver l'historique
            try:
                await db.availabilities.update_one(
                    {"_id": ObjectId(availability_id)},
                    {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}}
                )
            except InvalidId:
                raise ValidationError(f"Format d'ID invalide: {availability_id}")

            logger.info(f"✅ Configuration désactivée: {existing.name}")
            return True

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors de la suppression de la configuration {availability_id}: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            raise DatabaseError(f"Impossible de supprimer la configuration {availability_id}: {str(e)}")

    async def get_available_slots(
        self,
        start_date: datetime,
        end_date: datetime,
        vendor_id: Optional[str] = None
    ) -> List[AvailableSlot]:
        """Récupérer tous les créneaux disponibles pour une période"""
        try:
            # Validation des dates
            if start_date >= end_date:
                raise ValidationError("La date de début doit être antérieure à la date de fin")

            # S'assurer que les dates d'entrée ont un timezone
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            logger.info(f"🔍 Récupération des créneaux disponibles du {start_date.date()} au {end_date.date()} pour le vendeur {vendor_id}")

            # Récupérer la configuration de disponibilité
            availability = await self._get_active_availability(vendor_id)
            if not availability:
                logger.warning("⚠️ Aucune configuration de disponibilité active trouvée")
                # Créer une configuration par défaut si elle n'existe pas
                await self.initialize_default_availability()
                availability = await self._get_active_availability(vendor_id)
                if not availability:
                    logger.error("❌ Échec de création de la configuration par défaut")
                    raise ConfigurationError("Impossible de récupérer ou créer une configuration de disponibilité")

            logger.info(f"✅ Utilisation de la configuration: {availability.name}")

            available_slots = []
            current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

            while current_date <= end_date:
                logger.debug(f"📅 Traitement de la date: {current_date.strftime('%Y-%m-%d')}")
                day_slots = await self._get_slots_for_date(current_date, availability)
                available_slots.extend(day_slots)
                current_date += timedelta(days=1)

            logger.info(f"✅ {len(available_slots)} créneaux générés au total")
            return available_slots

        except ValidationError:
            raise
        except ConfigurationError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des créneaux: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Traceback complet: {traceback.format_exc()}")
            raise DatabaseError(f"Impossible de récupérer les créneaux disponibles: {str(e)}")

    async def check_slot_availability(
        self,
        date: datetime,
        duration_minutes: int,
        vendor_id: Optional[str] = None
    ) -> bool:
        """Vérifier si un créneau spécifique est disponible"""
        try:
            # Validation des paramètres
            if duration_minutes <= 0:
                raise ValidationError("La durée doit être positive")

            # S'assurer que la date a un timezone
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)

            logger.debug(f"🔍 Vérification de disponibilité pour {date} (durée: {duration_minutes}min)")

            # Vérifier dans la configuration de disponibilité
            availability = await self._get_active_availability(vendor_id)
            if not availability:
                logger.warning("⚠️ Aucune configuration de disponibilité trouvée")
                return False

            # Vérifier si la date est dans les jours travaillés
            day_of_week = date.weekday()
            daily_schedule = None
            for schedule in availability.weekly_schedule:
                if schedule.day_of_week == day_of_week:
                    daily_schedule = schedule
                    break

            if not daily_schedule or not daily_schedule.is_working_day:
                logger.debug(f"📅 Jour non travaillé: {day_of_week}")
                return False

            # Vérifier si l'heure est dans les créneaux disponibles
            slot_available = False
            for time_slot in daily_schedule.time_slots:
                # S'assurer que time_slot est un objet TimeSlot
                if isinstance(time_slot, dict):
                    time_slot = TimeSlot(**time_slot)

                try:
                    # Convertir les chaînes de temps en objets datetime pour la comparaison
                    start_hour, start_minute = map(int, time_slot.start_time.split(':'))
                    end_hour, end_minute = map(int, time_slot.end_time.split(':'))

                    # Créer des datetime avec le même date que le rendez-vous
                    slot_start = datetime.combine(date.date(), time(start_hour, start_minute))
                    slot_end = datetime.combine(date.date(), time(end_hour, end_minute))

                    # Forcer l'utilisation de timezone.utc pour toutes les dates
                    slot_start = slot_start.replace(tzinfo=timezone.utc)
                    slot_end = slot_end.replace(tzinfo=timezone.utc)

                    if slot_start <= date < slot_end:
                        slot_available = time_slot.is_available
                        break
                except ValueError as ve:
                    logger.error(f"❌ Erreur de format de temps: {time_slot.start_time} - {time_slot.end_time}")
                    continue

            if not slot_available:
                logger.debug("⏰ Créneau hors des heures de travail")
                return False

            # Vérifier les conflits avec les rendez-vous existants
            end_time = date + timedelta(minutes=duration_minutes)

            logger.debug(f"🔍 Vérification des conflits de {date} à {end_time}")

            # Requête MongoDB simplifiée
            conflict_count = await db.appointments.count_documents({
                "status": {"$in": ["en cours", "confirmé"]},
                "$or": [
                    {
                        "appointment_date": {"$gte": date, "$lt": end_time}
                    },
                    {
                        "$expr": {
                            "$and": [
                                {"$lt": ["$appointment_date", end_time]},
                                {"$gt": [
                                    {"$add": [
                                        "$appointment_date",
                                        {"$multiply": ["$duration_minutes", 60000]}
                                    ]},
                                    date
                                ]}
                            ]
                        }
                    }
                ]
            })

            is_available = conflict_count == 0
            logger.debug(f"📊 {conflict_count} conflits trouvés - Disponible: {is_available}")
            return is_available

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification de disponibilité: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            # Pour cette méthode, on retourne False en cas d'erreur plutôt que lever une exception
            return False

    async def create_default_availability(self, created_by: str) -> Availability:
        """Créer une configuration de disponibilité par défaut"""
        try:
            logger.info(f"🔧 Création de la configuration par défaut par {created_by}")

            default_data = AvailabilityCreate(
                name="Configuration par défaut",
                weekly_schedule=self._create_default_weekly_schedule(),
                default_duration=60,
                buffer_time=15,
                max_advance_booking_days=90,
                min_advance_booking_hours=24
            )

            availability = await self.create_availability(default_data, created_by)
            logger.info(f"✅ Configuration par défaut créée: {availability.id}")
            return availability

        except ValidationError:
            raise
        except DatabaseError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors de la création de la configuration par défaut: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            raise DatabaseError(f"Impossible de créer la configuration par défaut: {str(e)}")

    async def initialize_default_availability(self):
        """Créer une configuration par défaut si elle n'existe pas"""
        try:
            logger.debug("🔍 Vérification de l'existence d'une configuration par défaut")

            existing = await db.availabilities.find_one({"vendor_id": None, "is_active": True})
            if not existing:
                logger.info("📝 Aucune configuration par défaut trouvée, création en cours...")
                await self.create_default_availability("system")
                logger.info("✅ Configuration de disponibilité par défaut créée")
            else:
                logger.debug("✅ Configuration par défaut déjà existante")

        except Exception as e:
            logger.error(f"❌ Erreur lors de l'initialisation de la configuration par défaut: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            raise DatabaseError(f"Impossible d'initialiser la configuration par défaut: {str(e)}")

    # Méthodes privées

    async def _get_active_availability(self, vendor_id: Optional[str] = None) -> Optional[Availability]:
        """Récupérer la configuration de disponibilité active"""
        try:
            logger.debug(f"🔍 Recherche de configuration active (vendor_id: {vendor_id})")

            # Essayer d'abord la configuration spécifique au vendeur
            if vendor_id:
                availability = await db.availabilities.find_one({
                    "vendor_id": vendor_id,
                    "is_active": True
                })
                if availability:
                    logger.debug(f"✅ Configuration vendeur trouvée: {availability.get('name', 'N/A')}")
                    return Availability(**availability)

            # Sinon, configuration globale
            availability = await db.availabilities.find_one({
                "vendor_id": None,
                "is_active": True
            })

            if availability:
                logger.debug(f"✅ Configuration globale trouvée: {availability.get('name', 'N/A')}")
                return Availability(**availability)

            logger.warning("⚠️ Aucune configuration active trouvée")
            return None

        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération de la configuration active: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            logger.error(f"❌ Vendor ID: {vendor_id}")
            return None

    async def _get_slots_for_date(
        self,
        date: datetime,
        availability: Availability
    ) -> List[AvailableSlot]:
        """Générer les créneaux disponibles pour une date spécifique"""
        try:
            slots = []
            day_of_week = date.weekday()
            date_str = date.strftime("%Y-%m-%d")

            logger.debug(f"📅 Génération des créneaux pour {date_str} (jour {day_of_week})")

            # Vérifier si c'est un jour spécial
            if date_str in availability.blocked_dates:
                logger.debug(f"🚫 Date bloquée: {date_str}")
                return slots

            # Utiliser les créneaux spéciaux si disponibles
            if date_str in availability.special_dates:
                special_slots = availability.special_dates[date_str]
                logger.debug(f"📅 Utilisation des créneaux spéciaux pour {date_str}: {len(special_slots)} créneaux")

                for time_slot in special_slots:
                    try:
                        # S'assurer que time_slot est un objet TimeSlot
                        if isinstance(time_slot, dict):
                            time_slot = TimeSlot(**time_slot)

                        if time_slot.is_available:
                            slot = AvailableSlot(
                                date=date_str,
                                start_time=time_slot.start_time,
                                end_time=time_slot.end_time,
                                duration_minutes=availability.default_duration,
                                is_available=True
                            )
                            slots.append(slot)
                    except Exception as e:
                        logger.error(f"❌ Erreur lors du traitement du créneau spécial: {e}")
                        logger.error(f"❌ Type d'erreur: {type(e).__name__}")
                        continue

                return slots

            # Utiliser le planning hebdomadaire
            daily_schedule = None
            for schedule in availability.weekly_schedule:
                if schedule.day_of_week == day_of_week:
                    daily_schedule = schedule
                    break

            if not daily_schedule or not daily_schedule.is_working_day:
                logger.debug(f"📅 Jour non travaillé: {day_of_week}")
                return slots

            logger.debug(f"📅 Génération des créneaux pour le jour {day_of_week}")

            # Générer les créneaux horaires
            for time_slot in daily_schedule.time_slots:
                try:
                    # S'assurer que time_slot est un objet TimeSlot
                    if isinstance(time_slot, dict):
                        time_slot = TimeSlot(**time_slot)

                    if time_slot.is_available:
                        # Convertir les chaînes de temps en objets datetime pour la vérification des conflits
                        start_hour, start_minute = map(int, time_slot.start_time.split(':'))
                        slot_datetime = datetime.combine(date.date(), time(start_hour, start_minute))

                        # Forcer l'utilisation de timezone.utc pour toutes les dates
                        slot_datetime = slot_datetime.replace(tzinfo=timezone.utc)

                        is_available = await self._check_slot_conflicts(
                            slot_datetime,
                            availability.default_duration
                        )

                        slot = AvailableSlot(
                            date=date_str,
                            start_time=time_slot.start_time,
                            end_time=time_slot.end_time,
                            duration_minutes=availability.default_duration,
                            is_available=is_available
                        )
                        slots.append(slot)
                except ValueError as ve:
                    logger.error(f"❌ Erreur de format de temps: {time_slot.start_time} - {time_slot.end_time}")
                    logger.error(f"❌ Valeur invalide: {ve}")
                    continue
                except Exception as e:
                    logger.error(f"❌ Erreur lors du traitement du créneau: {e}")
                    logger.error(f"❌ Type d'erreur: {type(e).__name__}")
                    continue

            logger.debug(f"✅ {len(slots)} créneaux générés pour {date_str}")
            return slots

        except Exception as e:
            logger.error(f"❌ Erreur lors de la génération des créneaux pour {date}: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            logger.error(f"❌ Date: {date}, Availability: {availability.name if availability else 'None'}")
            return []

    async def _check_slot_conflicts(self, slot_datetime: datetime, duration_minutes: int) -> bool:
        """Vérifier les conflits pour un créneau spécifique"""
        try:
            # S'assurer que le datetime a un timezone
            if slot_datetime.tzinfo is None:
                slot_datetime = slot_datetime.replace(tzinfo=timezone.utc)

            end_time = slot_datetime + timedelta(minutes=duration_minutes)

            logger.debug(f"🔍 Vérification des conflits pour le créneau: {slot_datetime} à {end_time}")

            # Requête MongoDB simplifiée
            conflict_count = await db.appointments.count_documents({
                "status": {"$in": ["en cours", "confirmé"]},
                "$or": [
                    {
                        "appointment_date": {"$gte": slot_datetime, "$lt": end_time}
                    },
                    {
                        "$expr": {
                            "$and": [
                                {"$lt": ["$appointment_date", end_time]},
                                {"$gt": [
                                    {"$add": [
                                        "$appointment_date",
                                        {"$multiply": ["$duration_minutes", 60000]}
                                    ]},
                                    slot_datetime
                                ]}
                            ]
                        }
                    }
                ]
            })

            is_available = conflict_count == 0
            logger.debug(f"📊 {conflict_count} conflits trouvés - Disponible: {is_available}")
            return is_available

        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification des conflits: {e}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            logger.error(f"❌ Slot datetime: {slot_datetime}, Duration: {duration_minutes}")
            # En cas d'erreur, on considère qu'il y a un conflit pour être prudent
            return False

    def _create_default_weekly_schedule(self) -> List[DailySchedule]:
        """Créer un planning hebdomadaire par défaut"""
        weekly_schedule = []

        # Lundi à Samedi (8h-19h sans interruption)
        for day in range(6):  # 0-5 = Lundi-Samedi
            time_slots = []

            # Créneaux horaires de 8h à 19h
            current_hour = 8
            while current_hour < 19:
                start_time_str = f"{current_hour:02d}:00"
                end_time_str = f"{current_hour + 1:02d}:00"
                time_slots.append(TimeSlot(
                    start_time=start_time_str,
                    end_time=end_time_str,
                    is_available=True,
                    max_appointments=50
                ))
                current_hour += 1

            weekly_schedule.append(DailySchedule(
                day_of_week=day,
                is_working_day=True,
                time_slots=time_slots
            ))

        # Dimanche (fermé)
        weekly_schedule.append(DailySchedule(
            day_of_week=6,  # Dimanche
            is_working_day=False,
            time_slots=[]
        ))

        return weekly_schedule
