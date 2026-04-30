import locale
import logging
from datetime import datetime, timedelta
from typing import Dict
from uuid import UUID

from django.conf import settings
from django.db.models import F
from django.dispatch.dispatcher import receiver
from django.utils.timezone import now
from django_rest_passwordreset.signals import reset_password_token_created

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceRecord
from apps.users.const.notification_types import PUSH_NOTIFICATION
from apps.users.models import UserNotification
from apps.users.views import ResetPasswordRequestTokenCustom
from helpers.notifications import (
    create_password_notifications,
    create_single_notification,
    get_disclaimer,
)
from helpers.strings import get_obj_from_path


@receiver(reset_password_token_created, sender=ResetPasswordRequestTokenCustom)
def password_reset_token_created(
    sender, instance, reset_password_token, *args, **kwargs
):
    """
    Handles password reset tokens
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param args:
    :param kwargs:
    :return:
    """
    expires = now() + timedelta(days=1)
    context = {
        "title": "Kartado - Redefinição de senha",
        "current_user": reset_password_token.user,
        "username": reset_password_token.user.username,
        "email": reset_password_token.user.email,
        "reset_password_url": "{}/#/ResetPassword/?token={}&expires_at={}".format(
            settings.FRONTEND_URL,
            reset_password_token.key,
            expires.strftime("%Y-%m-%dT%H:%M:%S"),
        ),
    }

    template_path = "users/email/password_reset_email"

    create_password_notifications(reset_password_token.user, context, template_path)


def send_email_password(data, user):
    # Create url
    url = "{}/#/login".format(settings.FRONTEND_URL)

    context = {
        "title": "Kartado - Primeiro acesso à plataforma",
        "username": data["username"],
        "email": data["email"],
        "password": data["password"],
        "url": url,
    }

    template_path = "users/email/password_email"

    create_password_notifications(
        user,
        context,
        template_path,
        add_disclaimer=True,
        company_group=user.company_group,
    )


def handle_email_boletim(
    NOTIFICATION_AREA: str,
    start_date: datetime,
    end_date: datetime,
    title_text: str,
    header_text: str,
    sub_message: str,
):
    """
    Helper with common logic to send reports regarding readings and their conditions.

    Args:
        NOTIFICATION_AREA (str): Which report is being sent (UserNotification.notification)
        start_date (datetime): Start of the range for analysis
        end_date (datetime): End of the range for analysis
        title_text (str): Title of the notification
        header_text (str): Header of the notification
        sub_message (str): Subtitle of the notification
    """

    TEMPLATE_PATH = "users/email/boletim"

    user_notifs = UserNotification.objects.filter(notification=NOTIFICATION_AREA)

    # Get only Company instances that are related to a UserNotification to avoid
    # unnecessary work and queries.
    companies = Company.objects.filter(
        user_notifications__notification=NOTIFICATION_AREA
    )

    if companies:
        company_id_to_counts: Dict[UUID, dict] = {}

        for company in companies:
            validated_in_deadline = OccurrenceRecord.objects.filter(
                company=company,
                datetime__range=(start_date, end_date),
                validated_at__lte=F("validation_deadline"),
            ).count()
            validated_off_deadline = OccurrenceRecord.objects.filter(
                company=company,
                datetime__range=(start_date, end_date),
                validated_at__gte=F("validation_deadline"),
            ).count()
            waiting_validation = OccurrenceRecord.objects.filter(
                company=company,
                validated_at__isnull=True,
                validation_deadline__isnull=False,
            ).count()
            late_validation = OccurrenceRecord.objects.filter(
                company=company,
                validated_at__isnull=True,
                validation_deadline__lte=datetime.now(),
            ).count()
            normal = OccurrenceRecord.objects.filter(
                company=company, form_data__condition="Normal"
            ).count()
            attention = OccurrenceRecord.objects.filter(
                company=company, form_data__condition="Atenção"
            ).count()
            alert = OccurrenceRecord.objects.filter(
                company=company, form_data__condition="Alerta"
            ).count()
            emergency = OccurrenceRecord.objects.filter(
                company=company,
                form_data__condition="Emergência",
            ).count()

            company_url = (
                settings.FRONTEND_URL
                + "/#/SharedLink/Dashboard?company={}".format(str(company.pk))
            )

            # Get first match of all condition colors (defaults to None if not found)
            color_list = get_obj_from_path(
                company.custom_options,
                "company__fields__condition__selectoptions__options",
            )
            normal_color = next(
                filter(lambda obj: obj["name"] == "Normal", color_list), {"color": None}
            )["color"]
            alert_color = next(
                filter(lambda obj: obj["name"] == "Alerta", color_list), {"color": None}
            )["color"]
            attention_color = next(
                filter(lambda obj: obj["name"] == "Atenção", color_list),
                {"color": None},
            )["color"]
            emergency_color = next(
                filter(lambda obj: obj["name"] == "Emergência", color_list),
                {"color": None},
            )["color"]

            company_id: UUID = company.pk
            company_id_to_counts[company_id] = {
                "company": company,
                "company_url": company_url,
                "validated_in_deadline": validated_in_deadline,
                "validated_off_deadline": validated_off_deadline,
                "waiting_validation": waiting_validation,
                "late_validation": late_validation,
                "normal": normal,
                "normal_color": normal_color,
                "attention": attention,
                "attention_color": attention_color,
                "alert": alert,
                "alert_color": alert_color,
                "emergency": emergency,
                "emergency_color": emergency_color,
                "disclaimer": get_disclaimer(company.company_group),
            }

        for user_notif in user_notifs:
            # Company to represent grouped values
            rep_company = user_notif.companies.first()
            rep_item = company_id_to_counts[rep_company.pk]

            # Get items for all the UserNotification Company instances
            notif_companies_ids = list(
                set(user_notif.companies.values_list("uuid", flat=True))
            )
            companies_counts = [
                company_id_to_counts[company_id]
                for company_id in notif_companies_ids
                if company_id in company_id_to_counts
            ]

            context = {
                # Essentials
                "title": title_text,
                "header": header_text,
                "sub_message": sub_message,
                # Common data of rep Company
                "disclaimer": rep_item["disclaimer"],
                "normal_color": rep_item["normal_color"],
                "alert_color": rep_item["alert_color"],
                "attention_color": rep_item["attention_color"],
                "emergency_color": rep_item["emergency_color"],
                # Grouped Company data
                "data": companies_counts,
            }

            # For each count_int_field get the sum of the counts of that field and add the
            # total to the context and accessible by total_<field_name>.
            count_int_fields = [
                "validated_in_deadline",
                "validated_off_deadline",
                "waiting_validation",
                "late_validation",
                "normal",
                "attention",
                "alert",
                "emergency",
            ]
            context.update(
                {
                    f"total_{int_field}": sum(
                        counts[int_field] for counts in companies_counts
                    )
                    for int_field in count_int_fields
                }
            )

            create_single_notification(
                company=rep_company,
                context=context,
                user=user_notif.user,
                template_path=TEMPLATE_PATH,
                push=user_notif.notification_type == PUSH_NOTIFICATION,
            )
    else:
        logging.info(
            "handle_email_boletim: No UserNotification configured to receive the report"
        )


