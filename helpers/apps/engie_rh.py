import json

import requests
from requests.exceptions import Timeout

from apps.users.models import User
from RoadLabsAPI.settings import credentials


class NoResultsError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class UnknownError(Exception):
    pass


class ServiceUnavailableError(Exception):
    pass


NO_RESULTS_MESSAGES = [
    "DADOS NÃO ENCONTRADOS, PARA OS PARÂMETROS INFORMADOS.",
    "NENHUM FUNCIONARIO ENCONTRADO",
    "NENHUMA UO ENCONTRADA",
    "NENHUM CARGO ENCONTRADO",
    "FUNCIONÁRIO NÃO ENCONTRADO",
]


class EngieRH:
    def __init__(
        self,
        matricula,
        company,
        is_supervisor=False,
        url=credentials.ENGIE_RH_URL,
        username=credentials.HIDRO_USERNAME,
        password=credentials.HIDRO_PWD,
    ):
        self.matricula = matricula
        self.company = company
        self.is_supervisor = is_supervisor
        self.url = url
        self.username = username
        self.password = password
        self.finished = False

        self.ret_data = {
            "nmNome": "",
            "cdSituacao": "",
            "cdCargo": "",
            "cdEmpresaEBS": "",
            "codigoUORH40": "",
            "email": "",
            "groupId": "",
            "cdUO": "",
            "sgUO": "",
            "nmUO": "",
            "dsCargo": "",
            "matriculaSupervisor": "",
        }

    def _get_first_name(self):
        return self.ret_data["nmNome"].split(" ")[0].capitalize()

    def _get_last_name(self):
        return " ".join(
            [a.capitalize() for a in self.ret_data["nmNome"].split(" ")[1:]]
        )

    def _api_call(self, endpoint, payload):
        url = self.url + endpoint

        payload = {"sistema": "KARTADO", **payload}
        payload = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.request(
                "POST",
                url,
                headers=headers,
                data=payload,
                auth=(self.username, self.password),
                timeout=3,
            )
        except Timeout:
            raise ServiceUnavailableError({"reason": "timeout"})

        if response.status_code != 200:
            raise ServiceUnavailableError({"reason": response.status_code})

        result = response.json()
        if not result or "mensagem" not in result:
            raise UnknownError(payload)
        elif result["mensagem"] in NO_RESULTS_MESSAGES:
            raise NoResultsError(payload, result["mensagem"])
        else:
            return result

    def _consulta_funcionario(self):
        payload = {"cdFuncionario": self.matricula}
        response = self._api_call("consultaFuncionario", payload)
        worker = response["funcionarios"]["funcionario"][0]
        self.ret_data["nmNome"] = worker["nmNome"]
        self.ret_data["cdSituacao"] = worker["cdSituacao"]
        self.ret_data["cdCargo"] = worker["cdCargo"]
        self.ret_data["cdEmpresaEBS"] = worker["cdEmpresaEBS"]
        self.ret_data["codigoUORH40"] = worker["codigoUORH40"]

    def _consulta_dados_adicionais(self):
        payload = {"cdFuncionario": self.matricula}
        response = self._api_call("consultaDadosAdicionais", payload)

        worker_list = response["funcionarios"]["dadosFuncionario"]
        if len(worker_list) == 1:
            worker = worker_list[0]
        elif len(worker_list) > 1:
            try:
                worker = next(a for a in worker_list if a["groupId"])
            except StopIteration:
                raise UnknownError(payload)

        self.ret_data["email"] = worker["email"]
        self.ret_data["groupId"] = worker["groupId"]

    def _consulta_uo_funcionarios(self):
        payload = {"cdUniOrg": self.ret_data["codigoUORH40"]}
        response = self._api_call("consultaUoFuncionarios", payload)
        uo = response["UOFuncionarios"]["UO"][0]
        self.ret_data["cdUO"] = uo["cdUO"]
        self.ret_data["sgUO"] = uo["sgUO"]
        self.ret_data["nmUO"] = uo["nmUO"]

    def _consulta_cargos(self):
        payload = {"cdCargo": self.ret_data["cdCargo"]}
        response = self._api_call("consultaCargos", payload)
        role = response["cargos"]["cargo"][0]
        self.ret_data["dsCargo"] = role["dsCargo"]

    def _consulta_hierarquia_funcionario(self):
        payload = {"matricula": self.matricula}
        response = self._api_call("consultaHierarquiaFuncionario", payload)
        worker = response["hierarquia"]["matriculas"][0]
        self.ret_data["matriculaSupervisor"] = worker["matriculaSupervisor"]

    def run_queries(self):
        self._consulta_funcionario()
        self._consulta_dados_adicionais()
        self._consulta_uo_funcionarios()
        self._consulta_cargos()
        self._consulta_hierarquia_funcionario()
        self.finished = True

    def exists(self):
        if not self.finished:
            self.run_queries()
        return User.objects.filter(saml_nameid=self.ret_data["groupId"]).exists()

    def create_user(self):
        if not self.exists():
            supervisor = None
            if self.ret_data["matriculaSupervisor"]:
                supervisor_rh = EngieRH(
                    self.ret_data["matriculaSupervisor"],
                    self.company,
                    is_supervisor=True,
                )
                try:
                    supervisor = supervisor_rh.create_user()
                except NoResultsError:
                    pass

            user = User(
                first_name=self._get_first_name(),
                last_name=self._get_last_name(),
                username=self.ret_data["groupId"],
                saml_nameid=self.ret_data["groupId"],
                saml_idp=self.company.company_group.saml_idp,
                email=self.ret_data["email"],
                metadata={
                    "role": self.ret_data["dsCargo"],
                    "role_code": self.ret_data["cdCargo"],
                    "engie_company_code": self.ret_data["cdEmpresaEBS"],
                    "organizational_unit": self.ret_data["sgUO"],
                    "organizational_unit_code": self.ret_data["codigoUORH40"],
                    "rh_status": self.ret_data["cdSituacao"],
                },
                configuration={"send_email_notifications": True},
                is_supervisor=self.is_supervisor,
                is_internal=True,
                company_group=self.company.company_group,
                supervisor=supervisor,
            )
            user.save()
            return user

        else:
            if not self.ret_data["groupId"]:
                return None
            user = User.objects.get(saml_nameid=self.ret_data["groupId"])
            if self.is_supervisor and not user.is_supervisor:
                user.is_supervisor = True
                user.save()
            return user

    def preview_user(self):
        if not self.exists():
            supervisor = None
            if self.ret_data["matriculaSupervisor"]:
                supervisor = EngieRH(
                    self.ret_data["matriculaSupervisor"],
                    self.company,
                    is_supervisor=True,
                )
                supervisor.run_queries()

            user = {
                "firstName": self._get_first_name(),
                "lastName": self._get_last_name(),
                "username": self.ret_data["groupId"],
                "samlNameid": self.ret_data["groupId"],
                "email": self.ret_data["email"],
                "metadata": {
                    "role": self.ret_data["dsCargo"],
                    "organizationalUnit": self.ret_data["sgUO"],
                    "rhStatus": self.ret_data["cdSituacao"],
                },
                "supervisor": {
                    "name": "{} {}".format(
                        supervisor._get_first_name(),
                        supervisor._get_last_name(),
                    ),
                    "gid": supervisor.ret_data["groupId"],
                }
                if supervisor
                else {},
            }
            return user
        else:
            raise UserAlreadyExistsError()
