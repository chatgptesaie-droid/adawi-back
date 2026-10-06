from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# === PAGES CMS ===

class PageStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"

class PageBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    title: str = Field(..., min_length=1, max_length=200)
    body_html: str = Field("", description="Contenu HTML de la page")
    meta_description: Optional[str] = Field(None, max_length=160)
    meta_keywords: Optional[str] = None
    status: PageStatus = PageStatus.draft

class PageCreate(PageBase):
    pass

class PageUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    body_html: Optional[str] = None
    meta_description: Optional[str] = Field(None, max_length=160)
    meta_keywords: Optional[str] = None
    status: Optional[PageStatus] = None

class PageInDB(PageBase):
    id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    author_id: Optional[str] = None
    views_count: int = 0

class PagePublic(PageBase):
    id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    author_name: Optional[str] = None
    views_count: int = 0

# === FAQ ===

class FAQCategory(str, Enum):
    general = "general"
    commande = "commande"
    livraison = "livraison"
    retour = "retour"
    paiement = "paiement"
    compte = "compte"
    produit = "produit"

class FAQBase(BaseModel):
    question: str = Field(..., min_length=5, max_length=300)
    answer: str = Field(..., min_length=10)
    category: FAQCategory = FAQCategory.general
    order: int = Field(0, ge=0, description="Ordre d'affichage")
    is_featured: bool = Field(False, description="Question mise en avant")

class FAQCreate(FAQBase):
    pass

class FAQUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=5, max_length=300)
    answer: Optional[str] = Field(None, min_length=10)
    category: Optional[FAQCategory] = None
    order: Optional[int] = Field(None, ge=0)
    is_featured: Optional[bool] = None

class FAQInDB(FAQBase):
    id: str
    created_at: datetime
    updated_at: datetime

class FAQPublic(FAQBase):
    id: str
    created_at: datetime
    updated_at: datetime

# === GUIDE TAILLES ===

class SizeChartBase(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    size_chart: Dict[str, Any] = Field(..., description="Structure du guide des tailles")
    image_url: Optional[str] = None
    order: int = Field(0, ge=0)

class SizeChartCreate(SizeChartBase):
    pass

class SizeChartUpdate(BaseModel):
    category_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    size_chart: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None
    order: Optional[int] = Field(None, ge=0)

class SizeChartInDB(SizeChartBase):
    id: str
    created_at: datetime
    updated_at: datetime

class SizeChartPublic(SizeChartBase):
    id: str
    created_at: datetime
    updated_at: datetime

# === BLOG (OPTIONNEL) ===

class PostStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"

class PostBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    excerpt: Optional[str] = Field(None, max_length=300)
    content: str = Field(..., min_length=10)
    cover_image: Optional[str] = None
    tags: List[str] = []
    status: PostStatus = PostStatus.draft

class PostCreate(PostBase):
    pass

class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    excerpt: Optional[str] = Field(None, max_length=300)
    content: Optional[str] = Field(None, min_length=10)
    cover_image: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[PostStatus] = None

class PostInDB(PostBase):
    id: str
    author_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    views_count: int = 0

class PostPublic(PostBase):
    id: str
    author_id: str
    author_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    views_count: int = 0

class PostSummary(BaseModel):
    """Version résumée pour les listes"""
    id: str
    title: str
    slug: str
    excerpt: Optional[str] = None
    cover_image: Optional[str] = None
    tags: List[str] = []
    author_name: Optional[str] = None
    published_at: Optional[datetime] = None
    views_count: int = 0

# === MODÈLES DE RÉPONSE ===

class ContentOverview(BaseModel):
    """Aperçu du contenu pour l'admin"""
    total_pages: int
    published_pages: int
    draft_pages: int
    total_faqs: int
    total_posts: int
    published_posts: int
    recent_pages: List[PagePublic] = []
    popular_faqs: List[FAQPublic] = []
