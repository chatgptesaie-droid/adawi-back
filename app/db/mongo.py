from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from app.core.config import settings

# Connexion à MongoDB Atlas avec la configuration centralisée
client = AsyncIOMotorClient(settings.MONGODB_URI)
db = client[settings.MONGODB_DB]

async def ensure_indexes():
    """Créer les index nécessaires"""
    try:
        # Index pour la recherche textuelle sur les produits
        await db.products.create_index([("name", "text"), ("description", "text")])
        
        # Index pour les performances
        await db.products.create_index("category_id")
        await db.products.create_index("vendor_id")
        await db.orders.create_index("user_id")
        await db.orders.create_index("created_at")
        await db.analytics.create_index([("date", 1), ("page", 1)])
        
        # Index pour la sécurité et l'authentification
        await db.users.create_index("email", unique=True)
        await db.users.create_index("locked_until")
        await db.password_resets.create_index("reset_token", unique=True)
        await db.password_resets.create_index("expires_at", expireAfterSeconds=3600)  # Expire après 1 heure
        await db.password_resets.create_index("email")
        
        print("✅ Index MongoDB créés avec succès!")
        return True
    except OperationFailure as e:
        print(f"⚠️  Impossible de créer les index (permissions insuffisantes): {e}")
        print("ℹ️  Les index peuvent être créés manuellement dans MongoDB Atlas")
        return False
    except Exception as e:
        print(f"⚠️  Erreur lors de la création des index: {e}")
        return False

# Fonction d'initialisation pour FastAPI
async def init_db():
    """Initialiser la base de données"""
    success = await ensure_indexes()
    if success:
        print("✅ Base de données initialisée avec index!")
    else:
        print("⚠️  Base de données connectée (index non créés - permissions insuffisantes)")



