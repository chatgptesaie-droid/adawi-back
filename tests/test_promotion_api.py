import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from bson import ObjectId

from app.main import app
from app.models.promotion import PromotionCreate


class TestPromotionAPI:
    """Tests d'intégration pour l'API des promotions."""

    @pytest.fixture
    async def client(self):
        """Client de test HTTP."""
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            yield client

    @pytest.fixture
    def sample_promotion_data(self):
        """Données de test pour une promotion."""
        return {
            "name": "Promotion API Test",
            "description": "Test API promotion",
            "discount_percentage": 15.0,
            "start_date": datetime.utcnow().isoformat(),
            "end_date": (datetime.utcnow() + timedelta(days=7)).isoformat()
        }

    @pytest.fixture
    def mock_current_user(self):
        """Mock utilisateur authentifié."""
        return {
            "id": "user_id",
            "email": "test@example.com",
            "roles": ["user"]
        }

    @pytest.fixture
    def mock_admin_user(self):
        """Mock utilisateur admin."""
        return {
            "id": "admin_id",
            "email": "admin@example.com",
            "roles": ["admin"]
        }

    @pytest.mark.asyncio
    async def test_create_promotion_success(self, client, sample_promotion_data, mock_admin_user):
        """Test création promotion API réussie."""
        # Setup
        with patch('app.api.promotions.get_current_user_dependency', return_value=mock_admin_user), \
             patch('app.services.promotion_service.promotion_service.create_promotion', new_callable=AsyncMock) as mock_create:

            mock_promotion = AsyncMock()
            mock_promotion.name = sample_promotion_data["name"]
            mock_promotion.discount_percentage = sample_promotion_data["discount_percentage"]
            mock_create.return_value = mock_promotion

            # Execute
            response = await client.post("/promotions/", json=sample_promotion_data)

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == sample_promotion_data["name"]
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_promotion_unauthorized(self, client, sample_promotion_data, mock_current_user):
        """Test création promotion sans droits admin."""
        # Setup
        with patch('app.api.promotions.get_current_user_dependency', return_value=mock_current_user):

            # Execute
            response = await client.post("/promotions/", json=sample_promotion_data)

            # Assert
            assert response.status_code == 403
            assert "Accès refusé" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_promotions_success(self, client, mock_current_user):
        """Test récupération liste promotions."""
        # Setup
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.get_all_promotions', new_callable=AsyncMock) as mock_get_all:

            mock_promotions = [AsyncMock(id="1", name="Promo 1"), AsyncMock(id="2", name="Promo 2")]
            mock_get_all.return_value = mock_promotions

            # Execute
            response = await client.get("/promotions/")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "promotions" in data
            assert "total" in data
            assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_get_promotion_by_id_success(self, client, mock_current_user):
        """Test récupération promotion par ID."""
        # Setup
        promotion_id = str(ObjectId())
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.get_promotion', new_callable=AsyncMock) as mock_get:

            mock_promotion = AsyncMock(id=promotion_id, name="Test Promotion")
            mock_get.return_value = mock_promotion

            # Execute
            response = await client.get(f"/promotions/{promotion_id}")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == promotion_id

    @pytest.mark.asyncio
    async def test_get_promotion_by_id_not_found(self, client, mock_current_user):
        """Test récupération promotion inexistante."""
        # Setup
        promotion_id = str(ObjectId())
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.get_promotion', new_callable=AsyncMock) as mock_get:

            mock_get.return_value = None

            # Execute
            response = await client.get(f"/promotions/{promotion_id}")

            # Assert
            assert response.status_code == 404
            assert "Promotion non trouvée" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_active_promotion_success(self, client, mock_current_user):
        """Test récupération promotion active."""
        # Setup
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.get_active_promotion', new_callable=AsyncMock) as mock_get_active:

            mock_promotion = AsyncMock(id="active_id", name="Active Promotion")
            mock_get_active.return_value = mock_promotion

            # Execute
            response = await client.get("/promotions/active")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Active Promotion"

    @pytest.mark.asyncio
    async def test_get_active_promotion_none(self, client, mock_current_user):
        """Test aucune promotion active."""
        # Setup
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.get_active_promotion', new_callable=AsyncMock) as mock_get_active:

            mock_get_active.return_value = None

            # Execute
            response = await client.get("/promotions/active")

            # Assert
            assert response.status_code == 200
            assert response.json() is None

    @pytest.mark.asyncio
    async def test_update_promotion_success(self, client, mock_admin_user):
        """Test mise à jour promotion API."""
        # Setup
        promotion_id = str(ObjectId())
        update_data = {"name": "Updated Promotion"}
        with patch('app.api.promotions.require_admin_user', return_value=mock_admin_user), \
             patch('app.services.promotion_service.promotion_service.update_promotion', new_callable=AsyncMock) as mock_update:

            mock_updated_promotion = AsyncMock(id=promotion_id, name="Updated Promotion")
            mock_update.return_value = mock_updated_promotion

            # Execute
            response = await client.put(f"/promotions/{promotion_id}", json=update_data)

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated Promotion"

    @pytest.mark.asyncio
    async def test_delete_promotion_success(self, client, mock_admin_user):
        """Test suppression promotion API."""
        # Setup
        promotion_id = str(ObjectId())
        with patch('app.api.promotions.require_admin_user', return_value=mock_admin_user), \
             patch('app.services.promotion_service.promotion_service.delete_promotion', new_callable=AsyncMock) as mock_delete:

            mock_delete.return_value = True

            # Execute
            response = await client.delete(f"/promotions/{promotion_id}")

            # Assert
            assert response.status_code == 200
            assert "supprimée" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_delete_promotion_not_found(self, client, mock_admin_user):
        """Test suppression promotion inexistante."""
        # Setup
        promotion_id = str(ObjectId())
        with patch('app.api.promotions.require_admin_user', return_value=mock_admin_user), \
             patch('app.services.promotion_service.promotion_service.delete_promotion', new_callable=AsyncMock) as mock_delete:

            mock_delete.return_value = False

            # Execute
            response = await client.delete(f"/promotions/{promotion_id}")

            # Assert
            assert response.status_code == 404
            assert "Promotion non trouvée" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_deactivate_promotion_success(self, client, mock_admin_user):
        """Test désactivation promotion API."""
        # Setup
        promotion_id = str(ObjectId())
        with patch('app.api.promotions.require_admin_user', return_value=mock_admin_user), \
             patch('app.services.promotion_service.promotion_service.deactivate_promotion', new_callable=AsyncMock) as mock_deactivate:

            mock_deactivate.return_value = True

            # Execute
            response = await client.patch(f"/promotions/{promotion_id}/deactivate")

            # Assert
            assert response.status_code == 200
            assert "désactivée" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_calculate_discount_success(self, client, mock_current_user):
        """Test calcul réduction API."""
        # Setup
        original_price = 200.0
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.calculate_discounted_price', new_callable=AsyncMock) as mock_calculate:

            mock_calculate.return_value = (160.0, 40.0)  # 20% discount

            # Execute
            response = await client.post("/promotions/calculate-discount", json={"original_price": original_price})

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["original_price"] == original_price
            assert data["discounted_price"] == 160.0
            assert data["discount_amount"] == 40.0
            assert data["has_discount"] is True

    @pytest.mark.asyncio
    async def test_calculate_discount_no_promotion(self, client, mock_current_user):
        """Test calcul réduction sans promotion."""
        # Setup
        original_price = 200.0
        with patch('app.api.promotions.get_current_user', return_value=mock_current_user), \
             patch('app.services.promotion_service.promotion_service.calculate_discounted_price', new_callable=AsyncMock) as mock_calculate:

            mock_calculate.return_value = (200.0, 0.0)  # No discount

            # Execute
            response = await client.post("/promotions/calculate-discount", json={"original_price": original_price})

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["original_price"] == original_price
            assert data["discounted_price"] == 200.0
            assert data["discount_amount"] == 0.0
            assert data["has_discount"] is False
