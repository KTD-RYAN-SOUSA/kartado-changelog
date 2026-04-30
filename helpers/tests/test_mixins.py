from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestUUIDMixin(TestCase):
    """Tests for UUIDMixin"""

    def test_validate_uuid_on_create_with_existing_uuid(self):
        """Test UUID validation on create action when UUID already exists"""
        from helpers.mixins import UUIDMixin

        class MockSerializer(UUIDMixin):
            class Meta:
                model = Mock()

        serializer = MockSerializer()
        serializer._context = {"view": Mock(action="create")}

        mock_obj = Mock()
        serializer.Meta.model.objects.get.return_value = mock_obj

        from rest_framework_json_api import serializers

        with self.assertRaises(serializers.ValidationError) as context:
            serializer.validate_uuid("existing-uuid")

        assert "Já existe um objeto com este identificador" in str(context.exception)

    def test_validate_uuid_on_create_with_new_uuid(self):
        """Test UUID validation on create action when UUID doesn't exist"""
        from django.core.exceptions import ObjectDoesNotExist

        from helpers.mixins import UUIDMixin

        class MockSerializer(UUIDMixin):
            class Meta:
                model = Mock()

        serializer = MockSerializer()
        serializer._context = {"view": Mock(action="create")}

        serializer.Meta.model.objects.get.side_effect = ObjectDoesNotExist

        result = serializer.validate_uuid("new-uuid")

        assert result == "new-uuid"

    def test_validate_uuid_on_update_action(self):
        """Test UUID validation on update action (should skip validation)"""
        from helpers.mixins import UUIDMixin

        class MockSerializer(UUIDMixin):
            class Meta:
                model = Mock()

        serializer = MockSerializer()
        serializer._context = {"view": Mock(action="update")}

        result = serializer.validate_uuid("any-uuid")

        assert result == "any-uuid"
        serializer.Meta.model.objects.get.assert_not_called()

    def test_validate_uuid_with_no_action(self):
        """Test UUID validation when action is empty"""
        from helpers.mixins import UUIDMixin

        class MockSerializer(UUIDMixin):
            class Meta:
                model = Mock()

        serializer = MockSerializer()
        serializer._context = {"view": Mock(action="")}

        result = serializer.validate_uuid("any-uuid")

        assert result == "any-uuid"


class TestEagerLoadingMixin(TestCase):
    """Tests for EagerLoadingMixin"""

    def test_setup_eager_loading_with_select_related(self):
        """Test eager loading with select_related fields"""
        from helpers.mixins import EagerLoadingMixin

        class MockSerializer(EagerLoadingMixin):
            _SELECT_RELATED_FIELDS = ["company", "user"]

        mock_queryset = Mock()
        mock_queryset.select_related.return_value = mock_queryset

        MockSerializer.setup_eager_loading(mock_queryset)

        mock_queryset.select_related.assert_called_once_with("company", "user")

    def test_setup_eager_loading_with_prefetch_related(self):
        """Test eager loading with prefetch_related fields"""
        from helpers.mixins import EagerLoadingMixin

        class MockSerializer(EagerLoadingMixin):
            _PREFETCH_RELATED_FIELDS = ["permissions", "groups"]

        mock_queryset = Mock()
        mock_queryset.prefetch_related.return_value = mock_queryset

        MockSerializer.setup_eager_loading(mock_queryset)

        mock_queryset.prefetch_related.assert_called_once_with("permissions", "groups")

    def test_setup_eager_loading_with_both(self):
        """Test eager loading with both select_related and prefetch_related"""
        from helpers.mixins import EagerLoadingMixin

        class MockSerializer(EagerLoadingMixin):
            _SELECT_RELATED_FIELDS = ["company"]
            _PREFETCH_RELATED_FIELDS = ["permissions"]

        mock_queryset = Mock()
        mock_queryset.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset

        MockSerializer.setup_eager_loading(mock_queryset)

        mock_queryset.select_related.assert_called_once_with("company")
        mock_queryset.prefetch_related.assert_called_once_with("permissions")

    def test_setup_eager_loading_without_fields(self):
        """Test eager loading when no fields are defined"""
        from helpers.mixins import EagerLoadingMixin

        class MockSerializer(EagerLoadingMixin):
            pass

        mock_queryset = Mock()

        result = MockSerializer.setup_eager_loading(mock_queryset)

        assert result == mock_queryset
        mock_queryset.select_related.assert_not_called()
        mock_queryset.prefetch_related.assert_not_called()


class TestListCacheMixin(TestCase):
    """Tests for ListCacheMixin"""

    @patch("helpers.mixins.cache_page")
    def test_list_cache_mixin_default_timeout(self, mock_cache_page):
        """Test ListCacheMixin with default timeout"""
        from helpers.mixins import ListCacheMixin

        class MockViewSet(ListCacheMixin):
            def list(self, request, *args, **kwargs):
                return super().list(request, *args, **kwargs)

        viewset = MockViewSet()

        assert viewset.cache_timeout == 60 * 60  # 1 hour

    @patch("helpers.mixins.cache_page")
    def test_list_cache_mixin_custom_timeout(self, mock_cache_page):
        """Test ListCacheMixin with custom timeout"""
        from helpers.mixins import ListCacheMixin

        class MockViewSet(ListCacheMixin):
            cache_timeout = 300  # 5 minutes

        viewset = MockViewSet()

        assert viewset.cache_timeout == 300


class TestRetrieveCacheMixin(TestCase):
    """Tests for RetrieveCacheMixin"""

    @patch("helpers.mixins.cache_page")
    def test_retrieve_cache_mixin_default_timeout(self, mock_cache_page):
        """Test RetrieveCacheMixin with default timeout"""
        from helpers.mixins import RetrieveCacheMixin

        class MockViewSet(RetrieveCacheMixin):
            def retrieve(self, request, *args, **kwargs):
                return super().retrieve(request, *args, **kwargs)

        viewset = MockViewSet()

        assert viewset.cache_timeout == 60 * 60  # 1 hour

    @patch("helpers.mixins.cache_page")
    def test_retrieve_cache_mixin_custom_timeout(self, mock_cache_page):
        """Test RetrieveCacheMixin with custom timeout"""
        from helpers.mixins import RetrieveCacheMixin

        class MockViewSet(RetrieveCacheMixin):
            cache_timeout = 300  # 5 minutes

            def retrieve(self, request, *args, **kwargs):
                return super().retrieve(request, *args, **kwargs)

        viewset = MockViewSet()

        assert viewset.cache_timeout == 300
