# 🏗️ Architecture Logicielle - Plateforme E-commerce Showroom

## 📋 Vue d'ensemble

La plateforme **Showroom** est une solution e-commerce complète construite avec une architecture moderne en microservices, utilisant FastAPI pour le backend, React/TypeScript pour le frontend, et MongoDB comme base de données principale.

---

## 🏛️ Architecture Générale

### Pattern Architectural
```
┌─────────────────  ┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend        │    │   Backend API   │    │   Base de       │
│   React/TypeScript│◄──►│   FastAPI       │◄──►│   Données       │
│   (SPA)           │    │   (REST + WS)   │    │   MongoDB       │
└─────────────────  ┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────────┐
                    │ Services Externes   │
                    │ • PayGate           │
                    │ • MoneyFusion       │
                    │ • Email Service     │
                    │ • File Storage      │
                    └─────────────────────┘
```

### Architecture en Couches (Backend)

```
       ┌─────────────────────────────────────────┐
       │           API Layer (Routes)            │
       │  • Contrôleurs REST                     │
       │  • Validation des entrées               │
       │  • Gestion des réponses                 │
       │  • Authentification middleware          │
       └─────────────────────────────────────────┘
                     │
       ┌─────────────────────────────────────────┐
       │        Service Layer (Business)         │
       │  • Logique métier                       │
       │  • Orchestration des opérations         │
       │  • Intégrations externes                │
       │  • Notifications et emails              │
       └─────────────────────────────────────────┘
                     │
       ┌─────────────────────────────────────────┐
       │         Data Layer (Modèles)            │
       │  • Modèles Pydantic (validation)        │
       │  • Schémas MongoDB                      │
       │  • DTOs (Data Transfer Objects)         │
       └─────────────────────────────────────────┘
                     │
       ┌─────────────────────────────────────────┐
       │       Infrastructure Layer              │
       │  • Connexion MongoDB (Motor)            │
       │  • Configuration centralisée            │
       │  • Sécurité (JWT, hashage)              │
       │  • Cache et sessions                    │
       └─────────────────────────────────────────┘
       ```

---

## 🔧 Technologies & Frameworks

### Backend (Python)
| Composant | Technologie | Version | Rôle |
|-----------|-------------|---------|------|
| **Framework Web** | FastAPI | 0.104+ | API REST + WebSocket + OpenAPI |
| **Base de données** | MongoDB | Atlas | NoSQL document-oriented |
| **Driver MongoDB** | Motor | Async | Client async MongoDB |
| **Validation** | Pydantic | v2 | Data validation & serialization |
| **Authentification** | JWT | HS256 | Tokens sécurisés |
| **Sécurité** | PassLib + bcrypt | - | Hashage mots de passe |
| **Emails** | smtplib + Jinja2 | - | Templates emails |
| **WebSocket** | FastAPI WebSocket | - | Temps réel |
| **Configuration** | python-dotenv | - | Variables d'environnement |

### Frontend (JavaScript/TypeScript)
| Composant | Technologie | Version | Rôle |
|-----------|-------------|---------|------|
| **Framework** | React | 18+ | UI Components |
| **Language** | TypeScript | 5+ | Type safety |
| **Routing** | React Router | 6+ | Navigation SPA |
| **State** | React Hooks + Context | - | State management |
| **HTTP Client** | Axios/Fetch | - | API calls |
| **Styling** | CSS Modules/Tailwind | - | UI styling |
| **Build** | Vite | - | Development & build |

### Infrastructure
| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **Serveur** | Uvicorn | ASGI server |
| **Base de données** | MongoDB Atlas | Cloud database |
| **Cache** | Redis (optionnel) | Session & cache |
| **File Storage** | Local/Cloud | Images produits |
| **Email** | SMTP/Gmail | Notifications |
| **Monitoring** | Logs + Health checks | Observabilité |

---

## 📁 Structure du Projet

