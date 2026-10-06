# from app.core.config import settings
# from typing import Dict, Any, Optional
# import uuid
# # from apiMoneyFusion import PaymentClient

# class MoneyFusionService:
#     def __init__(self):
#         # Vérifier si API_KEY_MONEYFUSION est une vraie clé API ou autre chose
#         api_key = settings.API_KEY_MONEYFUSION

#         if api_key and api_key != 'test_moneyfusion_key' and not api_key.startswith('https://'):
#             # C'est une vraie clé API MoneyFusion
#             try:
#                 self.client = PaymentClient(api_key_url="https://api.moneyfusion.net")
#                 self.use_api = True
#                 self.boutique_url = None
#                 print("🔌 Utilisation de l'API MoneyFusion officielle avec clé API")
#             except Exception as e:
#                 print(f"❌ Erreur d'initialisation API MoneyFusion: {e}")
#                 self.use_api = False
#                 self.boutique_url = None
#         else:
#             # Pas de clé API valide - utiliser l'URL générique qui fonctionne
#             self.use_api = False
#             self.boutique_url = None
#             print("🔄 Utilisation de l'URL générique payin.moneyfusion.net (recommandé)")

#     async def create_payment(self,
#                            total_price: int,
#                            articles: list,
#                            phone_number: str,
#                            client_name: str,
#                            user_id: str,
#                            order_id: str,
#                            return_url: str) -> Dict[str, Any]:
#         """
#         Créer un paiement MoneyFusion
#         """
#         # Générer un token unique
#         token = str(uuid.uuid4())[:20]

#         if not self.use_api and self.boutique_url:
#             # Utiliser l'URL de boutique personnalisée
#             print(f"🔗 Génération du lien avec boutique personnalisée: {self.boutique_url}")

#             # Construire l'URL de paiement avec la boutique personnalisée
#             payment_url = f"{self.boutique_url}/?amount={total_price}&phone={phone_number}&client={client_name}&token={token}&order_id={order_id}&return_url={return_url}"

#             return {
#                 "statut": True,
#                 "token": token,
#                 "url": payment_url,
#                 "message": f"Payment link generated with custom boutique URL: {self.boutique_url}"
#             }

#         else:
#             # Utiliser l'API officielle ou l'URL générique qui fonctionne
#             if self.use_api:
#                 try:
#                     # Créer le paiement via l'API MoneyFusion
#                     payment = self.client.create_payment(
#                         total_price=str(total_price),
#                         articles=articles,
#                         numero_send=phone_number,
#                         nom_client=client_name,
#                         user_id=user_id,
#                         order_id=order_id,
#                         return_url=return_url
#                     )

#                     return payment

#                 except Exception as e:
#                     print(f"Erreur lors de la création du paiement MoneyFusion: {e}")
#                     print("Utilisation du fallback avec lien générique...")

#             # Utiliser l'URL de test MoneyFusion qui permet de simuler des paiements
#             # Format: https://payin.moneyfusion.net/payment/{token}/{amount}/{client_name}
#             # Pour les tests, on utilise un token fixe qui fonctionne
#             test_token = "test123"  # Token de test MoneyFusion
#             payment_url = f"https://payin.moneyfusion.net/payment/{test_token}/{total_price}/{client_name}"

#             return {
#                 "statut": True,
#                 "token": test_token,
#                 "url": payment_url,
#                 "message": "Payment link generated with MoneyFusion test URL (for testing purposes)"
#             }

#     async def get_payment(self, token: str) -> Dict[str, Any]:
#         """
#         Récupérer les informations d'un paiement MoneyFusion
#         """
#         if not self.use_api and self.boutique_url:
#             # Pour les boutiques personnalisées, on ne peut pas récupérer les infos via API
#             # Retourner une réponse simulée
#             print(f"🔗 Boutique personnalisée détectée - simulation des détails de paiement pour token: {token}")
#             return {
#                 "statut": True,
#                 "data": {
#                     "tokenPay": token,
#                     "numeroSend": "+228XXXXXXXX",
#                     "nomclient": "Client Boutique",
#                     "Montant": 0,
#                     "statut": "pending"
#                 },
#                 "message": f"Payment details (simulated for custom boutique: {self.boutique_url})"
#             }
#         else:
#             # Utiliser l'API officielle
#             try:
#                 payment_info = self.client.get_payment(token)
#                 return payment_info
#             except Exception as e:
#                 print(f"Erreur lors de la récupération du paiement MoneyFusion: {e}")
#                 # Fallback: simulation de réponse
#                 return {
#                     "statut": True,
#                     "data": {
#                         "tokenPay": token,
#                         "numeroSend": "+228XXXXXXXX",
#                         "nomclient": "Client",
#                         "Montant": 0,
#                         "statut": "pending"
#                     },
#                     "message": "Payment details (simulated)"
#                 }

#     def format_articles_from_order(self, order_data: Dict[str, Any]) -> list:
#         """
#         Formater les articles d'une commande pour MoneyFusion
#         """
#         articles = []
#         if "items" in order_data:
#             for item in order_data["items"]:
#                 articles.append({
#                     "name": item.get("name", "Produit"),
#                     "price": str(item.get("price", 0)),
#                     "quantity": item.get("quantity", 1)
#                 })
#         return articles

# # Instance globale du service
# moneyfusion_service = MoneyFusionService()
