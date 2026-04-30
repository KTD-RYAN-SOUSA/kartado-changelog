from unittest.mock import patch

import pytest

from apps.resources.models import MeasurementBulletinExport
from apps.service_orders.models import MeasurementBulletin
from helpers.measurement_bulletin import generate_bulletin
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestMeasurementBulletin(TestBase):
    model = "Helpers"

    @pytest.mark.django_db
    def test_generate_bulletin(self):
        """Test the generate_bulletin function."""
        measurement_bulletin = MeasurementBulletin.objects.first()
        measuremente_bulletin_export = MeasurementBulletinExport.objects.create(
            created_by=self.user,
            measurement_bulletin=measurement_bulletin,
            done=False,
            error=False,
        )

        generate_bulletin(str(measuremente_bulletin_export.uuid))

        # Recarregar do banco de dados
        measuremente_bulletin_export.refresh_from_db()

        assert measuremente_bulletin_export.done is True
        assert measuremente_bulletin_export.error is False

    @pytest.mark.django_db
    @patch("helpers.measurement_bulletin.capture_exception")
    @patch("helpers.measurement_bulletin.logging.error")
    def test_generate_bulletin_error(self, mock_logging_error, mock_capture_exception):
        """Test the generate_bulletin function with error handling."""

        # Use a valid UUID format but non-existent ID
        generate_bulletin("00000000-0000-0000-0000-000000000000")

        # Check that logging.error was called
        mock_logging_error.assert_called_once()

        # Verify capture_exception was called with some exception
        assert mock_capture_exception.called
