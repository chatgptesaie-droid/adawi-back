import asyncio
import sys
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


async def main() -> int:
    client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=10000,
    )
    try:
        await client.admin.command("ping")
        database = client[settings.MONGODB_DB]
        user_count = await database.users.count_documents({})
        print(f"Connexion MongoDB : OK\nBase : {database.name}\nCollection : users\nNombre d'utilisateurs : {user_count}")
        return 0
    except Exception as error:
        print(
            f"Échec de la vérification ({type(error).__name__}). "
            "Vérifie l'URI MongoDB, les accès Atlas et la connexion réseau."
        )
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
