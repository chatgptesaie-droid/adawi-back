from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.db.mongo import db
from app.models.support import (
    TicketCreate, TicketUpdate, TicketInDB, TicketPublic, TicketDetail,
    TicketMessage, MessageCreate, TicketStatus, TicketStats
)
from app.services.notification_service import notification_service
from app.core.emails_utils import notify_admin_of_new_ticket
from app.services.sms_service import (
    customer_name,
    customer_phone,
    send_customer_sms,
    short_reference,
    status_label,
)

class SupportService:
    def __init__(self):
        self.collection = db.tickets
        self.users_collection = db.users

    async def create_ticket(self, ticket: TicketCreate, customer_id: str) -> TicketPublic:
        """Crée un nouveau ticket de support"""
        now = datetime.utcnow()
        # Ne pas persister le product_id lors de la création du ticket
        payload = ticket.model_dump(exclude={"product_id"})
        ticket_data = {
            **payload,
            "customer_id": customer_id,
            "status": TicketStatus.ouvert.value,
            "created_at": now,
            "updated_at": now,
            "messages": []
        }
        
        result = await self.collection.insert_one(ticket_data)
        ticket_data["id"] = str(result.inserted_id)
        
        # Notification aux admins/vendeurs
        await notification_service.create_notification(
            user_id="staff",
            type="nouveau_ticket",
            message=f"Nouveau ticket de support: {ticket.title}",
            order_id=ticket.order_id
        )

        customer = await self.users_collection.find_one({"_id": ObjectId(customer_id)})
        await send_customer_sms(
            customer_phone(customer),
            customer_name(customer),
            f"Nous avons reçu votre ticket « {ticket.title} » (réf. {short_reference(ticket_data['id'])}).",
            occurred_at=now,
            event="ticket.created",
        )
        
        return await self._convert_to_public(ticket_data)

    async def get_tickets(
        self, 
        customer_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[TicketPublic]:
        """Récupère les tickets avec filtres"""
        query = {}
        
        if customer_id:
            query["customer_id"] = customer_id
        if assigned_to:
            query["assigned_to"] = assigned_to
        if status:
            query["status"] = status
        if category:
            query["category"] = category
            
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        tickets = []
        
        async for ticket in cursor:
            tickets.append(await self._convert_to_public(ticket))
            
        return tickets

    async def get_ticket(self, ticket_id: str, with_messages: bool = False) -> Optional[TicketDetail]:
        """Récupère un ticket par son ID"""
        try:
            ticket = await self.collection.find_one({"_id": ObjectId(ticket_id)})
            if not ticket:
                return None
                
            ticket["id"] = str(ticket["_id"])
            
            if with_messages:
                return await self._convert_to_detail(ticket)
            else:
                return await self._convert_to_public(ticket)
                
        except:
            return None

    async def update_ticket(self, ticket_id: str, update: TicketUpdate, user_id: str) -> Optional[TicketPublic]:
        """Met à jour un ticket"""
        try:
            update_data = {k: v for k, v in update.dict().items() if v is not None}
            update_data["updated_at"] = datetime.utcnow()
            
            # Si le statut change vers résolu
            if update.status == TicketStatus.resolu and "resolved_at" not in update_data:
                update_data["resolved_at"] = datetime.utcnow()
            
            result = await self.collection.update_one(
                {"_id": ObjectId(ticket_id)},
                {"$set": update_data}
            )
            
            if result.modified_count:
                ticket = await self.collection.find_one({"_id": ObjectId(ticket_id)})
                ticket["id"] = str(ticket["_id"])
                
                # Notification au client si changement de statut
                if update.status:
                    await notification_service.create_notification(
                        user_id=ticket["customer_id"],
                        type="ticket_statut",
                        message=f"Votre ticket '{ticket['title']}' est maintenant {update.status}",
                        order_id=ticket.get("order_id")
                    )
                    customer = await self.users_collection.find_one(
                        {"_id": ObjectId(ticket["customer_id"])}
                    )
                    status_text = status_label(update.status)
                    await send_customer_sms(
                        customer_phone(customer),
                        customer_name(customer),
                        f"Le statut de votre ticket « {ticket['title']} » est maintenant {status_text}.",
                        occurred_at=ticket.get("updated_at"),
                        event="ticket.status_changed",
                    )
                
                return await self._convert_to_public(ticket)
            return None
            
        except:
            return None

    async def add_message(self, ticket_id: str, message: MessageCreate, author_id: str) -> Optional[TicketDetail]:
        """Ajoute un message à un ticket"""
        try:
            # Récupérer les infos de l'auteur
            author = await self.users_collection.find_one({"_id": ObjectId(author_id)})
            if not author:
                return None
                
            now = datetime.utcnow()
            message_data = {
                "id": str(ObjectId()),
                "ticket_id": ticket_id,
                "author_id": author_id,
                "author_name": author.get("full_name", "Utilisateur"),
                "author_role": author.get("role", "client"),
                "message": message.message,
                "created_at": now,
                "is_internal": message.is_internal
            }
            
            # Ajouter le message au ticket
            result = await self.collection.update_one(
                {"_id": ObjectId(ticket_id)},
                {
                    "$push": {"messages": message_data},
                    "$set": {"updated_at": now}
                }
            )
            
            if result.modified_count:
                # Notification selon le rôle de l'auteur
                ticket = await self.collection.find_one({"_id": ObjectId(ticket_id)})
                
                if author.get("role") in ["vendeur", "admin"]:
                    # Notification au client
                    await notification_service.create_notification(
                        user_id=ticket["customer_id"],
                        type="ticket_reponse",
                        message=f"Nouvelle réponse sur votre ticket '{ticket['title']}'",
                        order_id=ticket.get("order_id")
                    )
                    if not message.is_internal:
                        customer = await self.users_collection.find_one(
                            {"_id": ObjectId(ticket["customer_id"])}
                        )
                        await send_customer_sms(
                            customer_phone(customer),
                            customer_name(customer),
                            f"Le support a répondu à votre ticket « {ticket['title']} ».",
                            occurred_at=now,
                            event="ticket.reply",
                        )
                else:
                    # Notification au staff
                    await notification_service.create_notification(
                        user_id="staff",
                        type="ticket_message",
                        message=f"Nouveau message sur le ticket '{ticket['title']}'",
                        order_id=ticket.get("order_id")
                    )
                
                return await self.get_ticket(ticket_id, with_messages=True)
            return None
            
        except:
            return None

    async def assign_ticket(self, ticket_id: str, assigned_to: str) -> Optional[TicketPublic]:
        """Assigne un ticket à un vendeur/admin"""
        update = TicketUpdate(
            assigned_to=assigned_to,
            status=TicketStatus.en_cours
        )
        return await self.update_ticket(ticket_id, update, assigned_to)

    async def get_vendor_tickets(self, vendor_id: str) -> List[TicketPublic]:
        """Récupère les tickets visibles par un vendeur.
        Inclut:
          - Tickets déjà assignés au vendeur
          - Tickets ouverts non assignés (pool d'attente)
        """
        try:
            # Tickets assignés directement
            assigned_tickets = await self.get_tickets(assigned_to=vendor_id)
            # Tickets ouverts non assignés (pool commun)
            unassigned_open_tickets = []
            cursor = self.collection.find({
                "assigned_to": {"$in": [None, ""]},
                "status": TicketStatus.ouvert.value
            })
            async for ticket in cursor:
                try:
                    ticket["id"] = str(ticket["_id"])
                    unassigned_open_tickets.append(await self._convert_to_public(ticket))
                except Exception:
                    continue

            # Combiner et dédupliquer (priorité: assigned > unassigned)
            combined = {}
            for t in unassigned_open_tickets + assigned_tickets:
                combined[t.id] = t

            return list(combined.values())
        except Exception:
            return []

    async def get_support_stats(self, vendor_id: Optional[str] = None) -> TicketStats:
        """Récupère les statistiques de support"""
        query = {}
        if vendor_id:
            # Stats pour un vendeur spécifique: uniquement les tickets qui lui sont assignés
            query = {"assigned_to": vendor_id}
        
        # Compter par statut
        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        
        status_counts = {status.value: 0 for status in TicketStatus}
        async for item in self.collection.aggregate(pipeline):
            status_counts[item["_id"]] = item["count"]
        
        # Temps de résolution moyen
        resolved_pipeline = [
            {"$match": {**query, "resolved_at": {"$exists": True}}},
            {"$project": {
                "resolution_time": {
                    "$divide": [
                        {"$subtract": ["$resolved_at", "$created_at"]},
                        3600000  # Convertir en heures
                    ]
                }
            }},
            {"$group": {"_id": None, "avg_time": {"$avg": "$resolution_time"}}}
        ]
        
        avg_resolution = await self.collection.aggregate(resolved_pipeline).to_list(1)
        avg_resolution_time = avg_resolution[0]["avg_time"] if avg_resolution else 0.0
        
        return TicketStats(
            total_tickets=sum(status_counts.values()),
            open_tickets=status_counts[TicketStatus.ouvert.value],
            in_progress_tickets=status_counts[TicketStatus.en_cours.value],
            resolved_tickets=status_counts[TicketStatus.resolu.value],
            closed_tickets=status_counts[TicketStatus.ferme.value],
            average_resolution_time=avg_resolution_time,
            tickets_by_category=[],  # À implémenter si nécessaire
            tickets_by_priority=[]   # À implémenter si nécessaire
        )

    async def get_support_overview(self) -> dict:
        """Récupère un résumé complet du support pour les administrateurs"""
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        # === COMPTEURS PRINCIPAUX ===
        
        # Total des tickets
        total_tickets = await self.collection.count_documents({})
        
        # Comptes par statut
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        tickets_by_status = {}
        async for item in self.collection.aggregate(status_pipeline):
            tickets_by_status[item["_id"]] = item["count"]
        
        # Initialiser les statuts manquants avec 0
        for status in TicketStatus:
            if status.value not in tickets_by_status:
                tickets_by_status[status.value] = 0
        
        # Comptes par priorité
        priority_pipeline = [
            {"$group": {"_id": "$priority", "count": {"$sum": 1}}}
        ]
        tickets_by_priority = {}
        async for item in self.collection.aggregate(priority_pipeline):
            tickets_by_priority[item["_id"]] = item["count"]
        
        # Comptes par catégorie
        category_pipeline = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]
        tickets_by_category = {}
        async for item in self.collection.aggregate(category_pipeline):
            tickets_by_category[item["_id"]] = item["count"]
        
        # === MÉTRIQUES TEMPORELLES ===
        
        # Nouveaux tickets aujourd'hui
        today_new_tickets = await self.collection.count_documents({
            "created_at": {"$gte": today_start}
        })
        
        # Nouveaux tickets cette semaine
        week_new_tickets = await self.collection.count_documents({
            "created_at": {"$gte": week_start}
        })
        
        # Nouveaux tickets ce mois
        month_new_tickets = await self.collection.count_documents({
            "created_at": {"$gte": month_start}
        })
        
        # === PERFORMANCE ===
        
        # Temps de résolution moyen
        resolution_pipeline = [
            {"$match": {"resolved_at": {"$exists": True}}},
            {"$project": {
                "resolution_time": {
                    "$divide": [
                        {"$subtract": ["$resolved_at", "$created_at"]},
                        3600000  # en heures
                    ]
                }
            }},
            {"$group": {"_id": None, "avg_time": {"$avg": "$resolution_time"}}}
        ]
        
        avg_resolution = await self.collection.aggregate(resolution_pipeline).to_list(1)
        average_resolution_time_hours = avg_resolution[0]["avg_time"] if avg_resolution else 0.0
        
        # Tickets en attente de réponse (dernière réponse par un client)
        pending_response_tickets = 0
        try:
            # Tickets où le dernier message est d'un client
            pending_pipeline = [
                {"$match": {"status": {"$in": ["ouvert", "en_cours"]}}},
                {"$project": {
                    "last_message": {"$arrayElemAt": ["$messages", -1]}
                }},
                {"$match": {"last_message.author_role": "client"}}
            ]
            pending_response_tickets = len(await self.collection.aggregate(pending_pipeline).to_list(None))
        except Exception:
            pass
        
        # Tickets en retard (>24h sans réponse du support)
        yesterday = now - timedelta(hours=24)
        overdue_tickets = await self.collection.count_documents({
            "status": {"$in": ["ouvert", "en_cours"]},
            "updated_at": {"$lt": yesterday}
        })
        
        # === RÉPARTITION DU TRAVAIL ===
        
        # Tickets non assignés
        unassigned_tickets = await self.collection.count_documents({
            "$or": [
                {"assigned_to": {"$exists": False}},
                {"assigned_to": None},
                {"assigned_to": ""}
            ]
        })
        
        # Répartition par assigné
        assignee_pipeline = [
            {"$match": {"assigned_to": {"$exists": True, "$ne": None, "$ne": ""}}},
            {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}}}
        ]
        
        tickets_by_assignee = []
        async for item in self.collection.aggregate(assignee_pipeline):
            try:
                # Récupérer le nom de l'assigné
                assignee = await self.users_collection.find_one({"_id": ObjectId(item["_id"])})
                name = "Utilisateur inconnu"
                if assignee:
                    name = assignee.get("full_name")
                    if not name:
                        first = assignee.get("first_name", "")
                        last = assignee.get("last_name", "")
                        name = f"{first} {last}".strip() or assignee.get("email", "Utilisateur")
                
                tickets_by_assignee.append({
                    "user_id": item["_id"],
                    "name": name,
                    "count": item["count"]
                })
            except Exception:
                tickets_by_assignee.append({
                    "user_id": item["_id"],
                    "name": "Utilisateur inconnu", 
                    "count": item["count"]
                })
        
        # Trier par nombre de tickets décroissant
        tickets_by_assignee.sort(key=lambda x: x["count"], reverse=True)
        
        # === TENDANCES RÉCENTES ===
        
        # Taux de résolution sur 7 jours
        week_total = await self.collection.count_documents({
            "created_at": {"$gte": week_start}
        })
        week_resolved = await self.collection.count_documents({
            "created_at": {"$gte": week_start},
            "status": {"$in": ["resolu", "ferme"]}
        })
        resolution_rate_7days = (week_resolved / week_total * 100) if week_total > 0 else 0.0
        
        return {
            # Compteurs principaux
            "total_tickets": total_tickets,
            "tickets_by_status": tickets_by_status,
            "tickets_by_priority": tickets_by_priority,
            "tickets_by_category": tickets_by_category,
            
            # Métriques temporelles
            "today_new_tickets": today_new_tickets,
            "week_new_tickets": week_new_tickets,
            "month_new_tickets": month_new_tickets,
            
            # Performance
            "average_resolution_time_hours": round(average_resolution_time_hours, 2),
            "pending_response_tickets": pending_response_tickets,
            "overdue_tickets": overdue_tickets,
            
            # Répartition du travail
            "unassigned_tickets": unassigned_tickets,
            "tickets_by_assignee": tickets_by_assignee,
            
            # Tendances récentes
            "resolution_rate_7days": round(resolution_rate_7days, 1),
            "customer_satisfaction": None  # À implémenter plus tard
        }

    async def _convert_to_public(self, ticket_data: dict) -> TicketPublic:
        """Convertit un ticket DB en ticket public"""
        ticket_data["id"] = str(ticket_data["_id"])
        
        # Récupérer le nom du client
        if "customer_id" in ticket_data:
            try:
                customer = await self.users_collection.find_one({"_id": ObjectId(ticket_data["customer_id"])})
                if customer:
                    # Essayer full_name, sinon construire à partir des autres champs
                    name = customer.get("full_name")
                    if not name:
                        first = customer.get("first_name", "")
                        last = customer.get("last_name", "")
                        name = f"{first} {last}".strip() or customer.get("email", "Client")
                    ticket_data["customer_name"] = name
                else:
                    ticket_data["customer_name"] = "Client"
            except Exception:
                ticket_data["customer_name"] = "Client"
        
        # Récupérer le nom de l'assigné
        if ticket_data.get("assigned_to"):
            try:
                assignee = await self.users_collection.find_one({"_id": ObjectId(ticket_data["assigned_to"])})
                if assignee:
                    # Essayer full_name, sinon construire à partir des autres champs
                    name = assignee.get("full_name")
                    if not name:
                        first = assignee.get("first_name", "")
                        last = assignee.get("last_name", "")
                        name = f"{first} {last}".strip() or assignee.get("email", "Staff")
                    ticket_data["assigned_to_name"] = name
                else:
                    ticket_data["assigned_to_name"] = "Staff"
            except Exception:
                ticket_data["assigned_to_name"] = "Staff"
        
        # Statistiques des messages
        messages = ticket_data.get("messages", [])
        ticket_data["messages_count"] = len(messages)
        ticket_data["last_message_at"] = messages[-1]["created_at"] if messages else None
        
        # Enlever les messages pour la vue publique
        ticket_data.pop("messages", None)
        
        return TicketPublic(**ticket_data)

    async def _convert_to_detail(self, ticket_data: dict) -> TicketDetail:
        """Convertit un ticket DB en ticket détaillé"""
        public_ticket = await self._convert_to_public(ticket_data.copy())
        
        # Récupérer les messages
        messages = ticket_data.get("messages", [])
        
        return TicketDetail(
            **public_ticket.dict(),
            messages=[TicketMessage(**msg) for msg in messages]
        )

support_service = SupportService()
