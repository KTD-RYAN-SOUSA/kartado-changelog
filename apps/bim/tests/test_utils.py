from unittest.mock import MagicMock, patch

from apps.bim.utils import delete_bim_model_and_file, delete_bim_models_by_company


class TestDeleteBimModelAndFile:
    """Testes unitários para delete_bim_model_and_file."""

    def test_delete_with_file_deletes_s3_and_db(self):
        """Deleta arquivo no S3 e registro no banco quando há arquivo."""
        bim_model = MagicMock()

        result = delete_bim_model_and_file(bim_model)

        bim_model.file.delete.assert_called_once_with(save=False)
        bim_model.delete.assert_called_once()
        assert result is True

    def test_delete_without_file_deletes_only_db(self):
        """Deleta apenas o registro no banco quando não há arquivo."""
        bim_model = MagicMock()
        bim_model.file = None

        result = delete_bim_model_and_file(bim_model)

        bim_model.delete.assert_called_once()
        assert result is True

    def test_delete_s3_failure_still_deletes_db(self):
        """Falha ao deletar do S3 é silenciada e o registro no banco é deletado mesmo assim."""
        bim_model = MagicMock()
        bim_model.file.delete.side_effect = Exception("S3 error")

        result = delete_bim_model_and_file(bim_model)

        bim_model.delete.assert_called_once()
        assert result is True

    def test_delete_db_failure_returns_false(self):
        """Retorna False quando a deleção do banco falha."""
        bim_model = MagicMock()
        bim_model.delete.side_effect = Exception("DB error")

        result = delete_bim_model_and_file(bim_model)

        assert result is False


class TestDeleteBimModelsByCompany:
    """Testes unitários para delete_bim_models_by_company."""

    def test_delete_by_company_calls_delete_for_each_model(self):
        """Chama delete_bim_model_and_file para cada modelo da company."""
        company = MagicMock()
        mock_queryset = [MagicMock(), MagicMock(), MagicMock()]

        with patch("apps.bim.models.BIMModel") as mock_model_class, patch(
            "apps.bim.utils.delete_bim_model_and_file"
        ) as mock_delete, patch("apps.bim.utils.transaction") as mock_transaction:
            mock_model_class.objects.filter.return_value.iterator.return_value = iter(
                mock_queryset
            )
            mock_transaction.atomic.return_value.__enter__ = MagicMock(
                return_value=None
            )
            mock_transaction.atomic.return_value.__exit__ = MagicMock(
                return_value=False
            )

            delete_bim_models_by_company(company)

            assert mock_delete.call_count == 3

    def test_delete_by_company_empty_queryset(self):
        """Não chama delete_bim_model_and_file quando não há modelos."""
        company = MagicMock()

        with patch("apps.bim.models.BIMModel") as mock_model_class, patch(
            "apps.bim.utils.delete_bim_model_and_file"
        ) as mock_delete, patch("apps.bim.utils.transaction") as mock_transaction:
            mock_model_class.objects.filter.return_value.iterator.return_value = iter(
                []
            )
            mock_transaction.atomic.return_value.__enter__ = MagicMock(
                return_value=None
            )
            mock_transaction.atomic.return_value.__exit__ = MagicMock(
                return_value=False
            )

            delete_bim_models_by_company(company)

            assert mock_delete.call_count == 0

    def test_delete_by_company_uses_transaction(self):
        """Executa as deleções dentro de uma transação atômica."""
        company = MagicMock()

        with patch("apps.bim.models.BIMModel") as mock_model_class, patch(
            "apps.bim.utils.transaction"
        ) as mock_transaction, patch("apps.bim.utils.delete_bim_model_and_file"):
            mock_model_class.objects.filter.return_value.iterator.return_value = iter(
                []
            )
            mock_transaction.atomic.return_value.__enter__ = MagicMock(
                return_value=None
            )
            mock_transaction.atomic.return_value.__exit__ = MagicMock(
                return_value=False
            )

            delete_bim_models_by_company(company)

            mock_transaction.atomic.assert_called_once()
            mock_transaction.atomic.return_value.__enter__.assert_called_once()
