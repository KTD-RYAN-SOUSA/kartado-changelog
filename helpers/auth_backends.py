from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.utils import ConnectionDoesNotExist

UserModel = get_user_model()


class SharedModelBackend(ModelBackend):
    api_url = settings.BACKEND_URL


class EngieModelBackend(ModelBackend):
    api_url = settings.ENGIE_BACKEND_URL

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        try:
            user = UserModel._default_manager.using("engie_prod").get(
                **{UserModel.USERNAME_FIELD: username}
            )
        except (UserModel.DoesNotExist, ConnectionDoesNotExist):
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user (#20760).
            UserModel().set_password(password)
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user


class CCRModelBackend(ModelBackend):
    api_url = settings.CCR_BACKEND_URL

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        try:
            user = UserModel._default_manager.using("ccr_prod").get(
                **{UserModel.USERNAME_FIELD: username}
            )
        except (UserModel.DoesNotExist, ConnectionDoesNotExist):
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user (#20760).
            UserModel().set_password(password)
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
