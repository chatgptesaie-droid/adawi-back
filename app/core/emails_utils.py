"""
Utilities for sending email notifications related to payments and invoices
"""

from app.services.email_service_enhanced import send_admin_email, send_status_email

async def notify_admin_of_new_invoice(db, user_name: str, amount: int, email: str, 
                                     identifier: str, status: str = "créée"):
    """Notify admin about a new invoice creation or payment"""
    subject = f"💰 Nouvelle facture {status} - {identifier}"
    body = f"""
    Une nouvelle facture a été {status}:
    
    - Client: {user_name}
    - Email: {email}
    - Montant: {amount} FCFA
    - Référence: {identifier}
    - Statut: {status}
    
    Veuillez vérifier le système d'administration pour plus de détails.
    """
    
    await send_admin_email(subject, body)

async def notify_admin_of_new_ticket(customer_name: str, customer_email: str, ticket_title: str, ticket_id: str):
    """Notify admin about a new support ticket"""
    subject = f"🎫 Nouveau ticket de support - {ticket_title}"
    body = f"""
    Un nouveau ticket de support a été créé:
    
    - Client: {customer_name}
    - Email: {customer_email}
    - Titre: {ticket_title}
    - ID Ticket: {ticket_id}
    
    Veuillez vérifier le système d'administration pour traiter ce ticket.
    """
    
    await send_admin_email(subject, body)

async def notify_admin_of_refund_request(customer_name: str, customer_email: str, amount: float, refund_id: str, reason: str):
    """Notify admin about a new refund request"""
    subject = f"💸 Nouvelle demande de remboursement - {refund_id}"
    body = f"""
    Une nouvelle demande de remboursement a été soumise:
    
    - Client: {customer_name}
    - Email: {customer_email}
    - Montant: {amount} FCFA
    - Raison: {reason}
    - ID Remboursement: {refund_id}
    
    Veuillez vérifier le système d'administration pour traiter cette demande.
    """
    
    await send_admin_email(subject, body)

async def send_payment_email(email: str, amount: int, payment_method: str, 
                           reference: str, status: str):
    """Send a payment email whose wording matches the actual payment status."""
    subject = f"✅ Paiement {status} - Référence: {reference}"
    normalized_status = status.strip().casefold()
    successful_statuses = {"réussi", "reussi", "payée", "payee", "effectué", "effectue", "success", "paid"}
    pending_statuses = {"créée", "creee", "créé", "cree", "en attente", "pending", "en cours"}
    cancelled_statuses = {"annulée", "annulee", "annulé", "annule", "cancelled", "canceled"}
    expired_statuses = {"expirée", "expiree", "expiré", "expire", "expired"}
    
    if normalized_status in successful_statuses:
        body = f"""
        Bonjour,
        
        Votre paiement de {amount} FCFA a été traité avec succès.
        
        Détails du paiement:
        - Montant: {amount} FCFA
        - Méthode: {payment_method}
        - Référence: {reference}
        - Statut: Paiement effectué avec succès
        
        Merci pour votre confiance !
        
        Cordialement,
        L'équipe Adawi
        """
    elif normalized_status in pending_statuses:
        body = f"""
        Bonjour,

        Votre commande a été enregistrée et votre paiement de {amount} FCFA est en attente de confirmation.

        Détails du paiement:
        - Montant: {amount} FCFA
        - Méthode: {payment_method}
        - Référence: {reference}
        - Statut: En attente

        Vous recevrez une confirmation dès que le paiement sera traité.

        Cordialement,
        L'équipe Adawi
        """
    elif normalized_status in cancelled_statuses | expired_statuses:
        status_message = "a été annulé" if normalized_status in cancelled_statuses else "a expiré"
        body = f"""
        Bonjour,

        Votre paiement de {amount} FCFA {status_message}.

        Détails du paiement:
        - Montant: {amount} FCFA
        - Méthode: {payment_method}
        - Référence: {reference}
        - Statut: {status}

        Veuillez réessayer ou contacter le support si nécessaire.

        Cordialement,
        L'équipe Adawi
        """
    else:
        body = f"""
        Bonjour,
        
        Votre paiement de {amount} FCFA a échoué ou a été refusé.
        
        Détails:
        - Montant: {amount} FCFA
        - Méthode: {payment_method}
        - Référence: {reference}
        - Statut: Échec du paiement
        
        Veuillez réessayer ou contacter le support.
        
        Cordialement,
        L'équipe Adawi
        """
    
    await send_status_email(email, subject, body)
