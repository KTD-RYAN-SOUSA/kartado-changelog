import pytest
from django.test import TestCase

from apps.users.models import User
from helpers.permissions import join_queryset

pytestmark = pytest.mark.django_db


class TestJoinQueryset(TestCase):
    def test_join_queryset_when_first_is_none(self):
        other = ["some", "list"]
        result = join_queryset(None, other)
        assert result is other

    @pytest.mark.django_db
    def test_join_queryset_two_querysets(self):
        qs1 = User.objects.all()
        qs2 = User.objects.none()
        result = join_queryset(qs1, qs2)
        assert hasattr(result, "query")

    def test_join_queryset_non_queryset_returns_first(self):
        first = [1, 2, 3]
        other = [4, 5, 6]
        result = join_queryset(first, other)
        assert result is first
