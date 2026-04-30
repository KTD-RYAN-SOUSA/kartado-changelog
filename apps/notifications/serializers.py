from rest_framework_json_api import serializers

from apps.notifications.models import PushNotification, UserPush
from helpers.mixins import EagerLoadingMixin


class PushNotificationSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "push_message__user",
        "company",
    ]

    read = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PushNotification
        fields = [
            "id",
            "cleared",
            "sent",
            "created_at",
            "updated_at",
            "sound",
            "message",
            "context",
            "extra_payload",
            "read",
            "company",
            "body",
        ]
        read_only_fields = [
            "cleared",
            "sent",
            "created_at",
            "updated_at",
            "sound",
            "message",
            "context",
            "extra_payload",
            "body",
        ]

    def get_read(self, obj):
        try:
            # do it this way to avoid query explosion. calling first() or get()
            # will make a new query for each object
            read = next(
                a
                for a in list(obj.push_message.all())
                if a.user == self.context["request"].user
            ).read
        except (Exception, StopIteration):
            read = False

        return read

    def update(self, instance, validated_data):
        if "read" in self.initial_data:
            read = self.initial_data["read"]

            try:
                user_push = UserPush.objects.get(
                    user=self.context["request"].user, push_message=instance
                )
            except Exception:
                raise serializers.ValidationError(
                    "Não existe Usuário associado a essa Notificação"
                )

            user_push.read = read
            user_push.save()

        return super(PushNotificationSerializer, self).update(instance, validated_data)
