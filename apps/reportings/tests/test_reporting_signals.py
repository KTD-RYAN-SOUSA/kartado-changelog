import uuid
from unittest.mock import Mock, patch

import pytest
from django.contrib.gis.geos import Point
from django.test import TestCase

from apps.reportings.models import Reporting
from apps.reportings.signals import (
    add_last_monitoring_files,
    check_road_name_and_point,
    fill_lot_field,
)

pytestmark = pytest.mark.django_db


class ReportingSignalsTestCase(TestCase):
    def setUp(self):
        self.company = Mock()
        self.company.metadata = {}

        self.road = Mock()
        self.road.name = "Test Road"
        self.road.lot_logic = {"some": "logic"}
        self.road.lane_type_logic = {"system_logic": {"some": "system_logic"}}

        self.occurrence_type = Mock()
        self.occurrence_type.pk = "123"
        self.occurrence_type.form_fields = {}

        self.reporting = Mock(spec=Reporting)
        self.reporting.company = self.company
        self.reporting.road = self.road
        self.reporting.road_name = "Test Road"
        self.reporting.km = 10.0
        self.reporting.end_km = 15.0
        self.reporting.direction = "North"
        self.reporting.point = Point(0, 0)
        self.reporting.geometry = None
        self.reporting.lot = None
        self.reporting.occurrence_type = self.occurrence_type
        self.reporting.form_data = {}
        self.reporting.form_metadata = {}
        self.reporting._state = Mock()
        self.reporting._state.adding = False

    @patch("apps.reportings.signals.get_obj_from_path")
    @patch("apps.reportings.signals.get_road_coordinates")
    @patch("apps.reportings.signals.bulk_update_with_history")
    def test_check_road_name_and_point_updates_geometry(
        self, mock_bulk_update, mock_get_road_coordinates, mock_get_obj_from_path
    ):
        """Testa se o signal check_road_name_and_point atualiza a geometria quando necessário"""
        mock_get_obj_from_path.return_value = False
        test_point = Point(1, 1)
        test_road = Mock()
        test_road.name = "New Road"
        test_road.lot_logic = {"some": "logic"}
        mock_get_road_coordinates.return_value = (test_point, test_road)

        check_road_name_and_point(
            sender=Reporting, created=False, instance=self.reporting
        )

        self.assertEqual(self.reporting.point, test_point)
        self.assertIsNotNone(self.reporting.geometry)
        mock_bulk_update.assert_called_once()

    @patch("apps.reportings.signals.get_obj_from_path")
    @patch("apps.reportings.signals.get_road_coordinates")
    @patch("apps.reportings.signals.bulk_update_with_history")
    def test_check_road_name_and_point_with_hidden_location(
        self, mock_bulk_update, mock_get_road_coordinates, mock_get_obj_from_path
    ):
        """Testa o comportamento quando hide_reporting_location é True"""
        mock_get_obj_from_path.return_value = True

        check_road_name_and_point(
            sender=Reporting, created=False, instance=self.reporting
        )

        self.assertIsNotNone(self.reporting.geometry)
        mock_bulk_update.assert_called_once()

    @patch("apps.reportings.signals.apply_json_logic")
    @patch("apps.reportings.signals.get")
    @patch("apps.reportings.signals.get_topics")
    def test_fill_lot_field_for_inspect_types(
        self, mock_get_topics, mock_get, mock_apply_json_logic
    ):
        """Testa se o signal fill_lot_field preenche corretamente o campo lot para tipos de inspeção"""
        mock_get.side_effect = (
            lambda path, company, default=None: ["123"]
            if path == "metadata.csp.inspect_types"
            else {}
        )
        mock_get_topics.return_value = {"5.1": ["ICRP", "ICRFD"]}
        mock_apply_json_logic.return_value = "Lot A"

        fill_lot_field(sender=Reporting, instance=self.reporting)

        self.assertEqual(self.reporting.lot, "Lot A")
        self.assertIn("lots", self.reporting.form_data)
        self.assertIn("road_system", self.reporting.form_data)

    @patch("apps.reportings.signals.apply_json_logic")
    @patch("apps.reportings.signals.get")
    def test_fill_lot_field_for_non_inspect_types(
        self, mock_get, mock_apply_json_logic
    ):
        """Testa se o signal fill_lot_field preenche apenas o campo lot para tipos que não são de inspeção"""
        mock_get.return_value = []
        mock_apply_json_logic.return_value = "Lot B"

        fill_lot_field(sender=Reporting, instance=self.reporting)

        self.assertEqual(self.reporting.lot, "Lot B")
        self.assertNotIn("lots", self.reporting.form_data)


