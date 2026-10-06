import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# La classe qui lit le header et celle qui contient le résultat
# HTTPBearer = Le lecteur de token, HTTPAuthorizationCredentials = Le résultat
from typing import Optional
from pydantic import BaseModel, Field, validator
from app.models.user import UserCreate, UserPublic, UserLogin, Token
from app.services.user_service import user_service
from app.core.security import create_access_token, get_password_hash
from app.services.email_service_enhanced import send_status_email
from app.core.config import settings
import uuid
from datetime import datetime, timedelta
from app.db.mongo import db

logger = logging.getLogger(__name__)

# Custom exception classes for better error handling
class AuthenticationError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class DatabaseError(Exception):
    def __init__(self, message: str = "Erreur de base de données"):
        self.message = message
        self.status_code = 500
        super().__init__(self.message)

class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        self.status_code = 400
        super().__init__(self.message)

# Helper function for consistent error responses
def create_error_response(error: Exception, default_message: str = "Une erreur inattendue s'est produite") -> dict:
    """Create a standardized error response"""
    if hasattr(error, 'status_code'):
        status_code = error.status_code
        message = error.message
    else:
        status_code = 500
        message = default_message
        logger.error(f"Unexpected error: {error}", exc_info=True)

    return {
        "error": message,
        "status_code": status_code,
        "timestamp": datetime.utcnow().isoformat()
    }

# Enhanced user lookup with error handling
async def safe_get_user_by_email(email: str) -> Optional[dict]:
    """Safely get user by email with proper error handling"""
    try:
        user = await user_service.get_user_by_email(email)
        return user
    except Exception as e:
        logger.error(f"Error retrieving user {email}: {e}")
        raise DatabaseError("Erreur lors de la récupération de l'utilisateur")

