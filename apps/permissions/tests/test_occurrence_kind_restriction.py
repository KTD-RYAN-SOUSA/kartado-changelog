import pytest

from apps.permissions.models import PermissionOccurrenceKindRestriction, UserPermission
from helpers.permissions import PermissionManager
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestPermissionOccurrenceKindRestriction(TestBase):
    model = "OccurrenceType"

    def test_get_allowed_occurrence_kinds_without_restriction(self, client):
        """Without any restriction configured, should return empty list (full access)."""
        permission_manager = PermissionManager(
            company_ids=self.company.uuid,
            user=self.user,
            model=self.model,
        )

        allowed_kinds = permission_manager.get_allowed_occurrence_kinds()

        assert allowed_kinds == []

    def test_get_allowed_occurrence_kinds_with_restriction(self, client):
        """With restriction configured, should return the allowed kinds."""
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        PermissionOccurrenceKindRestriction.objects.create(
            user_permission=user_permission,
            company=self.company,
            allowed_occurrence_kinds=["1", "2", "3"],
        )

        permission_manager = PermissionManager(
            company_ids=self.company.uuid,
            user=self.user,
            model=self.model,
        )

        allowed_kinds = permission_manager.get_allowed_occurrence_kinds()

        assert sorted(allowed_kinds) == ["1", "2", "3"]

    def test_get_allowed_occurrence_kinds_empty_list_means_full_access(self, client):
        """With empty allowed_occurrence_kinds list, should return empty (full access)."""
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        PermissionOccurrenceKindRestriction.objects.create(
            user_permission=user_permission,
            company=self.company,
            allowed_occurrence_kinds=[],
        )

        permission_manager = PermissionManager(
            company_ids=self.company.uuid,
            user=self.user,
            model=self.model,
        )

        allowed_kinds = permission_manager.get_allowed_occurrence_kinds()

        # Empty list in restriction means no specific kinds allowed,
        # but the merge logic returns empty set which equals full access
        assert allowed_kinds == []

    def test_get_allowed_occurrence_kinds_different_company_no_restriction(
        self, client
    ):
        """Restriction for different company should not affect current company."""
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        # Create another company's restriction (should not affect)
        from apps.companies.models import Company

        other_company = Company.objects.exclude(uuid=self.company.uuid).first()
        if other_company:
            PermissionOccurrenceKindRestriction.objects.create(
                user_permission=user_permission,
                company=other_company,
                allowed_occurrence_kinds=["99"],
            )

        permission_manager = PermissionManager(
            company_ids=self.company.uuid,
            user=self.user,
            model=self.model,
        )

        allowed_kinds = permission_manager.get_allowed_occurrence_kinds()

        # Should return empty (full access) since restriction is for other company
        assert allowed_kinds == []

    def test_restriction_model_str(self, client):
        """Test __str__ method of PermissionOccurrenceKindRestriction."""
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        restriction = PermissionOccurrenceKindRestriction.objects.create(
            user_permission=user_permission,
            company=self.company,
            allowed_occurrence_kinds=["1"],
        )

        expected_str = f"{user_permission.name} - {self.company.name}"
        assert str(restriction) == expected_str

    def test_restriction_unique_together(self, client):
        """Test unique_together constraint (user_permission, company)."""
        user_permission = UserPermission.objects.filter(companies=self.company).first()

        PermissionOccurrenceKindRestriction.objects.create(
            user_permission=user_permission,
            company=self.company,
            allowed_occurrence_kinds=["1"],
        )

        # Trying to create another restriction for same permission+company should fail
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            PermissionOccurrenceKindRestriction.objects.create(
                user_permission=user_permission,
                company=self.company,
                allowed_occurrence_kinds=["2"],
            )

    def test_restriction_cascade_delete_on_user_permission(self, client):
        """Test that restriction is deleted when UserPermission is deleted."""
        user_permission = UserPermission.objects.create(name="TEST_DELETE")
        user_permission.companies.add(self.company)

        restriction = PermissionOccurrenceKindRestriction.objects.create(
            user_permission=user_permission,
            company=self.company,
            allowed_occurrence_kinds=["1"],
        )
        restriction_uuid = restriction.uuid

        user_permission.delete()

        assert not PermissionOccurrenceKindRestriction.objects.filter(
            uuid=restriction_uuid
        ).exists()