class AddLastMonitoringFilesTestCase(TestCase):
    def setUp(self):
        self.occurrence_type = Mock()
        self.occurrence_type.occurrence_kind = "monitoring_type_1"

        self.company = Mock()
        self.company.metadata = {"inspection_occurrence_kind": ["monitoring_type_1"]}

        self.reporting = Mock(spec=Reporting)
        self.reporting.company = self.company
        self.reporting.occurrence_type = self.occurrence_type
        self.reporting.form_data = {}
        self.reporting.uuid = uuid.uuid4()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_not_created(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando a instância não foi criada"""
        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=False
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_company(self, mock_bulk_update, mock_logging):
        """Testa se o signal não executa quando não há company"""
        self.reporting.company = None

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_company_metadata(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando company não tem metadata"""
        self.company.metadata = None

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_inspection_occurrence_kind(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando não há inspection_occurrence_kind no metadata"""
        self.company.metadata = {}

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_occurrence_type_not_in_monitoring_ids(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando o occurrence_type não está nos monitoring_ids"""
        self.company.metadata = {"inspection_occurrence_kind": ["other_type"]}
        self.occurrence_type.occurrence_kind = "monitoring_type_1"

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_occurrence_type(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando não há occurrence_type"""
        self.reporting.occurrence_type = None

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_parent(self, mock_bulk_update, mock_logging):
        """Testa se o signal não executa quando não há parent"""
        self.reporting.parent = None

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_last_monitoring(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando não há último monitoramento"""

        parent = Mock()
        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = (
            None
        )
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_no_files_in_last_monitoring(
        self, mock_bulk_update, mock_logging
    ):
        """Testa se o signal não executa quando o último monitoramento não tem arquivos"""

        parent = Mock()
        last_monitoring = Mock()
        last_monitoring.form_data = {}

        files_manager = Mock()
        files_manager.all = Mock(return_value=[])
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_logging.assert_not_called()

    @patch("apps.reportings.signals.bulk_create_with_history")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_success_with_files(
        self, mock_bulk_update, mock_bulk_create
    ):
        """Testa se o signal funciona corretamente quando há arquivos para copiar"""

        parent = Mock()
        last_monitoring = Mock()
        last_monitoring.form_data = {}

        reporting_file_1 = Mock()
        original_uuid_1 = uuid.uuid4()
        reporting_file_1.uuid = original_uuid_1

        reporting_file_2 = Mock()
        original_uuid_2 = uuid.uuid4()
        reporting_file_2.uuid = original_uuid_2

        files_manager = Mock()
        files_manager.all = Mock(return_value=[reporting_file_1, reporting_file_2])
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        created_files = mock_bulk_create.call_args[0][0]
        cloned_file_1 = created_files[0]
        cloned_file_2 = created_files[1]

        self.assertNotEqual(cloned_file_1.uuid, original_uuid_1)
        self.assertNotEqual(cloned_file_2.uuid, original_uuid_2)
        self.assertEqual(cloned_file_1.reporting, self.reporting)
        self.assertEqual(cloned_file_2.reporting, self.reporting)

        expected_form_data = {
            "last_monitoring": [
                {
                    "last_monitoring_files": [
                        str(cloned_file_1.uuid),
                        str(cloned_file_2.uuid),
                    ]
                }
            ]
        }
        self.assertEqual(self.reporting.form_data, expected_form_data)

        mock_bulk_create.assert_called_once()
        mock_bulk_update.assert_called_once_with(
            [self.reporting], update_fields=["form_data"]
        )

    @patch("logging.warning")
    @patch("apps.reportings.signals.bulk_create_with_history")
    @patch("apps.reportings.signals.bulk_update")
    def test_add_last_monitoring_files_preserves_existing_form_data(
        self, mock_bulk_update, mock_bulk_create, mock_logging
    ):
        """Testa se o signal preserva form_data existente ao adicionar last_monitoring"""

        self.reporting.form_data = {"existing_field": "existing_value"}

        parent = Mock()
        last_monitoring = Mock()
        last_monitoring.form_data = {}

        reporting_file = Mock()
        original_uuid = uuid.uuid4()
        reporting_file.uuid = original_uuid

        files_manager = Mock()
        files_manager.all = Mock(return_value=[reporting_file])
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        created_files = mock_bulk_create.call_args[0][0]
        cloned_file = created_files[0]

        expected_form_data = {
            "existing_field": "existing_value",
            "last_monitoring": [{"last_monitoring_files": [str(cloned_file.uuid)]}],
        }
        self.assertEqual(self.reporting.form_data, expected_form_data)

    @patch("apps.reportings.signals.bulk_create_with_history")
    @patch("logging.warning")
    def test_add_last_monitoring_files_handles_exception(
        self, mock_logging, mock_bulk_create
    ):
        """Testa se o signal captura e imprime exceções"""

        self.company.metadata = {"inspection_occurrence_kind": ["monitoring_type_1"]}

        parent = Mock()
        last_monitoring = Mock()
        last_monitoring.form_data = {}

        reporting_file = Mock()
        reporting_file.pk = 1
        reporting_file.uuid = uuid.uuid4()
        mock_bulk_create.side_effect = Exception("Database error")

        files_manager = Mock()
        files_manager.all = Mock(return_value=[reporting_file])
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_logging.assert_called()

    @patch("apps.reportings.signals.bulk_update")
    @patch("apps.reportings.signals.bulk_create_with_history")
    def test_add_last_monitoring_files_blocked_with_mismatched_string_occurrence_kind(
        self, mock_bulk_create, mock_bulk_update
    ):
        """Testa se o signal é barrado quando inspection_occurrence_kind não coincide com occurrence_kind"""

        self.occurrence_type.occurrence_kind = "1"

        self.company.metadata = {"inspection_occurrence_kind": "501"}

        parent = Mock()
        last_monitoring = Mock()
        last_monitoring.form_data = {}

        reporting_file = Mock()
        original_uuid = uuid.uuid4()
        reporting_file.uuid = original_uuid

        files_manager = Mock()
        files_manager.all = Mock(return_value=[reporting_file])
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_update.assert_not_called()
        mock_bulk_create.assert_not_called()

        self.assertEqual(self.reporting.form_data, {})

    @patch("apps.reportings.signals.bulk_update")
    @patch("apps.reportings.signals.bulk_create_with_history")
    def test_add_last_monitoring_files_with_matching_string_inspection_occurrence_kind(
        self, mock_bulk_create, mock_bulk_update
    ):
        """Testa se o signal funciona corretamente quando inspection_occurrence_kind coincide com occurrence_kind"""

        self.occurrence_type.occurrence_kind = "501"
        self.company.metadata = {"inspectionOccurrenceKind": "501"}

        parent = Mock()
        last_monitoring = Mock()
        last_monitoring.form_data = {}

        reporting_file = Mock()
        original_uuid = uuid.uuid4()
        reporting_file.uuid = original_uuid

        files_manager = Mock()
        files_manager.all = Mock(return_value=[reporting_file])
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        created_files = mock_bulk_create.call_args[0][0]
        cloned_file = created_files[0]

        self.assertNotEqual(cloned_file.uuid, original_uuid)
        self.assertEqual(cloned_file.reporting, self.reporting)
        self.assertFalse(cloned_file.is_shared)
        self.assertTrue(cloned_file.include_dnit)

        expected_form_data = {
            "last_monitoring": [{"last_monitoring_files": [str(cloned_file.uuid)]}]
        }
        self.assertEqual(self.reporting.form_data, expected_form_data)

        mock_bulk_create.assert_called_once()
        mock_bulk_update.assert_called_once_with(
            [self.reporting], update_fields=["form_data"]
        )

    @patch("apps.reportings.signals.bulk_update")
    @patch("apps.reportings.signals.bulk_create_with_history")
    def test_add_last_monitoring_whitout_last_monitoring_files(
        self, mock_bulk_create, mock_bulk_update
    ):
        """Testa se o signal ignora arquivos que já estão em last_monitoring_files da monitoração anterior"""

        parent = Mock()
        last_monitoring = Mock()

        reporting_file_ignored = Mock()
        ignored_uuid = uuid.uuid4()
        reporting_file_ignored.uuid = ignored_uuid

        reporting_file_to_copy = Mock()
        to_copy_uuid = uuid.uuid4()
        reporting_file_to_copy.uuid = to_copy_uuid

        last_monitoring.form_data = {
            "last_monitoring": [{"last_monitoring_files": [str(ignored_uuid)]}]
        }

        files_manager = Mock()
        files_manager.all = Mock(
            return_value=[reporting_file_ignored, reporting_file_to_copy]
        )
        last_monitoring.reporting_files = files_manager

        children_manager = Mock()
        children_manager.exclude.return_value.filter.return_value.order_by.return_value.all.return_value = [
            last_monitoring
        ]
        parent.children = children_manager
        self.reporting.parent = parent

        add_last_monitoring_files(
            sender=Reporting, instance=self.reporting, created=True
        )

        mock_bulk_create.assert_called_once()
        created_files = mock_bulk_create.call_args[0][0]

        self.assertEqual(len(created_files), 1)
        cloned_file = created_files[0]

        self.assertNotEqual(cloned_file.uuid, ignored_uuid)
        self.assertNotEqual(cloned_file.uuid, to_copy_uuid)
        self.assertEqual(cloned_file.reporting, self.reporting)

        expected_form_data = {
            "last_monitoring": [{"last_monitoring_files": [str(cloned_file.uuid)]}]
        }
        self.assertEqual(self.reporting.form_data, expected_form_data)

        mock_bulk_update.assert_called_once_with(
            [self.reporting], update_fields=["form_data"]
        )