# Enhanced password reset with better error handling
async def safe_reset_password_request(email: str) -> dict:
    """Enhanced password reset request with comprehensive error handling"""
    try:
        # Validate email format
        if not email or '@' not in email:
            raise ValidationError("Format d'email invalide")

        # Check if user exists
        user = await safe_get_user_by_email(email)
        if not user:
            # Don't reveal if email exists for security
            logger.info(f"Password reset requested for non-existent email: {email}")
            return {"message": "Si l'email existe, un lien de réinitialisation a été envoyé"}

        # Generate reset token
        reset_token = str(uuid.uuid4())
        expiration = datetime.utcnow() + timedelta(hours=1)

        # Save token with error handling
        try:
            await db.password_resets.insert_one({
                "email": email,
                "reset_token": reset_token,
                "expires_at": expiration,
                "created_at": datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Database error saving reset token for {email}: {e}")
            raise DatabaseError("Erreur lors de la sauvegarde du token de réinitialisation")

        # Send email with error handling
        try:
            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
            subject = "Réinitialisation de votre mot de passe"
            body = f"""
            Bonjour,

            Vous avez demandé à réinitialiser votre mot de passe.
            Cliquez sur le lien suivant pour créer un nouveau mot de passe :

            {reset_link}

            Ce lien expirera dans 1 heure.

            Si vous n'avez pas demandé cette réinitialisation, veuillez ignorer cet email.

            Cordialement,
            L'équipe Showroom
            """

            await send_status_email(email, subject, body)
            logger.info(f"Password reset email sent to {email}")

        except Exception as e:
            logger.error(f"Error sending password reset email to {email}: {e}")
            # Don't fail the request if email fails, but log it

        return {"message": "Si l'email existe, un lien de réinitialisation a été envoyé"}

    except ValidationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in password reset request for {email}: {e}")
        raise DatabaseError("Erreur interne lors de la demande de réinitialisation")

# ___________________________________________________________           
# Enhanced password reset confirmation
async def safe_reset_password(token: str, new_password: str, confirmed_password: str) -> dict:
    """Enhanced password reset confirmation with validation"""
    try:
        # Validate passwords match
        if new_password != confirmed_password:
            raise ValidationError("Les mots de passe ne correspondent pas")

        # Validate password strength
        if len(new_password) < 6:
            raise ValidationError("Le mot de passe doit contenir au moins 6 caractères")

        # Find reset token
        try:
            reset_entry = await db.password_resets.find_one({"reset_token": token})
        except Exception as e:
            logger.error(f"Database error finding reset token: {e}")
            raise DatabaseError("Erreur lors de la vérification du token")

        if not reset_entry:
            raise AuthenticationError("Token invalide", 400)

        if reset_entry["expires_at"] < datetime.utcnow():
            raise AuthenticationError("Token expiré", 400)

        # Update user password
        try:
            hashed_password = get_password_hash(new_password)
            update_result = await db.users.update_one(
                {"email": reset_entry["email"]},
                {"$set": {"hashed_password": hashed_password, "updated_at": datetime.utcnow()}}
            )

            if update_result.modified_count == 0:
                raise DatabaseError("Utilisateur non trouvé ou mise à jour échouée")

        except Exception as e:
            logger.error(f"Database error updating password for {reset_entry['email']}: {e}")
            raise DatabaseError("Erreur lors de la mise à jour du mot de passe")

        # Clean up reset token
        try:
            await db.password_resets.delete_one({"reset_token": token})
        except Exception as e:
            logger.warning(f"Failed to delete reset token {token}: {e}")

        logger.info(f"Password successfully reset for {reset_entry['email']}")
        return {"message": "Votre mot de passe a été réinitialisé avec succès"}

    except ValidationError:
        raise
    except AuthenticationError:
        raise
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in password reset: {e}")
        raise DatabaseError("Erreur interne lors de la réinitialisation du mot de passe")

class ResetPasswordRequest(BaseModel):
    email: str

class ResetPassword(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, description="Nouveau mot de passe (minimum 6 caractères)")
    confirmed_password: str = Field(..., description="Confirmation du nouveau mot de passe")

    @validator('confirmed_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Les mots de passe ne correspondent pas')
        return v

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# ___________________________________________________________
@router.post("/register", response_model=UserPublic)
async def register(user: UserCreate):
    """Inscription d'un nouvel utilisateur."""
    try:
        new_user = await user_service.create_user(user)
        return new_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ___________________________________________________________   
@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin):
    """Connexion d'un utilisateur."""
    user = await user_service.authenticate_user(user_credentials.email, user_credentials.password)
    
    if not user:
        # Vérifier si le compte est verrouillé
        user_data = await user_service.collection.find_one({"email": user_credentials.email})
        if user_data:
            locked_until = user_data.get("locked_until")
            if locked_until and locked_until > datetime.utcnow():
                # Formater la date de déverrouillage
                unlock_time = locked_until.strftime("%H:%M")
                raise HTTPException(
                    status_code=401, 
                    detail=f"Compte verrouillé jusqu'à {unlock_time}"
                )
        
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    try:
        # Créer le token et récupérer le session_id
        access_token, session_id = create_access_token(data={"sub": user.email})
        
        return {
            "access_token": access_token, 
            "token_type": "bearer",
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"Erreur lors de la création du token pour {user_credentials.email}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne lors de la génération du token")

# ___________________________________________________________       
# # FICHIER Core/Auth.py
# async def get_current_user_dependency(  # ← Nom différent !
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ) -> UserPublic:
#     # ... code de validation ...
#     return UserPublic(...)

# # FICHIER auth.py
# from app.api.dependencies import get_current_user_dependency

# @router.get("/me", response_model=UserPublic)
# async def read_users_me(  # ← Nom différent aussi !
#     current_user: UserPublic = Depends(get_current_user_dependency)  # ← Réutilisation !
# ):
#     """Route pour récupérer son profil"""
#     return current_user  # ✅ Plus simple !



