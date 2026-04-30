from zappa.asynchronous import task

from .const.frequency_types import DAILY_MIDNIGHT, DAILY_NOON, HOURLY
from .helpers.historiador import EngieHistoriadorIntegration
from .helpers.maximo import EngieMaximoIntegration
from .models import IntegrationConfig


@task
def run_historiador_integration(integration_id):
    integration = IntegrationConfig.objects.get(uuid=integration_id)
    integration_class = EngieHistoriadorIntegration(integration)
    integration_class.run()


@task
def run_maximo_integration(integration_id):
    integration = IntegrationConfig.objects.get(uuid=integration_id)
    integration_class = EngieMaximoIntegration(integration)
    integration_class.run()


def run_integrations_daily_midnight():
    """
    This function is called every day at midnight by AWS
    """
    historiador_integrations = IntegrationConfig.objects.filter(
        integration_type="ENGIE_HISTORIADOR", frequency_type=DAILY_MIDNIGHT
    )
    for integration in historiador_integrations:
        run_historiador_integration(str(integration.uuid))

    maximo_integrations = IntegrationConfig.objects.filter(
        integration_type="ENGIE_MAXIMO", frequency_type=DAILY_MIDNIGHT
    )
    for integration in maximo_integrations:
        run_maximo_integration(str(integration.uuid))


def run_integrations_daily_noon():
    """
    This function is called every day at noon by AWS
    """
    historiador_integrations = IntegrationConfig.objects.filter(
        integration_type="ENGIE_HISTORIADOR", frequency_type=DAILY_NOON
    )
    for integration in historiador_integrations:
        run_historiador_integration(str(integration.uuid))

    maximo_integrations = IntegrationConfig.objects.filter(
        integration_type="ENGIE_MAXIMO", frequency_type=DAILY_NOON
    )
    for integration in maximo_integrations:
        run_maximo_integration(str(integration.uuid))


def run_integrations_hourly():
    """
    This function is called every hour by AWS
    """
    historiador_integrations = IntegrationConfig.objects.filter(
        integration_type="ENGIE_HISTORIADOR", frequency_type=HOURLY
    )
    for integration in historiador_integrations:
        integration_class = EngieHistoriadorIntegration(integration)
        integration_class.run()
