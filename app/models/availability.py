"""
Modèle pour la gestion des disponibilités et créneaux horaires
"""
from datetime import datetime, time
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, validator
from bson import ObjectId

class TimeSlot(BaseModel):
    """Créneau horaire individuel"""
    start_time: str  # Heure de début (ex: "08:00")
    end_time: str    # Heure de fin (ex: "09:00")
    is_available: bool = True
    max_appointments: int = 1  # Nombre maximum de rendez-vous simultanés

    @validator('start_time', 'end_time', pre=True)
    def parse_time(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v

    @property
    def start_time_obj(self) -> time:
        """Retourne l'heure de début comme objet time"""
        hours, minutes = map(int, self.start_time.split(':'))
        return time(hours, minutes)

    @property
    def end_time_obj(self) -> time:
        """Retourne l'heure de fin comme objet time"""
        hours, minutes = map(int, self.end_time.split(':'))
        return time(hours, minutes)

class DailySchedule(BaseModel):
    """Planning journalier"""
    day_of_week: int  # 0=Lundi, 1=Mardi, ..., 6=Dimanche
    is_working_day: bool = True
    time_slots: List[TimeSlot] = Field(default_factory=list)
    break_start: Optional[str] = None  # Début de pause (ex: "12:00")
    break_end: Optional[str] = None    # Fin de pause (ex: "13:00")

    @validator('break_start', 'break_end', pre=True)
    def parse_break_time(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v

    @property
    def break_start_obj(self) -> Optional[time]:
        """Retourne l'heure de début de pause comme objet time"""
        if self.break_start:
            hours, minutes = map(int, self.break_start.split(':'))
            return time(hours, minutes)
        return None

    @property
    def break_end_obj(self) -> Optional[time]:
        """Retourne l'heure de fin de pause comme objet time"""
        if self.break_end:
            hours, minutes = map(int, self.break_end.split(':'))
            return time(hours, minutes)
        return None

class Availability(BaseModel):
    """Configuration des disponibilités"""
    id: Optional[str] = Field(default=None, alias="_id")
    vendor_id: Optional[str] = None  # ID du vendeur (None = configuration globale)
    name: str  # Nom de la configuration (ex: "Planning Standard")

    # Configuration des jours de travail
    weekly_schedule: List[DailySchedule] = Field(default_factory=list)

    # Exceptions et jours spéciaux
    special_dates: Dict[str, List[TimeSlot]] = Field(default_factory=dict)  # "2024-01-01": [time_slots]
    blocked_dates: List[str] = Field(default_factory=list)  # ["2024-01-01", "2024-12-25"]

    # Paramètres généraux
    default_duration: int = 60  # Durée par défaut en minutes
    buffer_time: int = 15  # Temps tampon entre rendez-vous en minutes
    max_advance_booking_days: int = 90  # Nombre maximum de jours à l'avance
    min_advance_booking_hours: int = 24  # Nombre minimum d'heures à l'avance

    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    is_active: bool = True

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class AvailabilityCreate(BaseModel):
    """Modèle pour créer une configuration de disponibilité"""
    vendor_id: Optional[str] = None
    name: str
    weekly_schedule: List[DailySchedule] = Field(default_factory=list)
    special_dates: Dict[str, List[TimeSlot]] = Field(default_factory=dict)
    blocked_dates: List[str] = Field(default_factory=list)
    default_duration: int = 60
    buffer_time: int = 15
    max_advance_booking_days: int = 90
    min_advance_booking_hours: int = 24

class AvailabilityUpdate(BaseModel):
    """Modèle pour mettre à jour une configuration de disponibilité"""
    name: Optional[str] = None
    weekly_schedule: Optional[List[DailySchedule]] = None
    special_dates: Optional[Dict[str, List[TimeSlot]]] = None
    blocked_dates: Optional[List[str]] = None
    default_duration: Optional[int] = None
    buffer_time: Optional[int] = None
    max_advance_booking_days: Optional[int] = None
    min_advance_booking_hours: Optional[int] = None
    is_active: Optional[bool] = None

class AvailableSlot(BaseModel):
    """Créneau disponible pour la réservation"""
    date: str  # Format: "2024-01-15"
    start_time: str  # Format: "08:00"
    end_time: str  # Format: "09:00"
    duration_minutes: int
    is_available: bool
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
