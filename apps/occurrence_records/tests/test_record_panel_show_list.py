import pytest

from apps.occurrence_records.models import RecordPanel, RecordPanelShowList
from apps.users.models import User
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestRecordPanelShowList(TestBase):
    model = "RecordPanelShowList"

    def test_record_panel_show_list_history(self, client):
        """Ensure the RecordPanelShowList history is properly being filled"""

        user = User.objects.first()
        record_panel = RecordPanel.objects.first()
        rpsl = RecordPanelShowList.objects.create(
            user=user, panel=record_panel, order=71
        )

        # Ensure the + history was created
        hist = rpsl.history.first()
        assert hist.history_type == "+"

        # Ensure the ~ history was created
        rpsl.order = 17
        rpsl.save()
        hist = rpsl.history.first()
        assert hist.history_type == "~"
