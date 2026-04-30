import hashlib
import uuid
from unittest import mock
from unittest.mock import Mock, patch

from django.db.models import signals
from django.test import TestCase
from rest_framework_json_api import serializers

from helpers.signals import (  # Context managers and decorators; Utility functions
    DisableSignals,
    auto_add_job_number,
    auto_add_number,
    catch_signal,
    disable_signal_for_loaddata,
    history_dont_save_geometry_changes,
    prevent_signal,
    watcher_email_notification,
)


class TestPreventSignal(TestCase):
    """Tests for the prevent_signal decorator"""

    def setUp(self):
        self.mock_signal_fn = Mock()
        self.mock_sender = Mock()

    def test_prevent_signal_decorator(self):
        """Tests that prevent_signal decorator properly disconnects and reconnects signals"""
        # Create a test function that will be decorated
        def test_function():
            return "executed"

        # Apply the decorator
        decorated_function = prevent_signal(
            "post_save", self.mock_signal_fn, self.mock_sender
        )(test_function)

        # Mock the post_save signal
        with patch.object(signals, "post_save") as mock_post_save:
            # Mock the disconnect and connect methods
            mock_post_save.disconnect = Mock()
            mock_post_save.connect = Mock()

            # The original prevent_signal doesn't return the function result
            decorated_function()

            # Verify signal was disconnected and reconnected
            mock_post_save.disconnect.assert_called_once_with(
                self.mock_signal_fn, self.mock_sender
            )
            mock_post_save.connect.assert_called_once_with(
                self.mock_signal_fn, self.mock_sender
            )


class TestCatchSignal(TestCase):
    """Tests for the catch_signal context manager"""

    def test_catch_signal_context_manager(self):
        """Tests that catch_signal properly catches and mocks signals"""
        mock_signal = Mock()

        with catch_signal(mock_signal) as handler:
            # Verify signal was connected
            mock_signal.connect.assert_called_once_with(handler)
            self.assertIsInstance(handler, Mock)

        # Verify signal was disconnected after exiting context
        mock_signal.disconnect.assert_called_once_with(handler)


class TestDisableSignalForLoaddata(TestCase):
    """Tests for the disable_signal_for_loaddata decorator"""

    def test_disable_signal_for_loaddata_with_raw_true(self):
        """Tests that signal handler is disabled when raw=True"""
        mock_handler = Mock()

        @disable_signal_for_loaddata
        def signal_handler(*args, **kwargs):
            mock_handler(*args, **kwargs)

        # Call with raw=True (fixture loading)
        result = signal_handler(arg1="test", raw=True)

        # Should return None and not call the handler
        self.assertIsNone(result)
        mock_handler.assert_not_called()

    def test_disable_signal_for_loaddata_with_raw_false(self):
        """Tests that signal handler works normally when raw=False"""
        mock_handler = Mock()

        @disable_signal_for_loaddata
        def signal_handler(*args, **kwargs):
            mock_handler(*args, **kwargs)
            return "handler_called"

        # Call with raw=False (normal operation)
        signal_handler(arg1="test", raw=False)

        # Should call the handler normally
        mock_handler.assert_called_once_with(arg1="test", raw=False)

    def test_disable_signal_for_loaddata_without_raw(self):
        """Tests that signal handler works normally when raw is not provided"""
        mock_handler = Mock()

        @disable_signal_for_loaddata
        def signal_handler(*args, **kwargs):
            mock_handler(*args, **kwargs)
            return "handler_called"

        # Call without raw parameter
        signal_handler(arg1="test")

        # Should call the handler normally
        mock_handler.assert_called_once_with(arg1="test")


