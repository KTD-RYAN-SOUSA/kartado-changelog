import json

import pytest
from django.db.models import Q
from rest_framework import status

from apps.resources.models import Contract, ContractService
from helpers.testing.fixtures import TestBase, add_false_permission

pytestmark = pytest.mark.django_db


class TestResource(TestBase):
    model = "Contract"

    @pytest.fixture
    def contract_object(self):
        contract = Contract.objects.get(pk="339fc8c2-3351-4509-af8a-aa7c519d89ee")
        return contract

    def test_list_contract(self, client):
        response = client.get(
            path="/{}/?company={}&page_size=1".format(self.model, str(self.company.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert content["meta"]["pagination"]["count"] > 0

    def test_list_contract_without_company(self, client):
        response = client.get(
            path="/{}/".format(self.model),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_contract(self, client):
        response = client.get(
            path="/{}/{}/?company={}".format(
                self.model,
                "339fc8c2-3351-4509-af8a-aa7c519d89ee",
                str(self.company.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_filter_contract_type_unit_price_services(self, client):
        response = client.get(
            path="/{}/{}/?company={}&contract_type={}".format(
                self.model,
                "339fc8c2-3351-4509-af8a-aa7c519d89ee",
                str(self.company.pk),
                "unitPriceServices",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)
        # The call was successful

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_filter_contract_type_administration_services(self, client):
        response = client.get(
            path="/{}/{}/?company={}&contract_type={}".format(
                self.model,
                "339fc8c2-3351-4509-af8a-aa7c519d89ee",
                str(self.company.pk),
                "administrationServices",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_filter_contract_type_performance_services(self, client):
        response = client.get(
            path="/{}/{}/?company={}&contract_type={}".format(
                self.model,
                "339fc8c2-3351-4509-af8a-aa7c519d89ee",
                str(self.company.pk),
                "performanceServices",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_spent_price_from(self, client):
        response = client.get(
            path="/{}/?company={}&spent_price_from={}".format(
                self.model,
                str(self.company.pk),
                1,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_spent_price_to(self, client):
        response = client.get(
            path="/{}/?company={}&spent_price_to={}".format(
                self.model,
                str(self.company.pk),
                40000,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_spent_price_range(self, client):
        response = client.get(
            path="/{}/?company={}&spent_price_from={}&spent_price_to={}".format(
                self.model,
                str(self.company.pk),
                1,
                40000,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_performance_months_from(self, client):
        response = client.get(
            path="/{}/?company={}&performance_months_from={}".format(
                self.model,
                str(self.company.pk),
                1,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_performance_months_to(self, client):
        response = client.get(
            path="/{}/?company={}&performance_months_to={}".format(
                self.model,
                str(self.company.pk),
                10,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_performance_months_range(self, client):
        response = client.get(
            path="/{}/?company={}&performance_months_from={}&performance_months_to={}".format(
                self.model,
                str(self.company.pk),
                1,
                12,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_remaining_price_from(self, client):
        response = client.get(
            path="/{}/?company={}&remaining_price_from={}".format(
                self.model, str(self.company.pk), 200
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_remaining_price_to(self, client):
        response = client.get(
            path="/{}/?company={}&remaining_price_to={}".format(
                self.model,
                str(self.company.pk),
                100000,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_remaining_price_range(self, client):
        response = client.get(
            path="/{}/?company={}&remaining_price_from={}&remaining_price_to={}".format(
                self.model,
                str(self.company.pk),
                200,
                90000,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_accounting_classification(self, client):
        response = client.get(
            path="/{}/?company={}&accounting_classification={}".format(
                self.model,
                str(self.company.pk),
                "10425132",
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_has_unit_price_or_administration_service_true(
        self, client
    ):
        response = client.get(
            path="/{}/?company={}&has_unit_price_or_administration_service={}".format(
                self.model,
                str(self.company.pk),
                True,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) > 0

    def test_contract_filter_has_unit_price_or_administration_service_false(
        self, client
    ):
        response = client.get(
            path="/{}/?company={}&has_unit_price_or_administration_service={}".format(
                self.model,
                str(self.company.pk),
                False,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) == 0

    def test_contract_filter_has_unit_price_or_administration_service_only_administration_permission(
        self, client
    ):
        add_false_permission(
            self.user, self.company, "ContractItemUnitPrice", {"can_view": False}
        )

        response = client.get(
            path="/{}/?company={}&has_unit_price_or_administration_service={}".format(
                self.model,
                str(self.company.pk),
                True,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) >= 0

    def test_contract_filter_has_unit_price_or_administration_service_only_unit_price_permission(
        self, client
    ):
        add_false_permission(
            self.user, self.company, "ContractItemAdministration", {"can_view": False}
        )

        response = client.get(
            path="/{}/?company={}&has_unit_price_or_administration_service={}".format(
                self.model,
                str(self.company.pk),
                True,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) >= 0

    def test_contract_filter_has_unit_price_or_administration_service_no_permissions(
        self, client
    ):
        add_false_permission(
            self.user, self.company, "ContractItemAdministration", {"can_view": False}
        )
        add_false_permission(
            self.user, self.company, "ContractItemUnitPrice", {"can_view": False}
        )

        response = client.get(
            path="/{}/?company={}&has_unit_price_or_administration_service={}".format(
                self.model,
                str(self.company.pk),
                True,
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )
        content = json.loads(response.content)

        assert response.status_code == status.HTTP_200_OK
        assert len(content["data"]) == 0

    def test_preview_download(self, client, contract_object):

        response = client.get(
            path="/{}/{}/PreviewDownload/?company={}&work_days=1".format(
                self.model,
                str(contract_object.pk),
                str(self.company.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_preview_download_without_company(self, client, contract_object):

        response = client.get(
            path="/{}/{}/PreviewDownload/?work_days=1".format(
                self.model,
                str(contract_object.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert content["errors"][0]["detail"] == 'Parâmetro "Unidade" é obrigatório'

    def test_preview_download_without_work_days(self, client, contract_object):

        response = client.get(
            path="/{}/{}/PreviewDownload/?company={}".format(
                self.model,
                str(contract_object.pk),
                str(self.company.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert content["errors"][0]["detail"] == 'Parâmetro "Dias úteis" é obrigatório'

    def test_preview_download_wrong_work_days(self, client, contract_object):

        response = client.get(
            path="/{}/{}/PreviewDownload/?company={}&work_days=teste".format(
                self.model,
                str(contract_object.pk),
                str(self.company.pk),
            ),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
            data={},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        content = json.loads(response.content)
        assert (
            content["errors"][0]["detail"]
            == 'Parâmetro "Dias úteis" deve ser um número inteiro'
        )

    def test_contract_delete(self, client, contract_object):

        response = client.delete(
            path="/{}/{}/".format(self.model, str(contract_object.pk)),
            content_type="application/vnd.api+json",
            HTTP_AUTHORIZATION="JWT {}".format(self.token),
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        contract_services = ContractService.objects.filter(
            Q(unit_price_service_contracts=contract_object)
            | Q(administration_service_contracts=contract_object)
            | Q(performance_service_contracts=contract_object)
        )

        assert not contract_services.exists()
