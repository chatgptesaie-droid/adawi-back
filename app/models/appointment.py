"""
Modèle pour les rendez-vous
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId

class Appointment(BaseModel):
    """Modèle de rendez-vous"""
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str  # ID du client
    vendor_id: Optional[str] = None  # ID du vendeur assigné
    service_type: str  # Type de service (consultation, réparation, etc.)
    title: str  # Titre du rendez-vous
    description: Optional[str] = None  # Description détaillée

    # Date et heure
    appointment_date: datetime  # Date et heure du rendez-vous
    duration_minutes: int = 60  # Durée en minutes

    # Statut
    status: str = "en cours"  # en cours, confirmé, annulé, terminé

    # Informations de contact
    client_name: str
    client_email: str
    client_phone: str

    # Informations de localisation
    location: Optional[str] = None  # Adresse ou lieu du rendez-vous

    # Notes et commentaires
    client_notes: Optional[str] = None
    vendor_notes: Optional[str] = None
    admin_notes: Optional[str] = None

    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str  # ID de l'utilisateur qui a créé le rendez-vous

    # Rappels
    reminder_sent: bool = False
    reminder_sent_at: Optional[datetime] = None

    # Historique des statuts
    status_history: List[dict] = Field(default_factory=list)  # [{"status": "en cours", "changed_at": datetime, "changed_by": user_id}]

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class AppointmentCreate(BaseModel):
    """Modèle pour créer un rendez-vous"""
    service_type: str
    title: str
    description: Optional[str] = None
    appointment_date: datetime
    duration_minutes: int = 60
    client_name: str
    client_email: str
    client_phone: str
    location: str
    client_notes: Optional[str] = None

    @field_validator('service_type', 'title', 'client_name', 'client_email', 'client_phone', 'location')
    @classmethod
    def validate_required_fields(cls, v):
        if not v or not v.strip():
            raise ValueError("Ce champ est obligatoire et ne peut pas être vide")
        return v.strip()

class AppointmentUpdate(BaseModel):
    """Modèle pour mettre à jour un rendez-vous"""
    service_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    appointment_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    status: Optional[str] = None
    vendor_id: Optional[str] = None
    location: Optional[str] = None
    client_notes: Optional[str] = None
    vendor_notes: Optional[str] = None
    admin_notes: Optional[str] = None

class AppointmentStatusUpdate(BaseModel):
    """Modèle pour changer le statut d'un rendez-vous"""
    status: str  # en cours, confirmé, annulé, terminé
    notes: Optional[str] = None  # Raison du changement
