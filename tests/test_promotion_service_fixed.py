import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId

from app.services.promotion_service import PromotionService
from app.models.promotion import PromotionCreate, PromotionUpdate, PromotionStatus


class TestPromotionService:
    """Tests unitaires pour PromotionService."""

    @pytest.fixture
    def service(self):
        """Instance du service pour les tests."""
        return PromotionService()

    @pytest.fixture
    def sample_promotion_data(self):
        """Données de test pour une promotion."""
        return {
            "name": "Promotion Test",
            "description": "Description test",
            "discount_percentage": 20.0,
            "start_date": datetime.now(),
            "end_date": datetime.now() + timedelta(days=7)
        }

    @pytest.mark.asyncio
    async def test_create_promotion_success(self, service, sample_promotion_data):
        """Test création promotion réussie."""
        # Setup
        with patch.object(service, 'get_active_promotion', return_value=None), \
             patch.object(service, 'promotions_collection') as mock_collection:

            mock_collection.insert_one.return_value = AsyncMock(inserted_id=ObjectId())

            promotion_create = PromotionCreate(**sample_promotion_data)

            # Execute
            result = await service.create_promotion(promotion_create, "admin_id")

            # Assert
            assert result.name == sample_promotion_data["name"]
            assert result.discount_percentage == sample_promotion_data["discount_percentage"]
            assert result.status == PromotionStatus.ACTIVE
            mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_promotion_active_exists_error(self, service, sample_promotion_data):
        """Test erreur quand une promotion active existe déjà."""
        # Setup
        mock_active_promotion = MagicMock()
        with patch.object(service, 'get_active_promotion', return_value=mock_active_promotion):

            promotion_create = PromotionCreate(**sample_promotion_data)

            # Execute & Assert
            with pytest.raises(ValueError, match="Une promotion est déjà active"):
                await service.create_promotion(promotion_create, "admin_id")

    @pytest.mark.asyncio
    async def test_get_promotion_success(self, service):
        """Test récupération promotion réussie."""
        # Setup
        promotion_id = str(ObjectId())
        mock_promotion = {
            "_id": ObjectId(promotion_id),
            "name": "Test Promotion",
            "discount_percentage": 15.0,
            "is_active": True,
            "start_date": datetime.now(),
            "end_date": datetime.now() + timedelta(days=1),
            "created_by": "admin_id",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        with patch.object(service, 'promotions_collection') as mock_collection:
            mock_collection.find_one.return_value = mock_promotion

            # Execute
            result = await service.get_promotion(promotion_id)

            # Assert
            assert result is not None
            assert result.name == "Test Promotion"
            assert result.status == PromotionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_promotion_not_found(self, service):
        """Test récupération promotion inexistante."""
        # Setup
        with patch.object(service, 'promotions_collection') as mock_collection:
            mock_collection.find_one.return_value = None

            # Execute
            result = await service.get_promotion("invalid_id")

            # Assert
            assert result is None

    @pytest.mark.asyncio
    async def test_get_active_promotion_success(self, service):
        """Test récupération promotion active."""
        # Setup
        mock_promotion = {
            "_id": ObjectId(),
            "name": "Active Promotion",
            "discount_percentage": 10.0,
            "is_active": True,
            "start_date": datetime.now() - timedelta(hours=1),
            "end_date": datetime.now() + timedelta(hours=1),
            "created_by": "admin_id",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        with patch.object(service, 'promotions_collection') as mock_collection:
            mock_collection.find_one.return_value = mock_promotion

            # Execute
            result = await service.get_active_promotion()

            # Assert
            assert result is not None
            assert result.name == "Active Promotion"

    @pytest.mark.asyncio
    async def test_get_active_promotion_none(self, service):
        """Test aucune promotion active."""
        # Setup
        with patch.object(service, 'promotions_collection') as mock_collection:
            mock_collection.find_one.return_value = None

            # Execute
            result = await service.get_active_promotion()

            # Assert
            assert result is None

    @pytest.mark.asyncio
    async def test_calculate_discounted_price_with_promotion(self, service):
        """Test calcul prix réduit avec promotion active."""
        # Setup
        original_price = 100.0
        discount_percentage = 20.0
        mock_promotion = {
            "_id": ObjectId(),
            "discount_percentage": discount_percentage,
            "is_active": True,
            "start_date": datetime.now() - timedelta(hours=1),
            "end_date": datetime.now() + timedelta(hours=1),
            "created_by": "admin_id",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        with patch.object(service, 'get_active_promotion', return_value=mock_promotion):
            # Execute
            discounted_price, discount_amount = await service.calculate_discounted_price(original_price)

            # Assert
            expected_discount = original_price * (discount_percentage / 100)
            expected_discounted = original_price - expected_discount
            assert discounted_price == expected_discounted
            assert discount_amount == expected_discount

    @pytest.mark.asyncio
    async def test_calculate_discounted_price_no_promotion(self, service):
        """Test calcul prix réduit sans promotion active."""
        # Setup
        original_price = 100.0

        with patch.object(service, 'get_active_promotion', return_value=None):
            # Execute
            discounted_price, discount_amount = await service.calculate_discounted_price(original_price)

            # Assert
            assert discounted_price == original_price
            assert discount_amount == 0.0

    def test_get_promotion_status_active(self, service):
        """Test détermination statut promotion active."""
        promotion = {
            "is_active": True,
            "start_date": datetime.now() - timedelta(hours=1),
            "end_date": datetime.now() + timedelta(hours=1)
        }
        status = service._get_promotion_status(promotion)
        assert status == PromotionStatus.ACTIVE

    def test_get_promotion_status_inactive(self, service):
        """Test détermination statut promotion inactive."""
        promotion = {
            "is_active": False,
            "start_date": datetime.now() - timedelta(hours=1),
            "end_date": datetime.now() + timedelta(hours=1)
        }
        status = service._get_promotion_status(promotion)
        assert status == PromotionStatus.INACTIVE

    def test_get_promotion_status_expired(self, service):
        """Test détermination statut promotion expirée."""
        promotion = {
            "is_active": True,
            "start_date": datetime.now() - timedelta(hours=2),
            "end_date": datetime.now() - timedelta(hours=1)
        }
        status = service._get_promotion_status(promotion)
        assert status == PromotionStatus.EXPIRED
