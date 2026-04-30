import json
import urllib.parse
from datetime import datetime, timedelta

import requests
from django.db.models.fields.json import KeyTextTransform

from apps.occurrence_records.models import OccurrenceRecord
from helpers.apis.hidro_api.functions import hidro_api
from helpers.serializers import get_obj_serialized
from helpers.strings import to_snake_case
from RoadLabsAPI.settings import credentials

from ..const.frequency_types import DAILY_MIDNIGHT, DAILY_NOON, HOURLY
from ..models import IntegrationRun


def clean_serialized_object(in_obj):
    keys_to_remove = [
        "history",
        "last_record_data",
        "first_record_data",
        "reference_record_data",
        "lastRecordData",
        "firstRecordData",
        "referenceRecordData",
    ]

    for key_ in keys_to_remove:
        if key_ in in_obj:
            del in_obj[key_]

    return in_obj


class EngieMaximoIntegration:
    """
    Integration class for fetching and processing data from Engie's Maximo service.

    This class handles the integration with Engie's Maximo API, fetching instrument readings
    and creating corresponding OccurrenceRecords

    Attributes:
        integration (IntegrationConfig): Configuration for the integration
        log (dict): Dictionary containing request, response and report logs
        integration_run (IntegrationRun): Instance tracking the current integration execution


    Integration Flow:
        1. Initializes with an IntegrationConfig
        2. Validates frequency type (does not support HOURLY)
        3. Gets list of instrument point numbers to fetch
        4. Calls Maximo API with configured parameters
        5. Processes each reading and creates OccurrenceRecords
        6. Copies configured fields from instruments
        7. Adds historical reading data (last, first, reference)
        8. Logs progress and errors throughout execution

    API Requirements:
        - Authorization header with Basic auth
        - Request body with:
            - sistema: "Kartado"
            - select: Fields to retrieve
            - objeto: "OSLCMEASUREMENT"
            - where: URL-encoded query for date range and point numbers

    Error Handling:
        - Logs API errors
        - Handles missing or invalid data
        - Skips existing readings
        - Reports configuration issues
        - Tracks integration success/failure

    Notes:
        - Only supports DAILY_NOON and DAILY_MIDNIGHT frequency types
        - Copies configured fields from instrument to reading
        - Maintains historical reading data relationships
        - Adds water level data from hidro_api
        - Sets validation deadlines based on company configuration
        - Creates OccurrenceRecords with configured status and approval_step
    """

    def __init__(self, integrations):
        self.integration = integrations

        self.log = {"request": {}, "report": []}

        self.integration_run = IntegrationRun(
            integration_config=self.integration,
            started_at=datetime.now(),
            finished_at=None,
            log=self.log,
        )
        self.integration_run.save()

    def add_report(self, report):
        print(report)
        self.log["report"].append(report)

    def finish_up(self, error=False):
        self.integration_run.finished_at = datetime.now()
        self.integration_run.log = self.log
        self.error = error
        self.integration_run.save()

        self.integration.last_run_at = datetime.now()
        self.integration.save()

    def get_point_nums(self):
        instrument_form = self.integration.instrument_occurrence_type
        instrument_operational_position = (
            self.integration.instrument_operational_position
        )
        if not instrument_form:
            self.add_report(
                "Configurações incorretas. O formulário do instrumento não existe."
            )
            self.finish_up(error=True)
            return

        record_query = {
            "occurrence_type": instrument_form,
            "form_data__operational_position": instrument_operational_position,
            "company": self.integration.company,
        }
        record_query[
            "form_data__{}__isnull".format(
                to_snake_case(self.integration.instrument_code_field)
            )
        ] = False

        instrument_records = OccurrenceRecord.objects.filter(**record_query).annotate(
            instrument_code_field=KeyTextTransform(
                to_snake_case(self.integration.instrument_code_field),
                "form_data",
            )
        )

        return instrument_records.values_list("instrument_code_field", flat=True)

    def run(self):
        if self.integration.frequency_type == HOURLY:
            self.add_report(
                "Integração com Maximo não suporta frequência horária. Favor reconfigurar."
            )
            self.finish_up()
            return

        if (
            self.integration.frequency_type == DAILY_NOON
            or self.integration.frequency_type == DAILY_MIDNIGHT
        ):
            data_inicio = datetime.now().date() - timedelta(days=1)

        data_fim = data_inicio + timedelta(days=2)

        url = "https://servicos.engieenergia.com.br/osb/servicos/secured/rest/maximo/consultaMaximoOslc"

        point_nums = self.get_point_nums()
        if not point_nums.exists():
            self.add_report(
                "Encerrando sem realizar a chamada pois nenhum instrumento foi encontrado."
            )
            self.finish_up(error=True)
            return

        where_clause = urllib.parse.quote(
            'measuredate>="{}T00:00:00-03:00" and measuredate<"{}T00:00:00-03:00" and pointnum in [{}]'.format(
                data_inicio, data_fim, ",".join(point_nums)
            )
        )

        request_body = {
            "sistema": "Kartado",
            "select": "POINTNUM,MEASUREDATE,MEASUREMENTVALUE,SITEID,OBSERVATION,MEASUREMENTID,ASSETNUM,LOCATION,METERNAME,INSPECTOR,TBLE_OBSERVATION",
            "objeto": "OSLCMEASUREMENT",
            "where": where_clause,
        }

        self.add_report(
            "Iniciando chamada para {} com body {}".format(
                url, json.dumps(request_body)
            )
        )

        print(json.dumps(request_body))

        try:
            request = requests.post(
                url=url,
                json=request_body,
                auth=requests.auth.HTTPBasicAuth(
                    credentials.HIDRO_USERNAME, credentials.HIDRO_PWD
                ),
            )
            request.raise_for_status()
        except Exception as e:
            self.add_report("Erro ao chamar a API: {}".format(e))
            self.finish_up(error=True)
            return

        try:
            response = request.json()
        except Exception as e:
            self.add_report("Erro ao converter a resposta para JSON: {}".format(e))
            self.finish_up(error=True)
            return

        print()
        print(response)

        self.add_report(
            "Resposta recebida. Status code: {}".format(request.status_code)
        )

        self.log["response"] = {
            "status_code": request.status_code,
            "body": response,
            "headers": dict(request.headers),
        }

        if "retorno" not in response:
            self.add_report("A resposta da integração não contém a chave 'retorno'")
            self.finish_up(error=True)
            return

        if "member" not in response["retorno"]:
            self.add_report("A resposta da integração não contém a chave 'member'")
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

        for reading in response["retorno"]["member"]:
            if "pointnum" not in reading:
                self.add_report(
                    "Ignorando uma leitura pois o pointnum não foi recebido"
                )
                continue

            record_query = {"occurrence_type": instrument_form}
            record_query[
                "form_data__{}".format(
                    to_snake_case(self.integration.instrument_code_field)
                )
            ] = reading["pointnum"]

            try:
                instrument_record = OccurrenceRecord.objects.get(**record_query)
            except Exception:
                self.add_report(
                    "Ignorando o instrumento {} por não atender aos requisitos configurados".format(
                        reading["pointnum"]
                    )
                )
                continue

            try:
                timestamp = datetime.strptime(
                    reading["measuredate"], "%Y-%m-%dT%H:%M:%S-03:00"
                )
            except Exception:
                self.add_report(
                    "Ignorando uma leitura do instrumento {} pois não foi possível interpretar a timestamp: {}".format(
                        reading["pointnum"], reading["measuredate"]
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
                        reading["pointnum"],
                        timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                    )
                )
            else:
                form_data = {"instrument": str(instrument_record.uuid)}

                try:
                    for source_dest in self.integration.field_map:
                        source_field = source_dest["source_field"]
                        dest_field = to_snake_case(source_dest["dest_field"])
                        form_data[dest_field] = reading[source_field]
                except Exception:
                    self.add_report(
                        "Erro ao importar a leitura do instrumento {} às {} - Não foi possível mapear os campos da origem para o destino".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
                    continue

                try:
                    for field_to_copy in self.integration.fields_to_copy:
                        snake_case_field = to_snake_case(field_to_copy)
                        if snake_case_field in instrument_record.form_data:
                            form_data[snake_case_field] = instrument_record.form_data[
                                snake_case_field
                            ]
                except Exception:
                    self.add_report(
                        "Erro ao importar a leitura do instrumento {} às {} - Não foi possível copiar os campos do formulário do instrumento".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
                    continue

                # Incluir campos da medição anterior
                try:
                    last_reading = (
                        OccurrenceRecord.objects.filter(
                            datetime__lte=timestamp,
                            occurrence_type=reading_form,
                            form_data__instrument=str(instrument_record.uuid),
                        )
                        .order_by("-datetime")
                        .first()
                    )

                    obj_serialized = get_obj_serialized(
                        last_reading, is_occurrence_record=True
                    )

                    if obj_serialized:
                        form_data["last_record_data"] = clean_serialized_object(
                            obj_serialized
                        )

                except Exception:
                    self.add_report(
                        "Erro ao importar a leitura do instrumento {} às {} - Não foi possível copiar os dados da leitura anterior".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
                    # no need to jump to the next reading

                # Incluir campos da medição de referência
                try:
                    reference_reading_conditions = {
                        "occurrence_type": reading_form,
                        "form_data__instrument": str(instrument_record.uuid),
                    }
                    if "reference_reading_date" in instrument_record.form_data:
                        reference_reading_date = datetime.strptime(
                            instrument_record.form_data["reference_reading_date"],
                            "%Y-%m-%dT%H:%M:%S.000Z",
                        )
                        reference_reading_conditions[
                            "datetime__gte"
                        ] = reference_reading_date

                    reference_reading = (
                        OccurrenceRecord.objects.filter(**reference_reading_conditions)
                        .order_by("datetime")
                        .first()
                    )

                    obj_serialized = get_obj_serialized(
                        reference_reading, is_occurrence_record=True
                    )

                    if obj_serialized:
                        form_data["reference_record_data"] = clean_serialized_object(
                            obj_serialized
                        )

                except Exception:
                    self.add_report(
                        "Erro ao importar a leitura do instrumento {} às {} - Não foi possível copiar os dados da leitura anterior".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
                    # no need to jump to the next reading

                # Incluir campos da primeira medição
                try:
                    first_reading_conditions = {
                        "occurrence_type": reading_form,
                        "form_data__instrument": str(instrument_record.uuid),
                    }
                    first_reading = (
                        OccurrenceRecord.objects.filter(**first_reading_conditions)
                        .order_by("datetime")
                        .first()
                    )

                    obj_serialized = get_obj_serialized(
                        first_reading, is_occurrence_record=True
                    )

                    if obj_serialized:
                        form_data["first_record_data"] = clean_serialized_object(
                            obj_serialized
                        )

                except Exception:
                    self.add_report(
                        "Erro ao importar a leitura do instrumento {} às {} - Não foi possível copiar os dados da leitura anterior".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
                    # no need to jump to the next reading

                dam = self.integration.company.metadata.get("company_prefix", "")
                level = hidro_api(dam, timestamp)["response"]

                form_data["water_level_tank"] = level["nivelReservatorio"]

                validation_timedelta = self.integration.company.metadata.get(
                    "validation_timedelta", {"days": 7}
                )

                validation_deadline = timestamp + timedelta(**validation_timedelta)

                try:
                    reading_record = OccurrenceRecord(
                        company=instrument_record.company,
                        occurrence_type=reading_form,
                        datetime=timestamp,
                        validation_deadline=validation_deadline,
                        form_data=form_data,
                        operational_control=self.integration.reading_operational_control,
                        integration_run=self.integration_run,
                        created_by=self.integration.reading_created_by,
                        status=self.integration.default_status,
                        approval_step=self.integration.default_approval_step,
                    )
                    reading_record.save()
                    self.add_report(
                        "Criada leitura do instrumento {} às {}.".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
                except Exception:
                    self.add_report(
                        "Erro ao importar a leitura do instrumento {} às {} - não foi possível criar o registro".format(
                            reading["pointnum"],
                            timestamp.strftime("%Y/%m/%d %H:%M:%S"),
                        )
                    )
        self.finish_up()
