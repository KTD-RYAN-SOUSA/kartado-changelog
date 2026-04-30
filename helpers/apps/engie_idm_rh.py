import json
import logging
from time import sleep

import requests
from requests.exceptions import Timeout

from apps.companies.models import CompanyGroup, UserInCompany
from apps.users.models import User
from helpers.histories import bulk_update_with_history
from RoadLabsAPI.settings import credentials

from .engie_rh import (
    NoResultsError,
    ServiceUnavailableError,
    UnknownError,
    UserAlreadyExistsError,
)

NO_RESULTS_MESSAGES = [
    "DADOS NÃO ENCONTRADOS, PARA OS PARÂMETROS INFORMADOS.",
    "NENHUM FUNCIONARIO ENCONTRADO",
    "NENHUMA UO ENCONTRADA",
    "NENHUM CARGO ENCONTRADO",
    "FUNCIONÁRIO NÃO ENCONTRADO",
    "NENHUM USUARIO ENCONTRADO",
]


class EngieIdmRH:
    def __init__(
        self,
        group_id,
        company_group,
        is_supervisor=False,
        url=credentials.ENGIE_RH_URL,
        username=credentials.HIDRO_USERNAME,
        password=credentials.HIDRO_PWD,
    ):
        self.group_id = group_id
        self.company_group = company_group
        self.is_supervisor = is_supervisor
        self.url = url
        self.username = username
        self.password = password
        self.finished = False

        self.ret_data = {
            "matricula": "",
            "login": "",
            "email": "",
            "nomeCompleto": "",
            "groupid": "",
            "cdUo": "",
            "siglaUO": "",
            "cargo": "",
            "supervisor": "",
        }

    def _get_first_name(self):
        return self.ret_data["nomeCompleto"].split(" ")[0].capitalize()

    def _get_last_name(self):
        return " ".join(
            [a.capitalize() for a in self.ret_data["nomeCompleto"].split(" ")[1:]]
        )

    def _api_call(self, endpoint, payload):
        url = self.url + endpoint

        payload = {"sistema": "Kartado", **payload}
        payload = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.request(
                "POST",
                url,
                headers=headers,
                data=payload,
                auth=(self.username, self.password),
                timeout=5,
            )
        except Timeout:
            raise ServiceUnavailableError({"reason": "timeout"})

        if response.status_code != 200:
            raise ServiceUnavailableError({"reason": response.status_code})

        result = response.json()
        if not result or "dsMensagem" not in result:
            raise UnknownError(payload)
        elif result["dsMensagem"] in NO_RESULTS_MESSAGES:
            raise NoResultsError(payload, result["dsMensagem"])
        else:
            return result

    def _consulta_funcionario(self):
        payload = {"groupid": self.group_id}
        response = self._api_call("buscaUsuarioIDM", payload)
        worker = response["usuarios"][0]
        self.ret_data["matricula"] = worker["matricula"]
        self.ret_data["login"] = worker["login"]
        self.ret_data["email"] = worker["email"]
        self.ret_data["nomeCompleto"] = worker["nomeCompleto"]
        self.ret_data["groupid"] = worker["groupid"]
        self.ret_data["cdUo"] = worker["cdUo"]
        self.ret_data["siglaUO"] = worker["siglaUO"]
        self.ret_data["cargo"] = worker["cargo"]
        self.ret_data["supervisor"] = worker["supervisor"]

    def run_queries(self):
        self._consulta_funcionario()
        self.finished = True

    def exists(self):
        if not self.finished:
            self.run_queries()
        return User.objects.filter(saml_nameid=self.ret_data["groupid"]).exists()

    def create_user(self):
        if not self.exists():
            supervisor = None
            if self.ret_data["supervisor"]:
                supervisor_rh = EngieIdmRH(
                    self.ret_data["supervisor"],
                    self.company_group,
                    is_supervisor=True,
                )
                try:
                    supervisor = supervisor_rh.create_user()
                except NoResultsError:
                    pass

            user = User(
                first_name=self._get_first_name(),
                last_name=self._get_last_name(),
                username=self.ret_data["groupid"],
                saml_nameid=self.ret_data["groupid"],
                saml_idp=self.company_group.saml_idp,
                email=self.ret_data["email"],
                metadata={
                    "role": self.ret_data["cargo"],
                    "organizational_unit": self.ret_data["siglaUO"],
                    "organizational_unit_code": self.ret_data["cdUo"],
                },
                configuration={"send_email_notifications": True},
                is_supervisor=self.is_supervisor,
                is_internal=True,
                company_group=self.company_group,
                supervisor=supervisor,
            )
            user.save()
            return user

        else:
            if not self.ret_data["groupid"]:
                return None
            user = User.objects.get(saml_nameid=self.ret_data["groupid"])
            if self.is_supervisor and not user.is_supervisor:
                user.is_supervisor = True
                user.save()
            return user

    def preview_user(self):
        if not self.exists():
            supervisor = None
            if self.ret_data["supervisor"]:
                supervisor = EngieIdmRH(
                    self.ret_data["supervisor"],
                    self.company_group,
                    is_supervisor=True,
                )
                supervisor.run_queries()

            user = {
                "firstName": self._get_first_name(),
                "lastName": self._get_last_name(),
                "username": self.ret_data["groupid"],
                "samlNameid": self.ret_data["groupid"],
                "email": self.ret_data["email"],
                "metadata": {
                    "role": self.ret_data["cargo"],
                    "organizationalUnit": self.ret_data["siglaUO"],
                },
                "supervisor": {
                    "name": "{} {}".format(
                        supervisor._get_first_name(),
                        supervisor._get_last_name(),
                    ),
                    "gid": supervisor.ret_data["groupid"],
                }
                if supervisor
                else {},
            }
            return user
        else:
            raise UserAlreadyExistsError()


