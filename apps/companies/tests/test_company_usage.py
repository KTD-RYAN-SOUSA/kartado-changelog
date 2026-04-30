import json

import pytest
from rest_framework import status

from apps.companies.models import CompanyUsage
from helpers.testing.tests import BaseModelTests

pytestmark = pytest.mark.django_db


class TestCompanyUsage(BaseModelTests):
    def init_manual_fields(self):
        self.model_class = CompanyUsage
        self.model_attributes = {
            "date": "2024-08-01",
            "plan_name": "Original Plan",
        }
        self.update_attributes = {
            "plan_name": "Edited Plan",
        }
        self.model_relationships = {
            "companies": [self.company],
            "users": [self.user],
        }

    def test_auto_fields_were_filled(self, client):
        """Ensure all auto fields were autofilled when the instance was created"""

        path = f"/{self.model_name}/"
        req_data = self.get_req_body()
        response = client.post(**self.get_req_args(path, data=req_data))
        attributes = json.loads(response.content)["data"]["attributes"]

        model_instance: CompanyUsage = self.model_class.objects.get(
            pk=attributes["uuid"]
        )

        # Expected data
        company_data = list(model_instance.companies.values_list("name", "cnpj"))
        cnpj = next((cnpj for _, cnpj in company_data if cnpj), "")
        company_names = [name for name, _ in company_data if name]
        user_count = model_instance.user_usages.filter(is_counted=True).count()

        assert response.status_code == status.HTTP_201_CREATED
        assert attributes["cnpj"] == cnpj
        assert attributes["companyNames"] == company_names
        assert attributes["userCount"] == user_count