### Backend Structure
```
backend/
├── app/
│   ├── api/                     # 🛣️ Routes & Contrôleurs
│   │   ├── __init__.py
│   │   ├── auth.py             # 🔐 Authentification
│   │   ├── products.py         # 📦 Produits & Catégories
│   │   ├── cart.py             # 🛒 Panier d'achat
│   │   ├── orders.py           # 📋 Commandes & Suivi
│   │   ├── dashboard.py        # 📊 Dashboards
│   │   ├── notifications.py    # 🔔 Notifications
│   │   ├── paiement.py         # 💳 Paiements (PayGate)
│   │   ├── support.py          # 🎫 Support & Tickets
│   │   ├── refunds.py          # 💸 Remboursements
│   │   ├── analytics.py        # 📈 Analytics
│   │   ├── content.py          # 📄 CMS Public
│   │   ├── admin_content.py    # 👑 CMS Admin
│   │   └── export.py           # 📊 Export CSV
│   │
│   ├── core/                   # ⚙️ Configuration Centrale
│   │   ├── __init__.py
│   │   ├── config.py           # Variables d'environnement
│   │   ├── security.py         # JWT & Sécurité
│   │   └── emails_utils.py     # Templates emails
│   │
│   ├── db/                     # 🗄️ Base de Données
│   │   ├── __init__.py
│   │   └── mongo.py            # Connexion MongoDB
│   │
│   ├── models/                 # 📋 Modèles de Données
│   │   ├── __init__.py
│   │   ├── user.py             # 👤 Utilisateurs
│   │   ├── product.py          # 📦 Produits
│   │   ├── order.py            # 📋 Commandes
│   │   ├── cart.py             # 🛒 Panier
│   │   ├── support.py          # 🎫 Support
│   │   ├── refund.py           # 💸 Remboursements
│   │   ├── analytics.py        # 📈 Analytics
│   │   ├── content.py          # 📄 CMS
│   │   ├── dashboard.py        # 📊 Dashboard
│   │   └── facture.py          # 🧾 Factures
│   │
│   ├── services/               # 🔧 Logique Métier
│   │   ├── __init__.py
│   │   ├── user_service.py     # 👤 Gestion utilisateurs
│   │   ├── product_service.py  # 📦 Gestion produits
│   │   ├── order_service.py    # 📋 Gestion commandes
│   │   ├── cart_service.py     # 🛒 Gestion panier
│   │   ├── dashboard_service.py# 📊 Service dashboard
│   │   ├── email_service.py    # 📧 Service emails
│   │   ├── notification_service.py # 🔔 Notifications
│   │   ├── support_service.py  # 🎫 Service support
│   │   ├── refund_service.py   # 💸 Service remboursements
│   │   ├── analytics_service.py# 📈 Service analytics
│   │   ├── content_service.py  # 📄 Service CMS
│   │   ├── admin_service.py    # 👑 Service admin
│   │   ├── moneyfusion_service.py # 💳 MoneyFusion
│   │   └── websocket_service.py # 🔌 WebSocket
│   │
│   └── main.py                 # 🚀 Point d'entrée FastAPI
│
├── tests/                      # 🧪 Tests
├── uploads/                    # 📁 Fichiers uploadés
├── requirements.txt            # 📦 Dépendances
├── .env                        # 🔐 Variables d'environnement
├── start_server.py            # 🚀 Script de démarrage
└── README.md                   # 📖 Documentation
```

### Frontend Structure (yt-adawi/)
```
frontend/
├── public/                     # 📁 Assets statiques
├── src/
│   ├── components/             # 🧩 Composants réutilisables
│   │   ├── common/            # Composants génériques
│   │   ├── forms/             # Formulaires
│   │   ├── layout/            # Layout & navigation
│   │   └── ui/                # Composants UI de base
│   │
│   ├── pages/                 # 📄 Pages principales
│   │   ├── auth/              # 🔐 Authentification
│   │   ├── products/          # 📦 Produits
│   │   ├── cart/              # 🛒 Panier
│   │   ├── orders/            # 📋 Commandes
│   │   ├── dashboard/         # 📊 Dashboard
│   │   ├── support/           # 🎫 Support
│   │   └── admin/             # 👑 Administration
│   │
│   ├── services/              # 🔧 Services API
│   │   ├── api.ts             # Client HTTP
│   │   ├── auth.ts            # Authentification
│   │   └── websocket.ts       # WebSocket
│   │
│   ├── hooks/                 # 🎣 Hooks React personnalisés
│   ├── utils/                 # 🛠️ Utilitaires
│   ├── types/                 # 📋 Types TypeScript
│   ├── context/               # 🌐 Context React
│   └── App.tsx                # 🚀 Composant principal
│
├── package.json               # 📦 Dépendances
├── tsconfig.json              # ⚙️ Configuration TypeScript
├── vite.config.ts             # ⚙️ Configuration Vite
└── index.html                 # 📄 Point d'entrée HTML
```

