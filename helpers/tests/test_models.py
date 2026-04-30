from unittest.mock import Mock

import pytest
from django.test import TestCase

pytestmark = pytest.mark.django_db


class TestAbstractBaseModel(TestCase):
    """Tests for AbstractBaseModel"""

    def test_get_company_id_with_company(self):
        """Test get_company_id when company exists"""
        from helpers.models import AbstractBaseModel

        instance = Mock(spec=AbstractBaseModel)
        mock_company = Mock()
        mock_company.pk = "company-uuid-123"
        instance.company = mock_company

        result = AbstractBaseModel.get_company_id.fget(instance)

        assert result == "company-uuid-123"

    def test_get_company_id_without_company(self):
        """Test get_company_id when company is None"""
        from helpers.models import AbstractBaseModel

        instance = Mock(spec=AbstractBaseModel)
        instance.company = None

        result = AbstractBaseModel.get_company_id.fget(instance)

        assert result is None

    def test_str_not_implemented(self):
        """Test that __str__ raises NotImplementedError"""
        from helpers.models import AbstractBaseModel

        instance = Mock(spec=AbstractBaseModel)

        with self.assertRaises(NotImplementedError) as context:
            AbstractBaseModel.__str__(instance)

        assert "Please provide a proper __str__ method" in str(context.exception)