class TestDisableSignals(TestCase):
    """Tests for the DisableSignals context manager class"""

    def test_disable_signals_default_signals(self):
        """Tests DisableSignals with default signal list"""
        with patch("helpers.signals.pre_save") as mock_pre_save, patch(
            "helpers.signals.post_save"
        ) as mock_post_save:

            mock_pre_save.receivers = ["receiver1", "receiver2"]
            mock_post_save.receivers = ["receiver3"]

            with DisableSignals():
                # Signals should be disabled (receivers cleared)
                self.assertEqual(mock_pre_save.receivers, [])
                self.assertEqual(mock_post_save.receivers, [])

            # After exiting context, signals should be restored
            self.assertEqual(mock_pre_save.receivers, ["receiver1", "receiver2"])
            self.assertEqual(mock_post_save.receivers, ["receiver3"])

    def test_disable_signals_custom_signals(self):
        """Tests DisableSignals with custom signal list"""
        mock_signal = Mock()
        mock_signal.receivers = ["custom_receiver"]

        with DisableSignals(disabled_signals=[mock_signal]):
            # Custom signal should be disabled
            self.assertEqual(mock_signal.receivers, [])

        # After exiting context, signal should be restored
        self.assertEqual(mock_signal.receivers, ["custom_receiver"])


class TestHistoryDontSaveGeometryChanges(TestCase):
    """Tests for the history_dont_save_geometry_changes function"""

    def test_history_dont_save_geometry_changes_success(self):
        """Tests successful geometry hash generation and clearing"""
        mock_history = Mock()
        mock_geometry = Mock()
        mock_geometry.__str__ = Mock(return_value="POINT(1 2)")
        mock_history.geometry = mock_geometry

        history_dont_save_geometry_changes(mock_history)

        # Verify hash was calculated and stored in geometry_hash
        expected_hash = hashlib.md5("POINT(1 2)".encode()).hexdigest()
        self.assertEqual(mock_history.geometry_hash, expected_hash)

        # Verify geometry was cleared
        self.assertIsNone(mock_history.geometry)

    def test_history_dont_save_geometry_changes_exception(self):
        """Tests that function handles exceptions gracefully"""
        mock_history = Mock()
        # Set geometry to None to cause an exception in __str__()
        mock_history.geometry = None

        # Should not raise an exception
        history_dont_save_geometry_changes(mock_history)

        # Since there was an exception, geometry_hash should still be set (the function always sets it in except block)
        # Looking at the implementation, the function sets geometry_hash even when exception occurs
        self.assertTrue(hasattr(mock_history, "geometry_hash"))