---

## 🔐 Système d'Authentification & Autorisation

### Architecture de Sécurité
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client        │    │   JWT Token     │    │   API Routes    │
│   (Frontend)    │───►│   (Bearer)      │───►│   (Protected)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │   Middleware        │
                    │ • Vérification JWT  │
                    │ • Extraction user   │
                    │ • Vérification rôle │
                    └─────────────────────┘
```

### Rôles & Permissions
| Rôle | Permissions | Description |
|------|-------------|-------------|
| **Client** | `read:own_data` | Utilisateur standard |
| **Vendeur** | `read:own_products`, `write:products` | Gestion de ses produits |
| **Admin** | `read:all`, `write:all` | Accès complet |

### Flux d'Authentification
1. **Inscription** → Validation email → Hashage password → Création user
2. **Connexion** → Vérification credentials → Génération JWT → Retour token
3. **Accès protégé** → Vérification token → Extraction user → Autorisation

---

## 🗄️ Modèle de Données (MongoDB)

### Collections Principales
```javascript
// Utilisateurs
{
  "_id": ObjectId("..."),
  "email": "user@example.com",
  "hashed_password": "...",
  "full_name": "John Doe",
  "role": "client", // client, vendeur, admin
  "is_active": true,
  "created_at": ISODate("..."),
  "failed_login_attempts": 0,
  "locked_until": null
}

// Produits
{
  "_id": ObjectId("..."),
  "name": "Produit A",
  "description": "...",
  "price": 29.99,
  "cost_price": 15.00, // Phase 7
  "stock": 100,
  "low_stock_threshold": 10,
  "category_id": ObjectId("..."),
  "seller_id": ObjectId("..."),
  "images": ["url1.jpg", "url2.jpg"],
  "is_active": true
}

// Commandes
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "items": [
    {
      "product_id": ObjectId("..."),
      "name": "Produit A",
      "price": 29.99,
      "quantity": 2
    }
  ],
  "total": 59.98,
  "status": "en_cours", // en_cours, expediee, livree, annulee
  "payment_status": "effectue",
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

### Index MongoDB
```javascript
// Index de performance
db.users.createIndex({ "email": 1 }, { unique: true });
db.products.createIndex({ "category_id": 1 });
db.products.createIndex({ "seller_id": 1 });
db.orders.createIndex({ "user_id": 1 });
db.orders.createIndex({ "created_at": 1 });
db.orders.createIndex({ "status": 1 });
db.analytics.createIndex({ "date": 1, "page": 1 });
```

---

## 🔌 APIs & Endpoints

### Architecture REST
```
HTTP Method │ Endpoint Pattern          │ Description
────────────┼───────────────────────────┼────────────────────────────
GET         │ /api/resource             │ Liste des ressources
GET         │ /api/resource/{id}        │ Détail d'une ressource
POST        │ /api/resource             │ Créer une ressource
PUT         │ /api/resource/{id}        │ Modifier une ressource
DELETE      │ /api/resource/{id}        │ Supprimer une ressource
```

### Endpoints Principaux
| Module | Endpoint | Method | Description |
|--------|----------|--------|-------------|
| **Auth** | `/auth/login` | POST | Connexion utilisateur |
| | `/auth/register` | POST | Inscription |
| | `/auth/me` | GET | Profil utilisateur |
| **Produits** | `/products/` | GET | Liste produits |
| | `/products/{id}` | GET | Détail produit |
| | `/products/` | POST | Créer produit |
| **Commandes** | `/orders/` | GET | Mes commandes |
| | `/orders/{id}` | GET | Détail commande |
| | `/orders/checkout` | POST | Créer commande |
| **Dashboard** | `/dashboard/admin` | GET | Stats admin |
| | `/dashboard/vendeur` | GET | Stats vendeur |
| **Support** | `/support/tickets` | GET | Mes tickets |
| | `/support/tickets` | POST | Créer ticket |

---

## 🔧 Services Métier

