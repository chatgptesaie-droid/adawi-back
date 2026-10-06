from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.db.mongo import db
from app.models.content import (
    PageCreate, PageUpdate, PageInDB, PagePublic, PageStatus,
    FAQCreate, FAQUpdate, FAQInDB, FAQPublic, FAQCategory,
    SizeChartCreate, SizeChartUpdate, SizeChartInDB, SizeChartPublic,
    PostCreate, PostUpdate, PostInDB, PostPublic, PostSummary, PostStatus,
    ContentOverview
)
from app.services.email_service_enhanced import send_email
from app.services.newsletter_service import newsletter_service

class ContentService:
    def __init__(self):
        self.pages_collection = db.pages
        self.faqs_collection = db.faqs
        self.size_charts_collection = db.size_charts
        self.posts_collection = db.posts
        self.users_collection = db.users

    # === GESTION DES PAGES ===

    async def create_page(self, page: PageCreate, author_id: str) -> PagePublic:
        """Créer une nouvelle page"""
        # Vérifier que le slug n'existe pas déjà
        existing = await self.pages_collection.find_one({"slug": page.slug})
        if existing:
            raise ValueError(f"Une page avec le slug '{page.slug}' existe déjà")
        
        now = datetime.utcnow()
        page_data = {
            **page.dict(),
            "author_id": author_id,
            "created_at": now,
            "updated_at": now,
            "published_at": now if page.status == PageStatus.published else None,
            "views_count": 0
        }
        
        result = await self.pages_collection.insert_one(page_data)
        page_data["id"] = str(result.inserted_id)
        
        return await self._convert_page_to_public(page_data)

    async def get_page_by_slug(self, slug: str, increment_views: bool = False) -> Optional[PagePublic]:
        """Récupérer une page par son slug"""
        page = await self.pages_collection.find_one({"slug": slug})
        if not page:
            return None
        
        # Incrémenter le compteur de vues si demandé
        if increment_views:
            await self.pages_collection.update_one(
                {"_id": page["_id"]},
                {"$inc": {"views_count": 1}}
            )
            page["views_count"] = page.get("views_count", 0) + 1
        
        page["id"] = str(page["_id"])
        return await self._convert_page_to_public(page)

    async def get_pages(
        self, 
        status: Optional[PageStatus] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[PagePublic]:
        """Récupérer la liste des pages"""
        query = {}
        if status:
            query["status"] = status.value
        
        cursor = self.pages_collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        pages = []
        
        async for page in cursor:
            page["id"] = str(page["_id"])
            pages.append(await self._convert_page_to_public(page))
        
        return pages

    async def update_page(self, slug: str, update: PageUpdate, author_id: str) -> Optional[PagePublic]:
        """Mettre à jour une page"""
        update_data = {k: v for k, v in update.dict().items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()
        
        # Si on publie la page, définir published_at
        if update.status == PageStatus.published:
            existing = await self.pages_collection.find_one({"slug": slug})
            if existing and not existing.get("published_at"):
                update_data["published_at"] = datetime.utcnow()
        
        result = await self.pages_collection.update_one(
            {"slug": slug},
            {"$set": update_data}
        )
        
        if result.modified_count:
            return await self.get_page_by_slug(slug)
        return None

    async def delete_page(self, slug: str) -> bool:
        """Supprimer une page"""
        result = await self.pages_collection.delete_one({"slug": slug})
        return result.deleted_count > 0

    # === GESTION DES FAQ ===

    async def create_faq(self, faq: FAQCreate) -> FAQPublic:
        """Créer une nouvelle FAQ"""
        now = datetime.utcnow()
        faq_data = {
            **faq.dict(),
            "created_at": now,
            "updated_at": now
        }
        
        result = await self.faqs_collection.insert_one(faq_data)
        faq_data["id"] = str(result.inserted_id)
        
        return FAQPublic(**faq_data)

    async def get_faqs(
        self,
        category: Optional[FAQCategory] = None,
        featured_only: bool = False
    ) -> List[FAQPublic]:
        """Récupérer les FAQs"""
        query = {}
        if category:
            query["category"] = category.value
        if featured_only:
            query["is_featured"] = True
        
        cursor = self.faqs_collection.find(query).sort("order", 1)
        faqs = []
        
        async for faq in cursor:
            faq["id"] = str(faq["_id"])
            faqs.append(FAQPublic(**faq))
        
        return faqs

    async def get_faq(self, faq_id: str) -> Optional[FAQPublic]:
        """Récupérer une FAQ par son ID"""
        try:
            faq = await self.faqs_collection.find_one({"_id": ObjectId(faq_id)})
            if not faq:
                return None
            
            faq["id"] = str(faq["_id"])
            return FAQPublic(**faq)
        except:
            return None

    async def update_faq(self, faq_id: str, update: FAQUpdate) -> Optional[FAQPublic]:
        """Mettre à jour une FAQ"""
        try:
            update_data = {k: v for k, v in update.dict().items() if v is not None}
            update_data["updated_at"] = datetime.utcnow()
            
            result = await self.faqs_collection.update_one(
                {"_id": ObjectId(faq_id)},
                {"$set": update_data}
            )
            
            if result.modified_count:
                return await self.get_faq(faq_id)
            return None
        except:
            return None

    async def delete_faq(self, faq_id: str) -> bool:
        """Supprimer une FAQ"""
        try:
            result = await self.faqs_collection.delete_one({"_id": ObjectId(faq_id)})
            return result.deleted_count > 0
        except:
            return False

    # === GESTION DES GUIDES TAILLES ===

    async def create_size_chart(self, chart: SizeChartCreate) -> SizeChartPublic:
        """Créer un nouveau guide des tailles"""
        now = datetime.utcnow()
        chart_data = {
            **chart.dict(),
            "created_at": now,
            "updated_at": now
        }
        
        result = await self.size_charts_collection.insert_one(chart_data)
        chart_data["id"] = str(result.inserted_id)
        
        return SizeChartPublic(**chart_data)

    async def get_size_charts(self) -> List[SizeChartPublic]:
        """Récupérer tous les guides des tailles"""
        cursor = self.size_charts_collection.find().sort("order", 1)
        charts = []
        
        async for chart in cursor:
            chart["id"] = str(chart["_id"])
            charts.append(SizeChartPublic(**chart))
        
        return charts

    # === GESTION DU BLOG ===

    async def create_post(self, post: PostCreate, author_id: str) -> PostPublic:
        """Créer un nouveau post de blog"""
        # Vérifier que le slug n'existe pas déjà
        existing = await self.posts_collection.find_one({"slug": post.slug})
        if existing:
            raise ValueError(f"Un post avec le slug '{post.slug}' existe déjà")
        
        now = datetime.utcnow()
        post_data = {
            **post.dict(),
            "author_id": author_id,
            "created_at": now,
            "updated_at": now,
            "published_at": now if post.status == PostStatus.published else None,
            "views_count": 0
        }
        
        result = await self.posts_collection.insert_one(post_data)
        post_data["id"] = str(result.inserted_id)

        return await self._convert_post_to_public(post_data)

    async def get_posts(
        self,
        status: Optional[PostStatus] = None,
        tags: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[PostSummary]:
        """Récupérer la liste des posts (version résumée)"""
        query = {}
        if status:
            query["status"] = status.value
        if tags:
            query["tags"] = {"$in": tags}
        # Exclude soft-deleted posts
        query["deleted_at"] = {"$exists": False}
        
        cursor = self.posts_collection.find(query).sort("published_at", -1).skip(skip).limit(limit)
        posts = []
        
        async for post in cursor:
            post["id"] = str(post["_id"])
            
            # Récupérer le nom de l'auteur
            author_name = None
            if post.get("author_id"):
                try:
                    author = await self.users_collection.find_one({"_id": ObjectId(post["author_id"])})
                    if author:
                        author_name = author.get("full_name", "Auteur")
                except:
                    pass
            
            posts.append(PostSummary(
                id=post["id"],
                title=post["title"],
                slug=post["slug"],
                excerpt=post.get("excerpt"),
                cover_image=post.get("cover_image"),
                tags=post.get("tags", []),
                author_name=author_name,
                published_at=post.get("published_at"),
                views_count=post.get("views_count", 0)
            ))
        
        return posts

    async def get_post_by_slug(self, slug: str, increment_views: bool = False) -> Optional[PostPublic]:
        """Récupérer un post par son slug"""
        post = await self.posts_collection.find_one({"slug": slug, "deleted_at": {"$exists": False}})
        if not post:
            return None
        
        # Incrémenter le compteur de vues si demandé
        if increment_views:
            await self.posts_collection.update_one(
                {"_id": post["_id"]},
                {"$inc": {"views_count": 1}}
            )
            post["views_count"] = post.get("views_count", 0) + 1
        
        post["id"] = str(post["_id"])
        return await self._convert_post_to_public(post)

    async def hard_delete_post(self, slug: str) -> bool:
        """Supprimer un post de blog (hard delete)"""
        result = await self.posts_collection.delete_one({"slug": slug})
        return result.deleted_count > 0

    # === MÉTHODES UTILITAIRES ===

    async def _convert_page_to_public(self, page_data: dict) -> PagePublic:
        """Convertir une page DB en page publique"""
        # Récupérer le nom de l'auteur
        author_name = None
        if page_data.get("author_id"):
            try:
                author = await self.users_collection.find_one({"_id": ObjectId(page_data["author_id"])})
                if author:
                    author_name = author.get("full_name", "Auteur")
            except:
                pass
        
        page_data["author_name"] = author_name
        return PagePublic(**page_data)

    async def _convert_post_to_public(self, post_data: dict) -> PostPublic:
        """Convertir un post DB en post public"""
        # Récupérer le nom de l'auteur
        author_name = None
        if post_data.get("author_id"):
            try:
                author = await self.users_collection.find_one({"_id": ObjectId(post_data["author_id"])})
                if author:
                    author_name = author.get("full_name", "Auteur")
            except:
                pass
        
        post_data["author_name"] = author_name
        return PostPublic(**post_data)

    async def get_content_overview(self) -> ContentOverview:
        """Aperçu du contenu pour l'admin"""
        # Statistiques des pages
        total_pages = await self.pages_collection.count_documents({})
        published_pages = await self.pages_collection.count_documents({"status": "published"})
        draft_pages = await self.pages_collection.count_documents({"status": "draft"})
        
        # Statistiques des FAQs
        total_faqs = await self.faqs_collection.count_documents({})
        
        # Statistiques des posts (exclure les soft-deleted)
        total_posts = await self.posts_collection.count_documents({"deleted_at": {"$exists": False}})
        published_posts = await self.posts_collection.count_documents({"status": "published", "deleted_at": {"$exists": False}})
        
        # Pages récentes
        recent_pages = await self.get_pages(limit=5)
        
        # FAQs populaires (featured)
        popular_faqs = await self.get_faqs(featured_only=True)
        
        return ContentOverview(
            total_pages=total_pages,
            published_pages=published_pages,
            draft_pages=draft_pages,
            total_faqs=total_faqs,
            total_posts=total_posts,
            published_posts=published_posts,
            recent_pages=recent_pages[:3],  # Limiter à 3
            popular_faqs=popular_faqs[:5]   # Limiter à 5
        )

content_service = ContentService()