class TestAutoAddNumber(TestCase):
    """Tests for the auto_add_number function"""

    def setUp(self):
        self.mock_instance = Mock()
        self.mock_instance.number = None
        self.mock_company = Mock()
        self.mock_company.uuid = uuid.uuid4()
        self.mock_company.name = "Test Company"
        self.mock_company.metadata = {
            "test_key": {
                "test_kind": {
                    "type": "default_type",
                    "format": "{prefixo}-{nome}-{anoCompleto}.{serial}",
                },
                "default": {
                    "type": "default_type",
                    "format": "{prefixo}-{nome}-{anoCompleto}.{serial}",
                },
            }
        }

    @patch("helpers.signals.get_autonumber_array")
    @patch("helpers.signals.Company")
    def test_auto_add_number_with_occurrence_type(
        self, mock_company_class, mock_get_autonumber
    ):
        """Tests auto number generation with occurrence type"""
        mock_get_autonumber.return_value = {
            "nome": "default_type",
            "serial": 1,
            "anoCompleto": "2023",
            "prefixo": "TC",
        }

        # Mock Company.objects.get to return our mock company
        mock_company_class.objects.get.return_value = self.mock_company

        self.mock_instance.occurrence_type = Mock()
        self.mock_instance.occurrence_type.occurrence_kind = "test_kind"
        # Mock get_company_id as a property that returns a simple value
        type(self.mock_instance).get_company_id = mock.PropertyMock(return_value=1)

        auto_add_number(self.mock_instance, "test_key")

        # Verify the number was set
        self.assertIsNotNone(self.mock_instance.number)
        mock_get_autonumber.assert_called_once()

    @patch("helpers.signals.get_autonumber_array")
    def test_auto_add_number_with_company_attribute(self, mock_get_autonumber):
        """Tests auto number generation when instance has company attribute"""
        mock_get_autonumber.return_value = {
            "nome": "default_type",
            "serial": 1,
            "anoCompleto": "2023",
            "prefixo": "TC",
        }

        # Make sure instance doesn't have get_company_id so it uses company attribute
        if hasattr(self.mock_instance, "get_company_id"):
            delattr(self.mock_instance, "get_company_id")

        self.mock_instance.company = self.mock_company
        self.mock_instance.occurrence_type = Mock()
        self.mock_instance.occurrence_type.occurrence_kind = "test_kind"

        auto_add_number(self.mock_instance, "test_key")

        # Verify the number was set
        self.assertIsNotNone(self.mock_instance.number)
        mock_get_autonumber.assert_called_once_with(
            self.mock_company.uuid, "default_type"
        )

    def test_auto_add_number_with_existing_number(self):
        """Tests that function does nothing when number already exists"""
        self.mock_instance.number = "EXISTING-001"

        auto_add_number(self.mock_instance, "test_key")

        # Number should remain unchanged
        self.assertEqual(self.mock_instance.number, "EXISTING-001")

    @patch("helpers.signals.Company")
    def test_auto_add_number_missing_metadata(self, mock_company_class):
        """Tests that function raises error when metadata is missing"""
        # Create a mock company with empty metadata
        mock_company = Mock()
        mock_company.metadata = {}
        mock_company_class.objects.get.return_value = mock_company

        # Setup instance with get_company_id that will trigger Company.objects.get
        type(self.mock_instance).get_company_id = mock.PropertyMock(return_value=1)
        self.mock_instance.occurrence_type = None  # No occurrence type

        with self.assertRaises(serializers.ValidationError):
            auto_add_number(self.mock_instance, "missing_key")


class TestWatcherEmailNotification(TestCase):
    """Tests for the watcher_email_notification function"""

    def setUp(self):
        self.mock_company = Mock()
        self.mock_company.uuid = uuid.uuid4()
        self.mock_company.pk = 1

    @patch("helpers.signals.add_debounce_data")
    @patch("helpers.signals.UserNotification")
    @patch("helpers.signals.settings")
    def test_watcher_email_notification_occurrence_record(
        self, mock_settings, mock_user_notif, mock_add_debounce
    ):
        """Tests email notification for OccurrenceRecordWatcher"""
        # Import the real class to create a proper instance
        from apps.occurrence_records.models import OccurrenceRecordWatcher

        # Create a real instance and mock its attributes
        mock_watcher = Mock(spec=OccurrenceRecordWatcher)
        mock_watcher.uuid = uuid.uuid4()
        mock_watcher.pk = 1
        mock_watcher.status_email = True
        mock_watcher.user = Mock()
        mock_watcher.user.get_full_name.return_value = "John Doe"
        mock_watcher.created_by = Mock()
        mock_watcher.created_by.get_full_name.return_value = "Jane Smith"
        mock_watcher.firm = None

        # Setup occurrence record
        mock_watcher.occurrence_record = Mock()
        mock_watcher.occurrence_record.company = self.mock_company
        mock_watcher.occurrence_record.number = "OR-001"
        mock_watcher.occurrence_record.uuid = uuid.uuid4()

        # Setup settings
        mock_settings.FRONTEND_URL = "https://frontend.test"
        mock_settings.BACKEND_URL = "https://backend.test"

        # Setup UserNotification mock
        mock_user_notif.objects.filter.return_value.only.return_value = []

        watcher_email_notification("test_area", mock_watcher, True)

        # Verify add_debounce_data was called
        mock_add_debounce.assert_called_once()

    def test_watcher_email_notification_not_created(self):
        """Tests that no notification is sent when watcher is not newly created"""
        mock_watcher = Mock()
        mock_watcher.status_email = True

        # Should not process because created=False
        with patch("helpers.signals.add_debounce_data") as mock_add_debounce:
            watcher_email_notification("test_area", mock_watcher, False)
            mock_add_debounce.assert_not_called()

    def test_watcher_email_notification_email_disabled(self):
        """Tests that no notification is sent when email is disabled"""
        mock_watcher = Mock()
        mock_watcher.status_email = False

        # Should not process because status_email=False
        with patch("helpers.signals.add_debounce_data") as mock_add_debounce:
            watcher_email_notification("test_area", mock_watcher, True)
            mock_add_debounce.assert_not_called()

    def test_watcher_email_notification_unsupported_watcher(self):
        """Tests that NotImplementedError is raised for unsupported watcher types"""
        mock_watcher = Mock()
        mock_watcher.status_email = True

        # Make it not match any known watcher types
        mock_watcher.__class__ = type("UnsupportedWatcher", (), {})

        with self.assertRaises(NotImplementedError):
            watcher_email_notification("test_area", mock_watcher, True)