### Pattern Service Layer
```python
class ExampleService:
    def __init__(self):
        self.collection = db.example_collection

    async def get_all(self, user_id: str = None) -> List[ExampleModel]:
        """Récupérer tous les éléments avec filtres"""
        query = {}
        if user_id:
            query["user_id"] = ObjectId(user_id)

        cursor = self.collection.find(query)
        return [ExampleModel(**doc) async for doc in cursor]

    async def create(self, data: ExampleCreate) -> ExampleModel:
        """Créer un nouvel élément"""
        doc = data.dict()
        doc["created_at"] = datetime.utcnow()
        doc["updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(doc)
        return ExampleModel(id=str(result.inserted_id), **doc)
```

### Services Disponibles
- **UserService** : Gestion utilisateurs, rôles, sécurité
- **ProductService** : CRUD produits, catégories, inventaire
- **OrderService** : Commandes, suivi, statuts
- **CartService** : Panier d'achat, sessions
- **DashboardService** : KPIs, statistiques, analytics
- **EmailService** : Notifications, newsletters
- **SupportService** : Tickets, messages, catégories
- **RefundService** : Remboursements, workflow
- **ContentService** : CMS, pages, blog, FAQ

---

## 💳 Intégrations Externes

### PayGate Integration
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───►│   Backend   │───►│  PayGate   │
│   (Frontend)│    │   (API)     │    │  (Payment) │
└─────────────┘    └─────────────┘    └─────────────┘
       ▲                   │                   │
       │                   ▼                   ▼
       └─────────── Redirection ───────────────┘
                     Callback
                        │
                        ▼
               ┌─────────────────┐
               │   Confirmation  │
               │   Page          │
               └─────────────────┘
```

### MoneyFusion Integration
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───►│   Backend   │───►│ MoneyFusion│
│   (Checkout)│    │   (API)     │    │  (Gateway) │
└─────────────┘    └─────────────┘    └─────────────┘
```

### Email Service
```python
# Template email avec Jinja2
template = """
Bonjour {{ user.full_name }},

Votre commande #{{ order.id }} a été {{ status }}.

Détails: {{ order.total }}Fcfa
"""

# Envoi via SMTP
await email_service.send_email(
    to=user.email,
    subject="Mise à jour commande",
    template=template,
    context={"user": user, "order": order, "status": status}
)
```

---

## 📊 Dashboard & Analytics

### Architecture Dashboard
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   API Routes    │    │   Service       │
│   (Charts)      │◄──►│   (/dashboard) │◄──►│   Layer          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │   MongoDB       │
                                               │   Aggregations  │
                                               └─────────────────┘
```

### KPIs Disponibles
| Métrique | Source | Calcul |
|----------|--------|---------|
| **Revenus totaux** | Commandes payées | `SUM(total)` |
| **Nombre commandes** | Collection orders | `COUNT(*)` |
| **Clients actifs** | Utilisateurs | `COUNT(role=client)` |
| **Taux conversion** | Sessions/Achats | `(achats/sessions)*100` |
| **Panier moyen** | Commandes | `AVG(total)` |
| **Marges** | Produits | `(price-cost_price)/price` |

---

## 🔄 Flux de Données

### Flux Commande Complète
```
1. Client browse produits
       ↓
2. Ajout au panier (localStorage + API)
       ↓
3. Checkout → Création commande
       ↓
4. Paiement (PayGate/MoneyFusion)
       ↓
5. Callback → Mise à jour statut
       ↓
6. Notification email + WebSocket
       ↓
7. Suivi commande en temps réel
```

### Flux Analytics
```
Page visit → Pixel tracking → API /analytics/track
       ↓
Stockage anonymisé → Agrégation MongoDB
       ↓
Dashboard → Graphiques temps réel
```

---

## 🚀 Déploiement & DevOps

### Configuration Environnement
```bash
# Backend
PORT=8000
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=showroom
JWT_SECRET=your-secret-key
SMTP_HOST=smtp.gmail.com

# Frontend
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

### Pipeline CI/CD
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Git Push   │───►│   Tests     │───►│   Build     │
└─────────────┘    └─────────────┘    └─────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │   Déploiement   │
                                               │   (Docker/K8s)  │
                                               └─────────────────┘
