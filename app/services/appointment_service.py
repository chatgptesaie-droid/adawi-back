"""
Service de gestion des rendez-vous
"""
import logging
from datetime import datetime, timedelta, time, timezone
from typing import List, Optional, Dict, Any
from bson import ObjectId

from app.db.mongo import db
from app.models.appointment import (
    Appointment, AppointmentCreate, AppointmentUpdate,
    AppointmentStatusUpdate
)
from app.models.availability import Availability, AvailableSlot, TimeSlot, DailySchedule
from app.services import email_service
from app.services.notification_service import NotificationService
from app.services.sms_service import send_customer_sms

logger = logging.getLogger(__name__)

class AppointmentService:
    """Service pour gérer les rendez-vous"""

    def __init__(self):
        self.notification_service = NotificationService()

    async def create_appointment(self, appointment_data: AppointmentCreate, user_id: str) -> Appointment:
        """Créer un nouveau rendez-vous"""
        try:
            logger.info(f"Création RDV - User: {user_id}, Date: {appointment_data.appointment_date}")

            # Validation des données d'entrée
            try:
                await self._validate_appointment_data(appointment_data)
                logger.info("Validation OK")
            except Exception as e:
                logger.error(f"Erreur lors de la validation des données: {e}")
                raise ValueError(f"Erreur de validation: {str(e)}")

            # Vérifier la disponibilité du créneau
            try:
                is_available = await self._check_slot_availability(
                    appointment_data.appointment_date,
                    appointment_data.duration_minutes
                )
                logger.info(f"Disponibilité: {is_available}")

                if not is_available:
                    raise ValueError("Créneau non disponible")
            except Exception as e:
                logger.error(f"Erreur lors de la vérification de disponibilité: {e}")
                raise ValueError(f"Erreur de vérification de disponibilité: {str(e)}")

            # Créer le rendez-vous
            try:
                # S'assurer que la date a un timezone UTC
                appointment_date = appointment_data.appointment_date
                if appointment_date.tzinfo is None:
                    appointment_date = appointment_date.replace(tzinfo=timezone.utc)
                
                appointment_dict = appointment_data.dict()
                appointment_dict["appointment_date"] = appointment_date
                
                appointment = Appointment(
                    **appointment_dict,
                    user_id=user_id,
                    created_by=user_id,
                    status_history=[{
                        "status": "en cours",
                        "changed_at": datetime.now(timezone.utc),
                        "changed_by": user_id
                    }]
                )
                logger.info("Objet Appointment créé avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'objet Appointment: {e}")
                raise ValueError(f"Erreur de création d'objet: {str(e)}")

            # Sauvegarder en base (exclure l'id pour laisser MongoDB le générer)
            try:
                appointment_dict = appointment.dict(by_alias=True, exclude={"id"})
                result = await db.appointments.insert_one(appointment_dict)
                appointment.id = str(result.inserted_id)
                logger.info(f"Rendez-vous sauvegardé en base avec ID: {appointment.id}")
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde en base: {e}")
                raise ValueError(f"Erreur de sauvegarde en base: {str(e)}")

            # Créer une notification
            try:
                await self.notification_service.create_notification(
                    user_id=user_id,
                    title="Rendez-vous créé",
                    message=f"Votre rendez-vous pour le {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')} a été créé avec succès.",
                    type="appointment",
                    appointment_id=appointment.id
                )
                logger.info("Notification créée avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de la création de la notification: {e}")
                # Ne pas échouer pour une erreur de notification

            await send_customer_sms(
                appointment.client_phone,
                appointment.client_name,
                f"Votre rendez-vous « {appointment.title} » est enregistré pour le {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')}.",
                occurred_at=appointment.created_at,
                event="appointment.created",
            )

            # Notifier les admins/vendeurs
            try:
                await self._notify_admins_new_appointment(appointment)
                logger.info("Notification admin envoyée")
            except Exception as e:
                logger.error(f"Erreur lors de la notification admin: {e}")
                # Ne pas échouer pour une erreur de notification

            logger.info(f"Rendez-vous créé avec succès: {appointment.id}")
            return appointment

        except ValueError as e:
            # Re-lancer les ValueError (erreurs métier)
            logger.error(f"Erreur métier lors de la création: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la création du rendez-vous: {e}")
            logger.error(f"Type d'erreur: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Erreur interne lors de la création du rendez-vous: {str(e)}")

    async def get_appointments(
        self,
        user_id: Optional[str] = None,
        vendor_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        skip: int = 0
    ) -> List[Appointment]:
        """Récupérer les rendez-vous avec filtres"""
        try:
            query = {}

            if user_id:
                query["user_id"] = user_id
            if vendor_id:
                query["vendor_id"] = vendor_id
            if status:
                query["status"] = status

            if start_date or end_date:
                date_query = {}
                if start_date:
                    # S'assurer que la date de début a un timezone
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                    date_query["$gte"] = start_date
                if end_date:
                    # S'assurer que la date de fin a un timezone
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    date_query["$lte"] = end_date
                query["appointment_date"] = date_query

            appointments = await db.appointments.find(query)\
                .sort("created_at", -1)\
                .skip(skip)\
                .limit(limit)\
                .to_list(length=None)

            # Convertir ObjectId en string pour chaque rendez-vous
            for apt in appointments:
                apt["_id"] = str(apt["_id"])

            return [Appointment(**apt) for apt in appointments]

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des rendez-vous: {e}")
            raise

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        """Récupérer un rendez-vous par ID"""
        try:
            if not ObjectId.is_valid(appointment_id):
                return None

            appointment = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
            if appointment:
                # Convertir ObjectId en string
                appointment["_id"] = str(appointment["_id"])
                return Appointment(**appointment)
            return None
        except Exception as e:
            logger.error(f"Erreur récupération rendez-vous {appointment_id}: {e}")
            return None

    async def update_appointment(
        self,
        appointment_id: str,
        update_data: AppointmentUpdate,
        updated_by: str
    ) -> Optional[Appointment]:
        """Mettre à jour un rendez-vous"""
        try:
            # Récupérer le rendez-vous actuel
            current_appointment = await self.get_appointment_by_id(appointment_id)
            if not current_appointment:
                return None

            # Vérifier les changements de statut
            if update_data.status and update_data.status != current_appointment.status:
                await self._update_appointment_status(
                    appointment_id,
                    update_data.status,
                    updated_by,
                    update_data.vendor_notes or update_data.admin_notes
                )

            # Mettre à jour les données
            update_dict = update_data.dict(exclude_unset=True)
            update_dict["updated_at"] = datetime.now(timezone.utc)

            # Gérer le timezone pour la date de rendez-vous si elle est mise à jour
            if "appointment_date" in update_dict and update_dict["appointment_date"] is not None:
                if update_dict["appointment_date"].tzinfo is None:
                    update_dict["appointment_date"] = update_dict["appointment_date"].replace(tzinfo=timezone.utc)

            await db.appointments.update_one(
                {"_id": ObjectId(appointment_id)},
                {"$set": update_dict}
            )

            # Récupérer et retourner le rendez-vous mis à jour
            updated_appointment = await self.get_appointment_by_id(appointment_id)

            # Créer une notification
            await self._notify_appointment_update(updated_appointment, updated_by)

            return updated_appointment

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du rendez-vous {appointment_id}: {e}")
            raise

    async def update_appointment_status(
        self,
        appointment_id: str,
        status_update: AppointmentStatusUpdate,
        updated_by: str
    ) -> bool:
        """Mettre à jour le statut d'un rendez-vous"""
        try:
            return await self._update_appointment_status(
                appointment_id,
                status_update.status,
                updated_by,
                status_update.notes
            )
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du statut: {e}")
            raise

    async def get_available_slots(
        self,
        start_date: datetime,
        end_date: datetime,
        vendor_id: Optional[str] = None
    ) -> List[AvailableSlot]:
        """Récupérer les créneaux disponibles"""
        try:
            available_slots = []

            # Récupérer la configuration de disponibilité
            availability = await self._get_availability_config(vendor_id)

            current_date = start_date
            while current_date <= end_date:
                day_slots = await self._get_available_slots_for_date(
                    current_date, availability
                )
                available_slots.extend(day_slots)
                current_date += timedelta(days=1)

            return available_slots

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des créneaux disponibles: {e}")
            raise

    async def send_reminder_emails(self):
        """Envoyer les rappels de rendez-vous (à exécuter toutes les heures)"""
        try:
            # Rendez-vous dans les 24 prochaines heures
            now = datetime.now(timezone.utc)
            tomorrow = now + timedelta(hours=24)
            reminder_threshold = now + timedelta(hours=23)  # Pour éviter les doublons

            appointments = await db.appointments.find({
                "appointment_date": {
                    "$gte": reminder_threshold,
                    "$lte": tomorrow
                },
                "status": {"$in": ["en cours", "confirmé"]},
                "reminder_sent": False
            }).to_list(length=None)

            for apt_data in appointments:
                # Convertir ObjectId en string
                apt_data["_id"] = str(apt_data["_id"])
                appointment = Appointment(**apt_data)
                await self._send_appointment_reminder(appointment)

            logger.info(f"Rappels envoyés pour {len(appointments)} rendez-vous")

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi des rappels: {e}")

    # Méthodes privées

    async def _check_slot_availability(
        self,
        appointment_date: datetime,
        duration_minutes: int
    ) -> bool:
        """Vérifier si un créneau est disponible"""
        try:
            # S'assurer que les dates ont un timezone
            if appointment_date.tzinfo is None:
                appointment_date = appointment_date.replace(tzinfo=timezone.utc)
            
            new_start = appointment_date
            new_end = appointment_date + timedelta(minutes=duration_minutes)

            # Vérifier les rendez-vous qui chevauchent
            conflicting_appointments = await db.appointments.find({
                "status": {"$in": ["en cours", "confirmé"]},
                "$or": [
                    {
                        "appointment_date": {"$gte": new_start, "$lt": new_end}
                    },
                    {
                        "$expr": {
                            "$and": [
                                {"$lt": ["$appointment_date", new_end]},
                                {"$gt": [
                                    {"$add": [
                                        "$appointment_date", 
                                        {"$multiply": ["$duration_minutes", 60000]}
                                    ]},
                                    new_start
                                ]}
                            ]
                        }
                    }
                ]
            }).to_list(length=None)

            logger.info(f"Vérification disponibilité pour {new_start} - {new_end}: {len(conflicting_appointments)} conflits trouvés")
            return len(conflicting_appointments) == 0

        except Exception as e:
            logger.error(f"Erreur lors de la vérification de disponibilité: {e}")
            return False

    async def _update_appointment_status(
        self,
        appointment_id: str,
        new_status: str,
        changed_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """Mettre à jour le statut d'un rendez-vous"""
        try:
            # Ajouter à l'historique
            status_change = {
                "status": new_status,
                "changed_at": datetime.now(timezone.utc),
                "changed_by": changed_by
            }
            if notes:
                status_change["notes"] = notes

            await db.appointments.update_one(
                {"_id": ObjectId(appointment_id)},
                {
                    "$set": {
                        "status": new_status,
                        "updated_at": datetime.now(timezone.utc)
                    },
                    "$push": {"status_history": status_change}
                }
            )

            return True

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du statut: {e}")
            return False

    async def _get_availability_config(self, vendor_id: Optional[str] = None) -> Availability:
        """Récupérer la configuration de disponibilité"""
        try:
            # Essayer d'abord la configuration spécifique au vendeur
            if vendor_id:
                availability = await db.availabilities.find_one({
                    "vendor_id": vendor_id,
                    "is_active": True
                })
                if availability:
                    return Availability(**availability)

            # Sinon, configuration globale
            availability = await db.availabilities.find_one({
                "vendor_id": None,
                "is_active": True
            })

            if availability:
                return Availability(**availability)

            # Configuration par défaut si aucune n'existe
            return self._create_default_availability()

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la configuration: {e}")
            return self._create_default_availability()

    async def _get_available_slots_for_date(
        self,
        date: datetime,
        availability: Availability
    ) -> List[AvailableSlot]:
        """Récupérer les créneaux disponibles pour une date donnée"""
        try:
            slots = []
            day_of_week = date.weekday()  # 0=Lundi, 6=Dimanche

            # Vérifier si c'est un jour travaillé
            daily_schedule = None
            for schedule in availability.weekly_schedule:
                if schedule.day_of_week == day_of_week:
                    daily_schedule = schedule
                    break

            if not daily_schedule or not daily_schedule.is_working_day:
                return slots

            # Générer les créneaux horaires
            for time_slot in daily_schedule.time_slots:
                if time_slot.is_available:
                    slot = AvailableSlot(
                        date=date.strftime("%Y-%m-%d"),
                        start_time=time_slot.start_time,
                        end_time=time_slot.end_time,
                        duration_minutes=availability.default_duration,
                        is_available=True
                    )
                    slots.append(slot)

            return slots

        except Exception as e:
            logger.error(f"Erreur lors de la génération des créneaux: {e}")
            return []

    def _create_default_availability(self) -> Availability:
        """Créer une configuration de disponibilité par défaut"""
        weekly_schedule = []

        # Lundi à Vendredi (8h-17h)
        for day in range(5):  # 0-4 = Lundi-Vendredi
            time_slots = []
            current_hour = 8
            end_hour = 17

            while current_hour < end_hour:
                start_time_str = f"{current_hour:02d}:00"
                end_time_str = f"{current_hour + 1:02d}:00"
                time_slots.append(TimeSlot(
                    start_time=start_time_str,
                    end_time=end_time_str,
                    is_available=True
                ))
                current_hour += 1

            weekly_schedule.append(DailySchedule(
                day_of_week=day,
                is_working_day=True,
                time_slots=time_slots,
                break_start="12:00",
                break_end="13:00"
            ))

        # Samedi (8h-12h)
        saturday_slots = []
        current_hour = 8
        end_hour = 12

        while current_hour < end_hour:
            start_time_str = f"{current_hour:02d}:00"
            end_time_str = f"{current_hour + 1:02d}:00"
            saturday_slots.append(TimeSlot(
                start_time=start_time_str,
                end_time=end_time_str,
                is_available=True
            ))
            current_hour += 1

        weekly_schedule.append(DailySchedule(
            day_of_week=5,  # Samedi
            is_working_day=True,
            time_slots=saturday_slots
        ))

        # Dimanche (fermé)
        weekly_schedule.append(DailySchedule(
            day_of_week=6,  # Dimanche
            is_working_day=False,
            time_slots=[]
        ))

        return Availability(
            name="Configuration par défaut",
            weekly_schedule=weekly_schedule,
            created_by="system"
        )

    async def _notify_admins_new_appointment(self, appointment: Appointment):
        """Notifier les vendeurs et admins d'un nouveau rendez-vous"""
        try:
            # Notifier tous les vendeurs et admins via le système de notification interne
            await self.notification_service.notify_new_appointment(appointment.id)
            logger.info(f"Notifications internes créées pour le nouveau rendez-vous {appointment.id}")

            # Garder l'email pour les admins (SMTP_USER)
            import os
            smtp_user = os.getenv("SMTP_USER")
            if smtp_user:
                subject = f"🔔 Nouveau rendez-vous - {appointment.client_name}"
                body = f"""
                Bonjour,

                Un nouveau rendez-vous a été créé :

                👤 Client : {appointment.client_name}
                📧 Email client : {appointment.client_email}
                📅 Date et heure : {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')}
                📍 Service : {appointment.service_type}
                📝 Description : {appointment.description or 'N/A'}
                📍 Lieu : {appointment.location or 'À confirmer'}
                ⏱️ Durée : {appointment.duration_minutes} minutes

                Veuillez vérifier le système d'administration pour plus de détails.

                Cordialement,
                Système de rendez-vous
                """

                await email_service.send_status_email(
                    to_email=smtp_user,
                    subject=subject,
                    body=body
                )
                logger.info(f"Email de notification envoyé à {smtp_user}")
        except Exception as e:
            logger.error(f"Erreur lors de la notification admin: {e}")

    async def _notify_admins_appointment_cancelled(self, appointment: Appointment, cancelled_by: str):
        """Notifier les vendeurs et admins d'une annulation de rendez-vous"""
        try:
            # Créer une notification pour le staff (admin/vendeurs)
            message = f"Rendez-vous annulé : {appointment.title or 'Sans titre'} - {appointment.client_name} le {appointment.appointment_date.strftime('%d/%m/%Y %H:%M')}"

            await self.notification_service.create_notification(
                user_id="staff",
                type="appointment_cancelled",
                message=message,
                appointment_id=appointment.id,
                title="Rendez-vous annulé"
            )
            logger.info(f"Notification d'annulation créée pour le staff")

            # Envoyer aussi un email aux admins
            import os
            smtp_user = os.getenv("SMTP_USER")
            if smtp_user:
                subject = f"❌ Rendez-vous annulé - {appointment.client_name}"
                body = f"""
                Bonjour,

                Un rendez-vous a été annulé :

                👤 Client : {appointment.client_name}
                📧 Email client : {appointment.client_email}
                📅 Date et heure : {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')}
                📍 Service : {appointment.service_type}
                📝 Description : {appointment.description or 'N/A'}
                ⏱️ Durée : {appointment.duration_minutes} minutes
                👤 Annulé par : {cancelled_by}

                Veuillez prendre les mesures nécessaires.

                Cordialement,
                Système de rendez-vous
                """

                await email_service.send_status_email(
                    to_email=smtp_user,
                    subject=subject,
                    body=body
                )
                logger.info(f"Email d'annulation envoyé à {smtp_user}")
        except Exception as e:
            logger.error(f"Erreur lors de la notification d'annulation: {e}")

    async def _notify_appointment_update(self, appointment: Appointment, updated_by: str):
        """Notifier les parties concernées d'une mise à jour"""
        try:
            await self.notification_service.create_notification(
                user_id=appointment.user_id,
                title="Rendez-vous mis à jour",
                message=f"Votre rendez-vous du {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')} a été mis à jour.",
                type="appointment",
                appointment_id=appointment.id
            )

            if appointment.vendor_id:
                await self.notification_service.create_notification(
                    user_id=appointment.vendor_id,
                    title="Rendez-vous mis à jour",
                    message=f"Le rendez-vous du {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')} a été mis à jour.",
                    type="appointment",
                    appointment_id=appointment.id
                )

        except Exception as e:
            logger.error(f"Erreur lors de la notification de mise à jour: {e}")

    async def _send_appointment_reminder(self, appointment: Appointment):
        """Envoyer un rappel de rendez-vous"""
        try:
            await db.appointments.update_one(
                {"_id": ObjectId(appointment.id)},
                {
                    "$set": {
                        "reminder_sent": True,
                        "reminder_sent_at": datetime.now(timezone.utc)
                    }
                }
            )

            subject = f"Rappel de rendez-vous - {appointment.title}"
            body = f"""
            Bonjour {appointment.client_name},

            Ceci est un rappel automatique pour votre rendez-vous :

            📅 Date et heure : {appointment.appointment_date.strftime('%d/%m/%Y à %H:%M')}
            📍 Service : {appointment.service_type}
            📝 Description : {appointment.description or 'N/A'}
            📍 Lieu : {appointment.location or 'À confirmer'}

            Veuillez arriver 10 minutes avant l'heure prévue.

            Cordialement,
            L'équipe Showroom
            """

            await email_service.send_status_email(
                to_email=appointment.client_email,
                subject=subject,
                body=body
            )
            appointment_time = appointment.appointment_date.strftime("%d/%m/%Y à %H:%M")
            await send_customer_sms(
                appointment.client_phone,
                appointment.client_name,
                f"Rappel : votre rendez-vous est prévu le {appointment_time} ({appointment.service_type}).",
                event="appointment.reminder",
            )

            logger.info(f"Rappel envoyé pour le rendez-vous {appointment.id}")

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du rappel: {e}")

    async def _validate_appointment_data(self, appointment_data: AppointmentCreate):
        """Valider les données du rendez-vous"""
        try:
            from datetime import timezone
            
            # S'assurer que la date a un timezone
            appointment_date = appointment_data.appointment_date
            if appointment_date.tzinfo is None:
                appointment_date = appointment_date.replace(tzinfo=timezone.utc)

            now_utc = datetime.now(timezone.utc)
            
            if appointment_date <= now_utc:
                raise ValueError("La date du rendez-vous ne peut pas être dans le passé")

            if appointment_data.duration_minutes <= 0:
                raise ValueError("La durée du rendez-vous doit être positive")

            if appointment_data.duration_minutes > 480:
                raise ValueError("La durée du rendez-vous ne peut pas dépasser 8 heures")

        except Exception as e:
            logger.error(f"Erreur lors de la validation des données: {e}")
            raise