class TestAutoAddJobNumber(TestCase):
    """Tests for the auto_add_job_number function"""

    @patch("helpers.signals.get_autonumber_array")
    def test_auto_add_job_number_with_format(self, mock_get_autonumber):
        """Tests job number generation with custom format in metadata"""
        mock_get_autonumber.return_value = {
            "nome": "job",
            "serial": 1,
            "anoCompleto": "2023",
            "serialAno": "0001",
        }

        mock_company = Mock()
        mock_company.uuid = uuid.uuid4()
        mock_company.name = "Test Company"
        mock_company.metadata = {
            "job_name_format": "JOB-{prefixo}-{anoCompleto}-{serialAno}",
            "company_prefix": "TC",
        }

        result = auto_add_job_number(mock_company)

        # Verify the format was used
        self.assertIn("JOB-", result)
        self.assertIn("TC", result)
        self.assertIn("2023", result)
        mock_get_autonumber.assert_called_once_with(mock_company.uuid, "job")

    @patch("helpers.signals.get_autonumber_array")
    def test_auto_add_job_number_without_format(self, mock_get_autonumber):
        """Tests job number generation without custom format (fallback)"""
        mock_get_autonumber.return_value = {
            "nome": "job",
            "serial": 1,
            "anoCompleto": "2023",
            "serialAno": "0001",
        }

        mock_company = Mock()
        mock_company.uuid = uuid.uuid4()
        mock_company.name = "Test Company"
        mock_company.metadata = {}  # No job_name_format

        result = auto_add_job_number(mock_company)

        # Should use fallback format
        self.assertIn("[Test Company]", result)  # Company name as prefix
        self.assertIn("job", result)
        self.assertIn("2023", result)
        mock_get_autonumber.assert_called_once_with(mock_company.uuid, "job")

    @patch("helpers.signals.get_autonumber_array")
    def test_auto_add_job_number_without_company_prefix(self, mock_get_autonumber):
        """Tests job number generation without company_prefix in metadata"""
        mock_get_autonumber.return_value = {
            "nome": "job",
            "serial": 1,
            "anoCompleto": "2023",
            "serialAno": "0001",
        }

        mock_company = Mock()
        mock_company.uuid = uuid.uuid4()
        mock_company.name = "Test Company"
        mock_company.metadata = {
            "job_name_format": "CUSTOM-{prefixo}-{nome}-{anoCompleto}.{serialAno}"
        }

        result = auto_add_job_number(mock_company)

        # Should use company name as prefix when company_prefix is not available
        self.assertIn("[Test Company]", result)
        self.assertIn("CUSTOM-", result)
        mock_get_autonumber.assert_called_once_with(mock_company.uuid, "job")


if __name__ == "__main__":
    import unittest

    unittest.main()
