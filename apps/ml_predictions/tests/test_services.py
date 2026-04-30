import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.ml_predictions.models import MLPrediction, MLPredictionConfig
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestFetchPredictions(TestBase):
    model = "MLPrediction"

    def _run_fetch(self):
        from apps.ml_predictions.services import fetch_predictions

        return fetch_predictions.sync()

    @patch("apps.ml_predictions.services.DatabricksClient")
    def test_fetch_creates_new_predictions(self, mock_client_class, client):
        MLPredictionConfig.objects.create(company=self.company)
        rdo_1 = str(uuid.uuid4())
        rdo_2 = str(uuid.uuid4())

        mock_client = MagicMock()
        mock_client.predict_by_company.return_value = [
            {"id_rdo": rdo_1, "classe": 1, "descClasse": "revisao"},
            {"id_rdo": rdo_2, "classe": 0, "descClasse": "aprovado"},
        ]
        mock_client_class.return_value = mock_client

        total = self._run_fetch()

        assert total == 2
        assert MLPrediction.objects.filter(company=self.company).count() == 2

    @patch("apps.ml_predictions.services.DatabricksClient")
    def test_fetch_ignores_duplicates(self, mock_client_class, client):
        MLPredictionConfig.objects.create(company=self.company)
        rdo_1 = str(uuid.uuid4())
        rdo_2 = str(uuid.uuid4())

        MLPrediction.objects.create(
            company=self.company,
            output_data={"id_rdo": rdo_1, "classe": 1},
        )

        mock_client = MagicMock()
        mock_client.predict_by_company.return_value = [
            {"id_rdo": rdo_1, "classe": 1, "descClasse": "revisao"},
            {"id_rdo": rdo_2, "classe": 0, "descClasse": "aprovado"},
        ]
        mock_client_class.return_value = mock_client

        total = self._run_fetch()

        assert total == 1
        assert MLPrediction.objects.filter(company=self.company).count() == 2

    @patch("apps.ml_predictions.services.DatabricksClient")
    def test_fetch_with_no_configs(self, mock_client_class, client):
        MLPredictionConfig.objects.all().delete()
        total = self._run_fetch()

        assert total == 0

    @patch("apps.ml_predictions.services.DatabricksClient")
    def test_fetch_with_empty_results(self, mock_client_class, client):
        MLPredictionConfig.objects.create(company=self.company)

        mock_client = MagicMock()
        mock_client.predict_by_company.return_value = None
        mock_client_class.return_value = mock_client

        total = self._run_fetch()

        assert total == 0
        assert MLPrediction.objects.filter(company=self.company).count() == 0

    @patch("apps.ml_predictions.services.DatabricksClient")
    def test_fetch_skips_items_without_rdo_id(self, mock_client_class, client):
        MLPredictionConfig.objects.create(company=self.company)
        rdo_1 = str(uuid.uuid4())

        mock_client = MagicMock()
        mock_client.predict_by_company.return_value = [
            {"classe": 1, "descClasse": "revisao"},
            {"id_rdo": rdo_1, "classe": 0, "descClasse": "aprovado"},
        ]
        mock_client_class.return_value = mock_client

        total = self._run_fetch()

        assert total == 1

    @patch("apps.ml_predictions.services.DatabricksClient")
    def test_fetch_continues_on_error(self, mock_client_class, client):
        MLPredictionConfig.objects.create(company=self.company)

        mock_client = MagicMock()
        mock_client.predict_by_company.side_effect = Exception("Connection error")
        mock_client_class.return_value = mock_client

        total = self._run_fetch()

        assert total == 0