def handle_email_boletim_mensal():
    NOTIFICATION_AREA = "auscultacao.boletim_mensal"
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")

    head_templ = "Segue boletim mensal de leituras de segurança de barragens de {}"
    title_templ = "Segurança de barragens - Boletim mensal de {}"
    sub_message = "do mês"

    today = datetime.now()

    month, year = (
        (today.month - 1, today.year) if today.month != 1 else (12, today.year - 1)
    )

    pre_month = today.replace(day=1, month=month, year=year)

    title_template = title_templ.format(pre_month.strftime("%B de %Y").capitalize())
    header_template = head_templ.format(pre_month.strftime("%B de %Y").capitalize())

    handle_email_boletim(
        NOTIFICATION_AREA,
        pre_month,
        today,
        title_template,
        header_template,
        sub_message,
    )


def handle_email_boletim_semanal():
    NOTIFICATION_AREA = "auscultacao.boletim_semanal"
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")

    head_templ = (
        "Segue boletim semanal de leituras de segurança de barragens da {} de {}"
    )
    title_templ = "Segurança de barragens - Boletim semanal da {} de {}"
    sub_message = "da semana"
    week = ""

    today = datetime.now()
    week_before = today - timedelta(weeks=1)

    if today.day >= 1 and today.day < 7:
        week = "1º semana"
    elif today.day >= 7 and today.day < 14:
        week = "2º semana"
    elif today.day >= 14 and today.day < 21:
        week = "3º semana"
    elif today.day >= 21 and today.day < 28:
        week = "4º semana"
    else:
        week = "5º semana"

    title_template = title_templ.format(week, today.strftime("%B de %Y").capitalize())
    header_template = head_templ.format(week, today.strftime("%B de %Y").capitalize())

    handle_email_boletim(
        NOTIFICATION_AREA,
        week_before,
        today,
        title_template,
        header_template,
        sub_message,
    )


def handle_email_boletim_diario():
    NOTIFICATION_AREA = "auscultacao.boletim_diario"
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")

    head_templ = (
        "Segue boletim diário de leituras de segurança de barragens de {} de {}"
    )
    title_templ = "Segurança de barragens - Boletim diário de {} de {}"
    sub_message = "do dia"

    today = datetime.now()
    day_before = today - timedelta(days=1)

    title_template = title_templ.format(
        today.day, today.strftime("%B de %Y").capitalize()
    )
    header_template = head_templ.format(
        today.day, today.strftime("%B de %Y").capitalize()
    )

    handle_email_boletim(
        NOTIFICATION_AREA,
        day_before,
        today,
        title_template,
        header_template,
        sub_message,
    )
