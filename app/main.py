from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.api import auth, products, cart, orders, dashboard, notifications, admin_export, newsletter, contact, support, admin, refunds, inventory, analytics, export, content, admin_content, paiement, appointments, availability, promotions, profile, installments, user_photos
from fastapi import WebSocket, WebSocketDisconnect
from app.services.websocket_service import manager
from app.db.mongo import ensure_indexes
import os
import logging
from app.services.payment_scheduler import payment_scheduler
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Output to console
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Showroom API",
    description="API FastAPI pour Showroom",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configuration CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yt-adawi1.vercel.app", "http://localhost:5173"],  # En production, spécifie les domaines autorisés
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],

)

# Créer le dossier uploads s'il n'existe pas
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)

# Servir les fichiers statiques (images)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Inclusion des routes
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(newsletter.router)
app.include_router(contact.router)
app.include_router(support.router)
app.include_router(admin.router)
app.include_router(admin_export.router)
app.include_router(refunds.router)
app.include_router(inventory.router)
app.include_router(analytics.router)
app.include_router(export.router)
app.include_router(content.router)
app.include_router(admin_content.router)
app.include_router(paiement.router)
app.include_router(appointments.router, tags=["appointments"])
app.include_router(availability.router, tags=["availability"])
app.include_router(promotions.router, tags=["promotions"])
app.include_router(profile.router)
app.include_router(installments.router)
app.include_router(user_photos.router)

# Event handler de démarrage pour initialiser les index MongoDB et les services
@app.on_event("startup")
async def startup_event():
    """Initialisation au démarrage de l'application"""
    logger.info("Démarrage de l'initialisation de l'application...")

    try:
        # Initialiser les index MongoDB
        await ensure_indexes()
        logger.info("✅ Index MongoDB initialisés")
    except Exception as e:
        logger.warning(f"⚠️ Échec de l'initialisation des index MongoDB: {e}")
        logger.warning("L'application continuera sans les index optimisés")

    try:
        # Initialiser la configuration de disponibilité par défaut
        from app.services.availability_service import AvailabilityService
        availability_service = AvailabilityService()
        await availability_service.initialize_default_availability()
        logger.info("✅ Configuration de disponibilité initialisée")
    except Exception as e:
        logger.warning(f"⚠️ Échec de l'initialisation de la disponibilité: {e}")

    try:
        # Démarrer le scheduler de vérification des paiements
        asyncio.create_task(payment_scheduler.start_scheduler())
        logger.info("✅ Scheduler de paiement démarré")
    except Exception as e:
        logger.warning(f"⚠️ Échec du démarrage du scheduler: {e}")

    logger.info("🚀 Application démarrée (même en cas d'erreurs partielles)")

# Le gestionnaire WebSocket est maintenant dans websocket_service.py

@app.websocket("/ws/notifications/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            # On ne reçoit rien du client, on garde la connexion ouverte
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)

@app.get("/")
async def root():
    return {"message": "Bienvenue sur l'API Showroom!"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API Showroom opérationnelle"}

if __name__ == "__main__":
    import uvicorn
    import os
    # Configuration pour déploiement (Render, Heroku, etc.)
    uvicorn.run(
        app, 
        host="0.0.0.0",  # Accepte toutes les connexions
        port=int(os.environ.get("PORT", 8000))  # Port d'environnement
    )