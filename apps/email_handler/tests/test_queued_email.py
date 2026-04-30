import pytest

from apps.email_handler.asynchronous import send_queued_emails
from apps.email_handler.models import QueuedEmail
from apps.users.models import User
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestQueuedEmail(TestBase):
    model = "QueuedEmail"

    def test_create_email(self, client):

        email = QueuedEmail.objects.create(
            title="test", content_plain_text="test", content_html="text"
        )

        for user in self.company.users.all():
            email.send_to_users.add(user)

        email.cleared = True
        email.save()

        # __str__ method
        assert email.__str__()

    def test_send_function(self, mailoutbox):

        queue = QueuedEmail.objects.filter(sent=False, cleared=True).order_by(
            "created_at"
        )[:5]
        for email in queue:
            for user in email.send_to_users.all():
                if user:
                    user.configuration = {"send_email_notifications": True}
                    user.save()

        send_queued_emails()

        if len(QueuedEmail.objects.all()) < 5:
            assert len(mailoutbox) == len(QueuedEmail.objects.all())
        else:
            assert len(mailoutbox) == 5

    def test_send_function_without_conf(self, mailoutbox):

        user_without_conf = [
            User.objects.create(
                username="test",
                email="test@test.com",
                configuration={"send_email_notifications": False},
            )
        ]

        email = (
            QueuedEmail.objects.filter(sent=False, cleared=True)
            .order_by("created_at")
            .first()
        )
        email.title = "test"
        email.content_plain_text = "test"
        email.content_html = "text"
        email.save()

        for user in user_without_conf:
            email.send_to_users.add(user)
            email.save()

        with pytest.raises(Exception) as e:
            send_queued_emails()
            assert str(e.value) == "Email não enviado."
