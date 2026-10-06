# Gestion du JWT et de l'ID de session dans la couche Infrastructure

## 1. Création du Token JWT avec ID de session

- La fonction `create_access_token` dans `backend/app/core/security.py` est responsable de la création du token JWT.
- Elle reçoit un dictionnaire `data` contenant les informations à encoder dans le token (ex: user_id, email, rôle).
- Un identifiant unique de session (`session_id`) est généré via `uuid.uuid4()` et ajouté au payload.
- La date d'expiration est calculée selon la configuration (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- Le payload complet (données + session_id + expiration) est encodé en JWT avec la clé secrète et l'algorithme configurés.
- La fonction retourne le token JWT encodé et l'ID de session.

## 2. Vérification et décodage du Token JWT

- La fonction `verify_token` décode le token JWT reçu.
- Elle utilise la clé secrète et l'algorithme pour valider le token.
- Si le token est valide, elle retourne le payload décodé (incluant l'ID de session).
- En cas d'erreur (token invalide, expiré), elle retourne `None`.

## 3. Rôle de l'ID de session

- L'ID de session unique permet d'identifier une session utilisateur spécifique.
- Il peut être utilisé pour gérer la révocation de sessions, le suivi des connexions, ou la gestion des sessions actives.
- L'ID de session est stocké dans le token JWT et peut être extrait lors de la vérification.

## 4. Intégration dans l'Infrastructure Layer

- Ces fonctions sont situées dans la couche Infrastructure (`core/security.py`), car elles gèrent la sécurité fondamentale.
- Elles sont utilisées par la couche API pour authentifier les requêtes entrantes.
- La configuration (clé secrète, algorithme, durée) est centralisée dans `core/config.py`.
- Le hashage des mots de passe est également géré ici, garantissant la sécurité des données sensibles.

## 5. Exemple d'utilisation

```python
# Création d'un token lors de la connexion
token, session_id = create_access_token({"sub": user_id, "email": user_email, "role": user_role})

# Vérification d'un token reçu dans un middleware
payload = verify_token(token)
if payload is None:
    # Token invalide ou expiré
    raise UnauthorizedError()
else:
    # Accès autorisé, récupérer session_id
    session_id = payload.get("session_id")
```

---

Cette gestion robuste du JWT et de l'ID de session assure une authentification sécurisée et un contrôle fin des sessions utilisateur dans votre backend FastAPI.

Si vous souhaitez, je peux vous aider à documenter ou implémenter la gestion des sessions actives ou la révocation de tokens.
