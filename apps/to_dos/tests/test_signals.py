from datetime import datetime

import pytest

from helpers.testing.fixtures import TestBase

from ..models import ToDo, ToDoAction

pytestmark = pytest.mark.django_db


class TestToDoIfActionSeeSignal(TestBase):
    model = "ToDo"

    def test_set_read_at_marks_is_done_true(self):
        """
        Garante que definir read_at em um ToDo com action 'see'
        marca is_done como True automaticamente via signal.
        """
        instance = ToDo.objects.filter(
            company=self.company,
            read_at=None,
            is_done=False,
            action__default_options="see",
        ).first()

        instance.read_at = datetime.now()
        instance.save()

        instance.refresh_from_db()

        assert instance.is_done is True

    def test_clear_read_at_marks_is_done_false(self):
        """
        Garante que limpar read_at em um ToDo com action 'see'
        marca is_done como False automaticamente via signal.
        """
        instance = ToDo.objects.filter(
            company=self.company,
            read_at__isnull=False,
            action__default_options="see",
        ).first()

        # Configura is_done=True diretamente no banco sem disparar o signal,
        # para montar o estado inicial correto do teste.
        ToDo.objects.filter(pk=instance.pk).update(is_done=True)

        instance.refresh_from_db()
        instance.read_at = None
        instance.save()

        instance.refresh_from_db()

        assert instance.is_done is False

    def test_set_is_done_sets_read_at(self):
        """
        Garante que marcar is_done=True em um ToDo com action 'see'
        e read_at=None preenche read_at automaticamente via signal.
        """
        instance = ToDo.objects.filter(
            company=self.company,
            read_at=None,
            is_done=False,
            action__default_options="see",
        ).first()

        instance.is_done = True
        instance.save()

        instance.refresh_from_db()

        assert instance.read_at is not None

    def test_clear_is_done_clears_read_at(self):
        """
        Garante que marcar is_done=False em um ToDo com action 'see'
        e is_done=True limpa read_at automaticamente via signal.
        """
        instance = ToDo.objects.filter(
            company=self.company,
            read_at__isnull=False,
            action__default_options="see",
        ).first()

        # Configura is_done=True diretamente no banco sem disparar o signal,
        # para montar o estado inicial correto do teste.
        ToDo.objects.filter(pk=instance.pk).update(is_done=True)

        instance.refresh_from_db()
        instance.is_done = False
        instance.save()

        instance.refresh_from_db()

        assert instance.read_at is None

    def test_no_change_when_action_is_not_see(self):
        """
        Garante que o signal não altera is_done quando a action do ToDo
        não possui default_options='see'.
        """
        action = ToDoAction.objects.filter(default_options__isnull=True).first()

        instance = ToDo.objects.create(
            company=self.company,
            created_by=self.user,
            action=action,
            read_at=None,
            is_done=False,
        )

        instance.read_at = datetime.now()
        instance.save()

        instance.refresh_from_db()

        assert instance.is_done is False

    def test_no_change_on_new_instance(self):
        """
        Garante que o signal não altera is_done nem read_at durante a criação
        de um novo ToDo, pois o pre_save é disparado antes do INSERT e
        filter(pk=...) retorna None.
        """
        action = ToDoAction.objects.filter(default_options="see").first()

        instance = ToDo.objects.create(
            company=self.company,
            created_by=self.user,
            action=action,
            read_at=None,
            is_done=False,
        )

        assert instance.is_done is False
        assert instance.read_at is None
