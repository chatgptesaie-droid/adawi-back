import os
from pathlib import Path

import cloudinary
import cloudinary.api
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    credentials = {
        "CLOUDINARY_CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME"),
        "CLOUDINARY_API_KEY": os.getenv("CLOUDINARY_API_KEY"),
        "CLOUDINARY_API_SECRET": os.getenv("CLOUDINARY_API_SECRET"),
    }

    missing = [
        name
        for name, value in credentials.items()
        if not value or value.lower() == "your_api_secret"
    ]
    if missing:
        print("Configuration manquante ou à remplacer : " + ", ".join(missing))
        return 1

    cloudinary.config(
        cloud_name=credentials["CLOUDINARY_CLOUD_NAME"],
        api_key=credentials["CLOUDINARY_API_KEY"],
        api_secret=credentials["CLOUDINARY_API_SECRET"],
    )

    try:
        response = cloudinary.api.ping()
    except Exception as error:
        print(
            f"Connexion Cloudinary : échec ({type(error).__name__}). "
            "Vérifiez les identifiants et la connexion réseau."
        )
        return 1

    status = response.get("status", "réponse reçue") if isinstance(response, dict) else "réponse reçue"
    print(f"Connexion Cloudinary : OK ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())