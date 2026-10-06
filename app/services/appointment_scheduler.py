"""
Scheduler pour les rappels de rendez-vous
"""
import logging
import asyncio
from datetime import datetime, timedelta

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("APScheduler non disponible. Le scheduler de rendez-vous ne fonctionnera pas.")

from app.services.appointment_service import AppointmentService

logger = logging.getLogger(__name__)

class AppointmentScheduler:
    """Scheduler pour gérer les rappels de rendez-vous"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.appointment_service = AppointmentService()
        self.is_running = False

    async def start_scheduler(self):
        """Démarrer le scheduler"""
        try:
            if self.is_running:
                logger.warning("Le scheduler de rendez-vous est déjà en cours d'exécution")
                return

            # Ajouter le job de rappels toutes les heures
            self.scheduler.add_job(
                self._send_reminders_job,
                trigger=IntervalTrigger(hours=1),
                id="appointment_reminders",
                name="Envoi des rappels de rendez-vous",
                max_instances=1,
                replace_existing=True
            )

            # Démarrer le scheduler
            self.scheduler.start()
            self.is_running = True

            logger.info("🕐 Scheduler de rendez-vous démarré - vérification toutes les heures")

        except Exception as e:
            logger.error(f"Erreur lors du démarrage du scheduler de rendez-vous: {e}")
            raise

    async def stop_scheduler(self):
        """Arrêter le scheduler"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("🕐 Scheduler de rendez-vous arrêté")
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt du scheduler: {e}")

    async def _send_reminders_job(self):
        """Job d'envoi des rappels de rendez-vous"""
        try:
            logger.info("🔍 Début de l'envoi des rappels de rendez-vous...")

            await self.appointment_service.send_reminder_emails()

            logger.info("✅ Envoi des rappels terminé")

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi des rappels: {e}")

    async def trigger_manual_reminders(self):
        """Déclencher manuellement l'envoi des rappels (pour les tests)"""
        try:
            logger.info("🔍 Déclenchement manuel des rappels...")
            await self.appointment_service.send_reminder_emails()
            logger.info("✅ Rappels manuels envoyés")
        except Exception as e:
            logger.error(f"Erreur lors des rappels manuels: {e}")
            raise

# Instance globale
appointment_scheduler = AppointmentScheduler()