def run_engie_rh():
    try:
        company_group = CompanyGroup.objects.get(name="Engie")
    except CompanyGroup.DoesNotExist:
        logging.error("CompanyGroup does not exist")
    else:
        all_responses = []
        users = User.objects.filter(saml_nameid__isnull=False).exclude(username="engie")
        for user in users:
            if user.saml_nameid in [a["groupid"] for a in all_responses]:
                continue
            rh = EngieIdmRH(user.saml_nameid, company_group)
            try:
                rh.run_queries()
                all_responses.append(rh.ret_data)
            except NoResultsError:
                all_responses.append(
                    {
                        "matricula": "",
                        "login": "",
                        "email": "",
                        "nomeCompleto": "",
                        "groupid": user.saml_nameid,
                        "cdUo": "",
                        "siglaUO": "",
                        "cargo": "",
                        "supervisor": "",
                    }
                )
            sleep(1)
        for user in all_responses:
            if user["supervisor"] and user["supervisor"] not in [
                a["groupid"] for a in all_responses
            ]:
                rh = EngieIdmRH(user["supervisor"], company_group)
                try:
                    rh.run_queries()
                    all_responses.append(rh.ret_data)
                except NoResultsError:
                    all_responses.append(
                        {
                            "matricula": "",
                            "login": "",
                            "email": "",
                            "nomeCompleto": "",
                            "groupid": user["groupid"],
                            "cdUo": "",
                            "siglaUO": "",
                            "cargo": "",
                            "supervisor": "",
                        }
                    )
                sleep(0.5)

        for resp in all_responses:
            try:
                user = User.objects.get(saml_nameid__icontains=resp["groupid"])
            except Exception:
                try:
                    rh_api = EngieIdmRH(resp["groupid"], company_group)
                    _ = rh_api.create_user()
                except Exception:
                    pass
        users = User.objects.filter(saml_nameid__isnull=False).exclude(username="engie")
        for user in users:
            resp = next(
                (
                    a
                    for a in all_responses
                    if a["groupid"].upper() == user.saml_nameid.upper()
                ),
                None,
            )
            if resp and resp["supervisor"] and not user.supervisor:
                try:
                    supervisor = User.objects.get(saml_nameid=resp["supervisor"])
                    if not supervisor.is_supervisor:
                        supervisor.is_supervisor = True
                        supervisor.save()
                    user.supervisor = supervisor
                    user.save()
                    logging.info(
                        "Setting {} supervisor to {}".format(
                            user.get_full_name(), resp["supervisor"]
                        )
                    )
                except Exception:
                    pass
                continue
            if (
                resp
                and resp["supervisor"]
                and user.supervisor
                and user.supervisor.saml_nameid.upper() != resp["supervisor"].upper()
            ):
                try:
                    supervisor = User.objects.get(saml_nameid=resp["supervisor"])
                    if not supervisor.is_supervisor:
                        supervisor.is_supervisor = True
                        supervisor.save()
                    user.supervisor = supervisor
                    user.save()
                    logging.info(
                        "Setting {} supervisor from {} to {}".format(
                            user.get_full_name(),
                            user.supervisor.saml_nameid,
                            resp["supervisor"],
                        )
                    )

                except Exception:
                    pass
        users = User.objects.filter(saml_nameid__isnull=False).exclude(username="engie")
        uics_update = []
        for user in users:
            resp = next(
                (
                    a
                    for a in all_responses
                    if a["groupid"].upper() == user.saml_nameid.upper()
                ),
                None,
            )
            if resp and not resp["login"]:
                uics = UserInCompany.objects.filter(user=user).prefetch_related(
                    "company"
                )
                if uics.count():
                    companies = []
                    for uic in uics:
                        if uic.is_active:
                            companies.append(uic.company.name)
                            uic.is_active = False
                            uics_update.append(uic)
                    if len(companies):
                        logging.info(
                            "{} user is inactive in {} companies".format(
                                user.get_full_name(), ", ".join(companies)
                            )
                        )
        if uics_update:
            bulk_update_with_history(
                objs=uics_update,
                model=UserInCompany,
                user=None,
                use_django_bulk=True,
            )