@router.get("/me", response_model=UserPublic)
# /me : Une URL standard en API. Signifie "moi" ou "mon profil"
# Quand quelqu'un fait GET /me → ça renvoie ses propres infos
# response_model=UserPublic : On ne renverra QUE les infos publiques (pas le mot de passe, pas les tokens)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
#     Le besoin : Pour savoir QUI est "me", il faut un token
# La solution : FastAPI extrait automatiquement le token du header Authorization

    """Récupère les informations de l'utilisateur connecté."""
    from app.core.security import verify_token
    
    token = credentials.credentials
    payload = verify_token(token)

# Le besoin : Le token est un string crypté, il faut le décoder
# Ce qui se passe : verify_token vérifie la signature, l'expiration, et extrait les données
# Exemple : Le token décodé donne {"sub": "email@example.com", "exp": 123456789}
   
    # Si verify_token renvoie None → le token est invalide

    if payload is None:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    email = payload.get("sub")

    # Si le token est valide, on extrait l'email (qui est le "sujet" du token)

    if email is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    # On cherche l'utilisateur dans la base de données

    user = await user_service.get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")

    # Si l'utilisateur n'est pas trouvé → erreur 401

    return UserPublic(**user.dict())

    # On renvoie les infos de l'utilisateur (sans le mot de passe)
    # user.dict() convertit l'objet DB en dictionnaire

    # UserPublic(**dict) crée une version "publique" (sans mot de passe, etc.)

    # Puis FastAPI convertit ça en JSON pour la réponse

# ___________________________________________________________       
async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)) -> Optional[UserPublic]:
    """Récupère les informations de l'utilisateur connecté (optionnel pour les endpoints publics)."""
    if not credentials:
        return None

    from app.core.security import verify_token

    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        return None

    email = payload.get("sub")
    if email is None:
        return None

    user = await user_service.get_user_by_email(email)
    if user is None:
        return None

    return UserPublic(**user.dict())

# ___________________________________________________________           
async def get_current_user_dependency(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserPublic:
    """Dépendance pour récupérer l'utilisateur actuel (réutilisable par d'autres modules)."""
    from app.core.security import verify_token

    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    email = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    user = await user_service.get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")

    return UserPublic(**user.dict())

# ___________________________________________________________           
@router.post("/reset-password-request")
async def reset_password_request(request: ResetPasswordRequest):
    """Request a password reset."""
    user = await user_service.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    # Generate reset token
    reset_token = str(uuid.uuid4())
    expiration = datetime.utcnow() + timedelta(hours=1)  # Token valid for 1 hour

    # Save token in the database (you may need to create a new collection for this)
    await db.password_resets.insert_one({
        "email": request.email,
        "reset_token": reset_token,
        "expires_at": expiration
    })

    # Send email with reset link
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    subject = "Réinitialisation de votre mot de passe"
    body = f"""
    Bonjour,
    
    Vous avez demandé à réinitialiser votre mot de passe. 
    Cliquez sur le lien suivant pour créer un nouveau mot de passe :
    
    {reset_link}
    
    Ce lien expirera dans 1 heure.
    
    Si vous n'avez pas demandé cette réinitialisation, veuillez ignorer cet email.
    
    Cordialement,
    L'équipe Showroom
    """
    
    await send_status_email(request.email, subject, body)

    return {"message": "Reset link sent to your email"}

# ___________________________________________________________           
@router.post("/reset-password")
async def reset_password(request: ResetPassword):
    """Reset the password using the token."""
    reset_entry = await db.password_resets.find_one({"reset_token": request.token})
    if not reset_entry or reset_entry["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Update user's password
    user = await user_service.get_user_by_email(reset_entry["email"])
    if user:
        hashed_password = get_password_hash(request.new_password)
        await db.users.update_one({"email": reset_entry["email"]}, {"$set": {"hashed_password": hashed_password}})
        # Optionally delete the reset token
        await db.password_resets.delete_one({"reset_token": request.token})

    return {"message": "Your password has been reset successfully"}
@router.get("/session", response_model=dict)
async def get_session_info(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Récupère les informations de session depuis le token."""
    from app.core.security import verify_token
    
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    session_id = payload.get("session_id")
    email = payload.get("sub")
    
    if session_id is None or email is None:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    return {
        "session_id": session_id,
        "email": email
    }