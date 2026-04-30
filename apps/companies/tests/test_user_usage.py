import json

import pytest
from rest_framework import status

from apps.companies.models import CompanyUsage, UserUsage
from helpers.testing.tests import BaseModelTests

pytestmark = pytest.mark.django_db


class TestUserUsage(BaseModelTests):
    def init_manual_fields(self):
        self.model_class = UserUsage
        self.model_attributes = {
            "is_counted": True,
        }
        self.update_attributes = {
            "is_counted": False,
        }

        # NOTE: We'll create a new CompanyUsage instance to avoid unique_together conflicts
        company_usage = CompanyUsage.objects.create(
            date="2022-04-12", plan_name="Test plan"
        )
        company_usage.companies.add(self.company)
        self.model_relationships = {
            "user": self.user,
            "company_usage": company_usage,
        }

    def test_auto_fields_were_filled(self, client):
        """Ensure all auto fields were autofilled when the instance was created"""

        path = f"/{self.model_name}/"
        req_data = self.get_req_body()
        response = client.post(**self.get_req_args(path, data=req_data))
        attributes = json.loads(response.content)["data"]["attributes"]

        model_instance: UserUsage = self.model_class.objects.get(pk=attributes["uuid"])

        # Expected data
        usage_date = model_instance.company_usage.date.strftime("%Y-%m-%d")
        user = model_instance.user

        assert response.status_code == status.HTTP_201_CREATED
        assert attributes["usageDate"] == usage_date
        assert attributes["fullName"] == user.get_full_name()
        assert attributes["email"] == user.email
        assert attributes["username"] == user.username

    def test_user_count_increases_when_a_user_usage_is_created(self, client):
        # Create new CompanyUsage
        old_company_usage = self.model_relationships["company_usage"]
        company_usage = CompanyUsage.objects.create(
            date="2012-04-12", plan_name="Test plan"
        )
        company_usage.companies.add(self.company)
        self.model_relationships["company_usage"] = company_usage

        past_count = company_usage.user_count

        path = f"/{self.model_name}/"
        req_data = self.get_req_body()
        response = client.post(**self.get_req_args(path, data=req_data))

        company_usage = CompanyUsage.objects.get(pk=company_usage.pk)
        current_count = company_usage.user_count

        assert response.status_code == status.HTTP_201_CREATED
        assert current_count == past_count + 1

        # Reset user value
        self.model_relationships["company_usage"] = old_company_usage
