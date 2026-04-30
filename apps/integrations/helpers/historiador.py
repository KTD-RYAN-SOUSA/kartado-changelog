from datetime import datetime, timedelta

import requests
from django.db.models.signals import post_save

from apps.occurrence_records.models import OccurrenceRecord
from apps.occurrence_records.signals import notify_new_reading
from helpers.strings import to_snake_case

from ..const.frequency_types import DAILY_MIDNIGHT, DAILY_NOON, HOURLY
from ..models import IntegrationRun

error_codes = {
    "500": "Instrumento sem comunicação",
    "65535": "Instrumento sem comunicação",
    "200": "Instrumento sem leitura devido alguma inconsistência no processo de leitura",
    "327670": "Não execução/tentativa de leitura",
}


class EngieHistoriadorIntegration:
    """
    Integration class for fetching and processing data from Engie's Historiador service.

    This class handles the integration with Engie's Historiador API, fetching instrument readings
    and creating corresponding OccurrenceRecords

    Attributes:
        integration (IntegrationConfig): Configuration for the integration
        log (dict): Dictionary containing request and report logs
        integration_run (IntegrationRun): Instance tracking the current integration execution


    Integration Flow:
        1. Initializes with an IntegrationConfig
        2. Determines date range based on frequency type (HOURLY, DAILY_NOON, DAILY_MIDNIGHT)
        3. Calls Historiador API with configured parameters
        4. Processes each instrument's readings
        5. Creates OccurrenceRecords for new readings
        6. Logs progress and errors throughout execution

    API Requirements:
        - Authorization header with Basic auth
        - URL parameters:
            - dataInicio: Start date (DD/MM/YYYY)
            - dataFim: End date (DD/MM/YYYY)
            - intervalo: Reading interval (e.g., "1h")
            - path: Historiador path from configuration

    Error Handling:
        - Logs API errors
        - Handles missing or invalid data
        - Skips existing readings
        - Reports configuration issues
        - Tracks integration success/failure

    Notes:
        - Disables notification signals during reading creation
        - Supports field mapping from API to OccurrenceRecord
        - Handles instrument code prefixes
        - Copies configured fields from instrument to reading
        - Supports error code translation
    """

    def __init__(self, integration):
        self.integration = integration

        self.log = {"request": {}, "report": []}

        self.integration_run = IntegrationRun(
            integration_config=self.integration,
            started_at=datetime.now(),
            finished_at=None,
            log=self.log,
        )
        self.integration_run.save()

    def add_report(self, report):
        self.log["report"].append(report)

    def finish_up(self, error=False):
        self.integration_run.finished_at = datetime.now()
        self.integration_run.log = self.log
        self.error = error
        self.integration_run.save()

        self.integration.last_run_at = datetime.now()
        self.integration.save()

    def run(self):
        if self.integration.frequency_type == HOURLY:
            data_inicio = datetime.now().date()
        if (
            self.integration.frequency_type == DAILY_NOON
            or self.integration.frequency_type == DAILY_MIDNIGHT
        ):
            data_inicio = datetime.now().date() - timedelta(days=1)

        data_fim = data_inicio + timedelta(days=1)
        intervalo = "1h"
        path = self.integration.historiador_path

        url = "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/historiador/buscaElementoInterpoladoHist?sistema=KARTADO&dataInicio={data_inicio}&dataFim={data_fim}&intervalo={intervalo}&path={path}".format(
            data_inicio=data_inicio.strftime("%d/%m/%Y"),
            data_fim=data_fim.strftime("%d/%m/%Y"),
            intervalo=intervalo,
            path=path,
        )

        headers = {
            "Authorization": "Basic aGlzdG9yaWFkb3I6bUdtRlNHOUY5cExsdGNIZWRvQzE="
        }

        self.add_report("Iniciando chamada para {}".format(url))

        request = requests.request("GET", url, headers=headers)
        response = request.json()

        self.add_report(
            "Resposta recebida. Status code: {}".format(request.status_code)
        )

        self.log["response"] = {
            "status_code": request.status_code,
            "body": response,
            "headers": dict(request.headers),
        }

        if "Items" not in response:
            self.add_report("A resposta da integração não contém a chave 'Items'")
            self.finish_up(error=True)
            return

        instrument_form = self.integration.instrument_occurrence_type
        if not instrument_form:
            self.add_report(
                "Configurações incorretas. O formulário do instrumento não existe."
            )
            self.finish_up(error=True)
            return

        reading_form = self.integration.reading_occurrence_type
        if not reading_form:
            self.add_report(
                "Configurações incorretas. O formulário da leitura não existe."
            )
            self.finish_up(error=True)
            return

        for instrument in response["Items"]:
            if "Name" not in instrument:
                self.add_report("Ignorando um instrumento pois o nome não foi recebido")
                continue

            if self.integration.instrument_code_prefix:
                prefix = self.integration.instrument_code_prefix
                if (len(instrument["Name"]) < len(prefix)) or (
                    instrument["Name"][: len(prefix)] != prefix
                ):
                    self.add_report(
                        "Ignorando o instrumento {} por não atender aos requisitos de prefixo configurados".format(
                            instrument["Name"]
                        )
                    )
                    continue

            record_query = {"occurrence_type": instrument_form}
            record_query[
                "form_data__{}".format(
                    to_snake_case(self.integration.instrument_code_field)
                )
            ] = instrument["Name"]

            try:
                instrument_record = OccurrenceRecord.objects.get(**record_query)
            except Exception:
                self.add_report(
                    "Ignorando o instrumento {} por não atender aos requisitos configurados".format(
                        instrument["Name"]
                    )
                )
                continue

            for instrument_reading in instrument["Items"]:
                if (
                    "Good" in instrument_reading
                    and instrument_reading["Good"]
                    and "Value" in instrument_reading
                    and (
                        instrument_reading["Value"] or instrument_reading["Value"] == 0
                    )
                ):
                    try:
                        timestamp = datetime.strptime(
                            instrument_reading["Timestamp"],
                            "%Y-%m-%dT%H:%M:%S+00:00",
                        )
                    except Exception:
                        self.add_report(
                            "Ignorando uma leitura do instrumento {} pois não foi possível interpretar a timestamp: {}".format(
                                instrument["Name"],
                                instrument_reading["Timestamp"],
                            )
                        )
                        continue

                    already_exists = OccurrenceRecord.objects.filter(
                        datetime=timestamp,
                        occurrence_type=reading_form,
                        form_data__instrument=str(instrument_record.uuid),
                    ).exists()

                    if already_exists:
                        self.add_report(
                            "Ignorando uma leitura do instrumento {} às {} pois esse registro já foi importado".format(
                                instrument["Name"],
                                timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                            )
                        )
                    else:
                        form_data = {"instrument": str(instrument_record.uuid)}

                        try:
                            for source_dest in self.integration.field_map:
                                source_field = source_dest["source_field"]
                                dest_field = to_snake_case(source_dest["dest_field"])
                                form_data[dest_field] = instrument_reading[source_field]
                                if (
                                    str(instrument_reading[source_field])
                                    in error_codes.keys()
                                ):
                                    form_data["notes"] = error_codes[
                                        str(instrument_reading[source_field])
                                    ]

                        except Exception:
                            self.add_report(
                                "Erro ao importar a leitura do instrumento {} às {} - Não foi possível mapear os campos da origem para o destino".format(
                                    instrument["Name"],
                                    timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                                )
                            )
                            continue

                        try:
                            for field_to_copy in self.integration.fields_to_copy:
                                snake_case_field = to_snake_case(field_to_copy)
                                if snake_case_field in instrument_record.form_data:
                                    form_data[
                                        snake_case_field
                                    ] = instrument_record.form_data[snake_case_field]
                        except Exception:
                            self.add_report(
                                "Erro ao importar a leitura do instrumento {} às {} - Não foi possível copiar os campos do formulário do instrumento".format(
                                    instrument["Name"],
                                    timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                                )
                            )
                            continue

                        try:
                            reading_record = OccurrenceRecord(
                                company=instrument_record.company,
                                occurrence_type=reading_form,
                                datetime=timestamp,
                                form_data=form_data,
                                operational_control=self.integration.reading_operational_control,
                                integration_run=self.integration_run,
                                created_by=self.integration.reading_created_by,
                                status=self.integration.default_status,
                                approval_step=self.integration.default_approval_step,
                            )
                            # no need to trigger notifications for this integration's readings
                            post_save.disconnect(
                                notify_new_reading, sender=OccurrenceRecord
                            )
                            reading_record.save()
                            post_save.connect(
                                notify_new_reading, sender=OccurrenceRecord
                            )
                            self.add_report(
                                "Criada leitura do instrumento {} às {}.".format(
                                    instrument["Name"],
                                    timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                                )
                            )
                        except Exception:
                            self.add_report(
                                "Erro ao importar a leitura do instrumento {} às {} - não foi possível criar o registro".format(
                                    instrument["Name"],
                                    timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                                )
                            )
        self.finish_up()