```

### Monitoring & Logging
- **Health Checks** : `/health` endpoint
- **Logs structurés** : JSON format avec niveaux
- **Métriques** : Response times, error rates
- **Alertes** : Email sur erreurs critiques

---

## 🔒 Sécurité

### Mesures de Sécurité Implémentées
- **JWT Tokens** avec expiration
- **Hashage bcrypt** des mots de passe
- **Rate Limiting** sur les endpoints sensibles
- **CORS** configuré restrictivement
- **Validation Pydantic** des entrées
- **Sanitisation** des données utilisateur
- **HTTPS** en production
- **Audit logs** des actions sensibles

### Gestion des Sessions
```python
# Token JWT avec payload
{
  "sub": "user_id",
  "email": "user@example.com",
  "role": "client",
  "exp": 1640995200,
  "iat": 1640991600
}
```

---

## 📈 Performance & Optimisation

### Optimisations Implémentées
-<attempt_completion>
<result>
Architecture logicielle du projet Showroom - Backend FastAPI

1. Structure générale
--------------------
Le backend est organisé selon une architecture modulaire et claire, facilitant la maintenance et l'évolution :

- **app/** : Contient tout le code applicatif
  - **api/** : Routes FastAPI exposant les endpoints REST
  - **core/** : Configuration centrale, sécurité (JWT, etc.)
  - **db/** : Connexion et gestion MongoDB via Motor (async)
  - **models/** : Modèles Pydantic pour validation et sérialisation des données
  - **services/** : Logique métier, services métiers découplés des routes
  - **main.py** : Point d'entrée FastAPI

- **tests/** : Scripts de tests automatisés (à développer)
- **uploads/** : Fichiers uploadés
- **start_server.py** : Script de démarrage recommandé

2. Technologies et outils
-------------------------
- **Framework web** : FastAPI (ASGI, async)
- **Base de données** : MongoDB Atlas, accès via Motor (async PyMongo)
- **Modélisation** : Pydantic pour validation des données
- **Authentification** : JWT avec rôles (client, vendeur, admin)
- **Notifications** : WebSocket pour notifications temps réel
- **Tests** : Scripts Python pour tests unitaires et d’intégration

3. Principaux modules et responsabilités
----------------------------------------
- **API** : Gestion des routes REST pour authentification, produits, commandes, dashboard, support, remboursements, analytics, CMS, etc.
- **Services** : Implémentation de la logique métier (ex: gestion commandes, calculs dashboard, gestion utilisateurs, remboursements)
- **Modèles** : Définition des schémas de données (utilisateurs, produits, commandes, tickets support, remboursements, analytics, contenu CMS)
- **Base de données** : Connexion MongoDB, création d’index, accès direct via requêtes MongoDB natives et pipelines d’agrégation
- **Sécurité** : Gestion des tokens JWT, contrôle d’accès par rôles, protection des endpoints

4. Fonctionnalités clés
-----------------------
- Système complet de suivi des commandes avec historique et notifications
- Dashboard enrichi pour admin et vendeurs avec métriques financières, alertes stock, remboursements
- Gestion des utilisateurs avec rôles et permissions granulaires
- Système de support et tickets avec workflow complet
- Gestion des remboursements avec statuts et approbations
- Analytics visiteurs avec tracking et statistiques
- CMS intégré pour pages, FAQ, blog, guides des tailles
- Export CSV des données commerciales
- Notifications temps réel via WebSocket
- Authentification sécurisée avec JWT

5. Déploiement et configuration
-------------------------------
- Configuration via variables d’environnement (.env)
- Script de démarrage simple (start_server.py)
- Support multi-environnements (dev, prod)
- Index MongoDB optimisés pour performances

6. Tests et validation
----------------------
- Scripts de tests automatisés pour endpoints critiques
- Tests spécifiques pour phases 7 & 8 (BI, CMS)
- Validation des workflows clés (auth, commandes, remboursements)

Résumé
------
Cette architecture modulaire, basée sur FastAPI et MongoDB, offre une solution scalable, performante et facile à maintenir pour une plateforme e-commerce complète avec suivi des commandes, support client, analytics et CMS intégré.

Si vous souhaitez, je peux vous aider à générer une documentation technique détaillée ou un diagramme d’architecture visuel.

</result>
</attempt_completion>
