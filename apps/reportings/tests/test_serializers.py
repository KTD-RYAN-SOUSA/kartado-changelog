from unittest.mock import Mock, PropertyMock, patch

import pytest
from rest_framework import serializers

from apps.reportings.serializers import (
    LightReportingSerializer,
    ReportingObjectSerializer,
    ReportingSerializer,
)


@pytest.mark.django_db
class TestLightReportingSerializer:
    def setup_method(self):
        self.serializer = LightReportingSerializer()

    def test_get_occurrence_kind_with_exception(self):
        obj = Mock()
        obj.occurrence_type = Mock()
        type(obj.occurrence_type).occurrence_kind = property(
            lambda _: (_ for _ in ()).throw(Exception("boom"))
        )
        result = self.serializer.get_occurrence_kind(obj)
        assert result is None

    def test_get_occurrence_kind_without_occurrence_type(self):
        obj = Mock()
        obj.occurrence_type = None
        result = self.serializer.get_occurrence_kind(obj)
        assert result is None


@pytest.mark.django_db
class TestReportingSerializer:
    def setup_method(self):
        self.serializer = ReportingSerializer()

    def test_get_occurrence_kind_with_exception(self):
        obj = Mock()
        obj.occurrence_type = Mock()
        type(obj.occurrence_type).occurrence_kind = property(
            lambda _: (_ for _ in ()).throw(Exception("boom"))
        )
        result = self.serializer.get_occurrence_kind(obj)
        assert result is None

    def test_get_occurrence_kind_without_occurrence_type(self):
        obj = Mock()
        obj.occurrence_type = None
        result = self.serializer.get_occurrence_kind(obj)
        assert result is None

    def test_get_parent_kind_with_exception(self):
        parent_mock = Mock()
        parent_mock.occurrence_type = True
        obj = Mock()
        obj.parent = parent_mock
        fake_occurrence_type = Mock()
        type(fake_occurrence_type).occurrence_kind = PropertyMock(
            side_effect=Exception("boom")
        )
        obj.occurrence_type = fake_occurrence_type
        result = self.serializer.get_parent_kind(obj)
        assert result is None

    def test_get_parent_kind_without_occurrence_type(self):
        obj = Mock()
        obj.parent = Mock()
        obj.parent.occurrence_type = None
        result = self.serializer.get_parent_kind(obj)
        assert result is None

    def test_get_parent_kind_without_occurrence_kind(self):
        obj = Mock()
        obj.parent = Mock()
        obj.parent.occurrence_type = True
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = None
        result = self.serializer.get_parent_kind(obj)
        assert result is None

    def test_get_shared_with_agency_when_origin_agency(self):
        obj = Mock()
        progress = Mock()
        progress.construction.origin = "AGENCY"
        obj.reporting_construction_progresses.all.return_value = [progress]
        obj.shared_with_agency = False
        obj.form_data = {}
        result = self.serializer.get_shared_with_agency(obj)
        assert result is True

    def test_get_shared_with_agency_when_origin_not_agency(self):
        obj = Mock()
        progress = Mock()
        progress.construction.origin = "OTHER"
        obj.reporting_construction_progresses.all.return_value = [progress]
        obj.shared_with_agency = False
        obj.form_data = {}
        result = self.serializer.get_shared_with_agency(obj)
        assert result is False

    def test_get_shared_with_agency_with_artesp_code_returns_boolean(self):
        """
        Test that when artesp_code is present in form_data,
        the method returns a boolean (True) instead of the string value
        """
        obj = Mock()
        obj.reporting_construction_progresses.all.return_value = []
        obj.shared_with_agency = False
        obj.form_data = {"artesp_code": "901708"}
        result = self.serializer.get_shared_with_agency(obj)
        assert result is True
        assert isinstance(result, bool)

    def test_get_shared_with_agency_without_artesp_code_returns_false(self):
        """
        Test that when artesp_code is not present in form_data,
        the method returns False
        """
        obj = Mock()
        obj.reporting_construction_progresses.all.return_value = []
        obj.shared_with_agency = False
        obj.form_data = {}
        result = self.serializer.get_shared_with_agency(obj)
        assert result is False
        assert isinstance(result, bool)

    def test_get_inspection_with_recuperations_true(self):
        relation = Mock()
        relation.reporting_relation_id = "rel"
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": ["1"],
            "recuperation_reporting_relation": "rel",
        }
        obj.reporting_relation_parent.all.return_value = [relation]
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "1"
        result = self.serializer.get_inspection_with_recuperations(obj)
        assert result is True

    def test_get_inspection_with_recuperations_false(self):
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": ["1"],
            "recuperation_reporting_relation": "rel",
        }
        obj.reporting_relation_parent.all.return_value = []
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "2"
        result = self.serializer.get_inspection_with_recuperations(obj)
        assert result is False

    def test_get_status_inspection_with_recuperations_occurrence_none(self):
        obj = Mock()
        obj.occurrence_type = None
        result = self.serializer.get_status_inspection_with_recuperations(obj)
        assert result is None

    def test_get_status_inspection_with_recuperations_string_kind(self):
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": "1",
            "recuperation_reporting_relation": "rel",
        }
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "1"
        obj.form_data = {"therapy": []}
        obj.reporting_relation_child.all.return_value = []
        obj.created_recuperations_with_relation = None
        result = self.serializer.get_status_inspection_with_recuperations(obj)
        assert result in ["02", "10"]

    def test_get_status_inspection_with_recuperations_created_true(self):
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": ["1"],
            "recuperation_reporting_relation": "rel",
        }
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "1"
        obj.form_data = {"therapy": [{"occurrence_type": "x"}]}
        obj.created_recuperations_with_relation = True
        result = self.serializer.get_status_inspection_with_recuperations(obj)
        assert result == "20"

    def test_get_status_inspection_with_recuperations_created_false(self):
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": ["1"],
            "recuperation_reporting_relation": "rel",
        }
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "1"
        obj.form_data = {"therapy": [{"occurrence_type": "x"}]}
        obj.created_recuperations_with_relation = False
        result = self.serializer.get_status_inspection_with_recuperations(obj)
        assert result == "99"

    def test_get_status_inspection_with_recuperations_reporting_relation_child_false(
        self,
    ):
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": ["2"],
            "recuperation_reporting_relation": "rel",
        }
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "X"
        obj.reporting_relation_child.all.return_value = []
        result = self.serializer.get_status_inspection_with_recuperations(obj)
        assert result == "00"

    def test_get_status_inspection_with_recuperations_reporting_relation_child_true(
        self,
    ):
        fake_relation = Mock()
        fake_relation.reporting_relation_id = "rel"
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": ["2"],
            "recuperation_reporting_relation": "rel",
        }
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "X"
        obj.reporting_relation_child.all.return_value = [fake_relation]
        result = self.serializer.get_status_inspection_with_recuperations(obj)
        assert result == "01"

    def test_get_inspection_with_recuperations_with_str_kind(self):
        relation = Mock()
        relation.reporting_relation_id = "rel"
        obj = Mock()
        obj.company.metadata = {
            "inspection_occurrence_kind": "1",  # força string
            "recuperation_reporting_relation": "rel",
        }
        obj.reporting_relation_parent.all.return_value = [relation]
        obj.occurrence_type = Mock()
        obj.occurrence_type.occurrence_kind = "1"
        result = self.serializer.get_inspection_with_recuperations(obj)
        assert result is True

    def test_get_inspection_with_recuperations_else_false(self):
        obj = Mock()

        obj.company.metadata = {}
        obj.reporting_relation_parent.all.return_value = []
        obj.occurrence_type = None

        result = self.serializer.get_inspection_with_recuperations(obj)
        assert result is False


@pytest.mark.django_db
class TestReportingSerializerCreate:
    def setup_method(self):
        self.serializer = ReportingSerializer()
        self.serializer.initial_data = {}

    # Helpers ---------------------------
    def make_fake_reporting(self):
        fake = Mock()
        fake.uuid = "fake-uuid"
        fake.company = Mock()
        fake.company.metadata = {}
        fake.firm = None

        # active_shape_files -> aceita add(*args)
        fake.active_shape_files = Mock()
        fake.active_shape_files.add = Mock()

        # history
        fake.history = Mock()
        fake.history.first.return_value = Mock()

        # precisa ser iteráveis
        fake.reporting_relation_parent = Mock()
        fake.reporting_relation_parent.all.return_value = []

        fake.reporting_relation_child = Mock()
        fake.reporting_relation_child.all.return_value = []

        fake.reporting_resources = Mock()
        fake.reporting_resources.all.return_value = []

        # usado no RDO
        fake.reportings = Mock()
        fake.reportings.add = Mock()

        return fake

    def _mock_recordmenu(self, fake_menu=None):
        if not fake_menu:
            fake_menu = Mock()
        qs = Mock()
        qs.order_by.return_value.first.return_value = fake_menu
        return qs

    def _mock_filter(self, result=None, side_effect=None):
        qs = Mock()
        if side_effect:
            qs.first.side_effect = side_effect
        else:
            qs.first.return_value = result
        return qs

    # -----------------------------------

    def test_create_with_mobile_sync_exception(self):
        validated_data = {"company": Mock(), "active_shape_files": []}
        validated_data["company"].metadata = {}
        self.serializer.initial_data = {"mobile_sync": {"id": "fake-id"}}

        with patch(
            "apps.reportings.serializers.Reporting.objects.create"
        ) as mock_create, patch(
            "apps.reportings.serializers.MobileSync.objects.get",
            side_effect=Exception("boom"),
        ), patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu, patch(
            "apps.reportings.serializers.MultipleDailyReport.objects.filter"
        ) as mock_filter:

            fake_reporting = self.make_fake_reporting()
            mock_create.return_value = fake_reporting

            mock_filter.return_value.first.return_value = None
            fake_menu = Mock()
            mock_recordmenu.return_value.order_by.return_value.first.return_value = (
                fake_menu
            )

            # cobre o except sem erro
            result = self.serializer.create(validated_data)
            assert result == fake_reporting
            assert validated_data["menu"] == fake_menu

    def test_create_self_relations_parent_filled(self):
        validated_data = {"company": Mock(), "active_shape_files": []}
        validated_data["company"].metadata = {}
        self.serializer.initial_data = {
            "create_self_relations": [
                {
                    "parent": None,
                    "child": "child-uuid",
                    "reporting_relation": "rel-uuid",
                }
            ]
        }

        with patch(
            "apps.reportings.serializers.Reporting.objects.create"
        ) as mock_create, patch(
            "apps.reportings.serializers.Reporting.objects.get"
        ), patch(
            "apps.reportings.serializers.ReportingRelation.objects.get"
        ), patch(
            "apps.reportings.serializers.ReportingInReporting.objects.create"
        ) as mock_inrel, patch(
            "apps.reportings.serializers.MultipleDailyReport.objects.filter"
        ) as mock_filter, patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu:

            fake_reporting = self.make_fake_reporting()
            mock_create.return_value = fake_reporting
            mock_filter.return_value = self._mock_filter(result=None)
            fake_menu = Mock()
            mock_recordmenu.return_value = self._mock_recordmenu(fake_menu)

            self.serializer.create(validated_data)

            mock_inrel.assert_called_once()
            assert validated_data["menu"] == fake_menu

    def test_multiple_daily_report_attributeerror(self):
        validated_data = {"company": Mock(), "active_shape_files": []}
        validated_data["company"].metadata = {}

        with patch(
            "apps.reportings.serializers.Reporting.objects.create"
        ) as mock_create, patch(
            "apps.reportings.serializers.MultipleDailyReport.objects.filter"
        ) as mock_filter, patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu:

            fake_reporting = self.make_fake_reporting()
            mock_create.return_value = fake_reporting
            mock_filter.return_value = self._mock_filter(side_effect=AttributeError)
            fake_menu = Mock()
            mock_recordmenu.return_value = self._mock_recordmenu(fake_menu)

            result = self.serializer.create(validated_data)
            assert result == fake_reporting
            assert validated_data["menu"] == fake_menu

    def test_create_self_relations_child_filled(self):
        validated_data = {"company": Mock(), "active_shape_files": []}
        validated_data["company"].metadata = {}
        self.serializer.initial_data = {
            "create_self_relations": [
                {
                    "parent": "parent-uuid",
                    "child": None,
                    "reporting_relation": "rel-uuid",
                }
            ]
        }

        with patch(
            "apps.reportings.serializers.Reporting.objects.create"
        ) as mock_create, patch(
            "apps.reportings.serializers.Reporting.objects.get"
        ), patch(
            "apps.reportings.serializers.ReportingRelation.objects.get"
        ), patch(
            "apps.reportings.serializers.ReportingInReporting.objects.create"
        ) as mock_inrel, patch(
            "apps.reportings.serializers.MultipleDailyReport.objects.filter"
        ) as mock_filter, patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu:

            fake_reporting = self.make_fake_reporting()
            mock_create.return_value = fake_reporting
            mock_filter.return_value = self._mock_filter(result=None)
            fake_menu = Mock()
            mock_recordmenu.return_value = self._mock_recordmenu(fake_menu)

            self.serializer.create(validated_data)

            assert self.serializer.initial_data["create_self_relations"][0][
                "child"
            ] == str(fake_reporting.uuid)
            mock_inrel.assert_called_once()

    def test_create_self_relations_invalid_link_exception(self):
        validated_data = {"company": Mock(), "active_shape_files": []}
        validated_data["company"].metadata = {}
        self.serializer.initial_data = {
            "create_self_relations": [
                {
                    "parent": "parent-uuid",
                    "child": "child-uuid",
                    "reporting_relation": "rel-uuid",
                }
            ]
        }

        with patch(
            "apps.reportings.serializers.Reporting.objects.create"
        ) as mock_create, patch(
            "apps.reportings.serializers.Reporting.objects.get",
            side_effect=Exception("boom"),
        ), patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu:

            fake_reporting = self.make_fake_reporting()
            mock_create.return_value = fake_reporting
            fake_menu = Mock()
            mock_recordmenu.return_value = self._mock_recordmenu(fake_menu)

            with pytest.raises(serializers.ValidationError) as exc:
                self.serializer.create(validated_data)

            assert "kartado.error.reporting_in_reporting.invalid_link" in str(exc.value)

    def test_create_with_mobile_sync_success(self):
        validated_data = {"company": Mock(), "active_shape_files": []}
        validated_data["company"].metadata = {}
        self.serializer.initial_data = {"mobile_sync": {"id": "valid-id"}}

        fake_reporting = self.make_fake_reporting()
        fake_history = Mock()
        fake_reporting.history.first.return_value = fake_history
        fake_mobile_sync = Mock()

        with patch(
            "apps.reportings.serializers.Reporting.objects.create",
            return_value=fake_reporting,
        ), patch(
            "apps.reportings.serializers.MobileSync.objects.get",
            return_value=fake_mobile_sync,
        ), patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu, patch(
            "apps.reportings.serializers.MultipleDailyReport.objects.filter"
        ) as mock_filter:

            mock_filter.return_value.first.return_value = None
            fake_menu = Mock()
            mock_recordmenu.return_value.order_by.return_value.first.return_value = (
                fake_menu
            )

            self.serializer.create(validated_data)

            # garante que entrou no else e salvou
            assert fake_history.mobile_sync == fake_mobile_sync
            fake_history.save.assert_called_once()
            assert validated_data["menu"] == fake_menu

    def test_due_at_manually_specified_true(self):
        validated_data = {
            "company": Mock(),
            "due_at": "not-none",
            "active_shape_files": [],
        }
        validated_data["company"].metadata = {}

        with patch(
            "apps.reportings.serializers.Reporting.objects.create"
        ) as mock_create, patch(
            "apps.reportings.serializers.MultipleDailyReport.objects.filter"
        ) as mock_filter, patch(
            "apps.reportings.serializers.RecordMenu.objects.filter"
        ) as mock_recordmenu:

            fake_reporting = self.make_fake_reporting()
            mock_create.return_value = fake_reporting
            mock_filter.return_value = self._mock_filter(result=None)
            fake_menu = Mock()
            mock_recordmenu.return_value = self._mock_recordmenu(fake_menu)

            result = self.serializer.create(validated_data)

            assert result == fake_reporting
            assert validated_data["due_at_manually_specified"] is True
            assert validated_data["menu"] == fake_menu


@pytest.mark.django_db
class TestReportingSerializerConditionalGeometry:
    """
    Testa a serialização condicional de feature_collection baseada em query param.

    Cenários cobertos (requisições GET):
    1. Sem request → inclui feature_collection (uso direto do serializer)
    2. Sem query param → exclui feature_collection (padrão)
    3. include_geometry=false → exclui feature_collection
    4. include_geometry=true → inclui feature_collection
    5. include_geometry=TRUE → inclui feature_collection (case insensitive)
    6. include_geometry=1 → exclui feature_collection (valor != 'true')

    Cenários cobertos (requisições de escrita):
    7. POST → sempre inclui feature_collection (para processar dados)
    8. PATCH → sempre inclui feature_collection (para processar dados)
    9. PUT → sempre inclui feature_collection (para processar dados)

    Cenários cobertos (retrieve):
    10. ReportingObjectSerializer → sempre inclui feature_collection
    11. GET retrieve (action=retrieve) → sempre inclui feature_collection
    """

    def test_init_without_request_includes_feature_collection(self):
        """
        Quando não há request no contexto, feature_collection deve ser incluído.
        Isso garante compatibilidade com uso direto do serializer (ex: scripts).
        """
        serializer = ReportingSerializer()
        assert "feature_collection" in serializer.fields

    def test_init_without_include_geometry_excludes_feature_collection(self):
        """
        Quando include_geometry não está presente ou != 'true' em requisição GET,
        feature_collection deve ser excluído.
        """
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" not in serializer.fields

    def test_init_with_include_geometry_false_excludes_feature_collection(self):
        """
        Quando include_geometry=false (ou qualquer valor != 'true') em requisição GET,
        feature_collection deve ser excluído.
        """
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {"include_geometry": "false"}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" not in serializer.fields

    def test_init_with_include_geometry_true_includes_feature_collection(self):
        """
        Quando include_geometry=true em requisição GET,
        feature_collection deve ser incluído.
        """
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {"include_geometry": "true"}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

    def test_init_with_include_geometry_TRUE_includes_feature_collection(self):
        """
        Quando include_geometry=TRUE (case insensitive) em requisição GET,
        feature_collection deve ser incluído.
        """
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {"include_geometry": "TRUE"}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

    def test_init_with_include_geometry_1_excludes_feature_collection(self):
        """
        Quando include_geometry=1 (não 'true') em requisição GET,
        feature_collection deve ser excluído.
        """
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {"include_geometry": "1"}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" not in serializer.fields

    def test_init_with_post_always_includes_feature_collection(self):
        """
        Em requisições POST, feature_collection deve sempre estar disponível
        para processar os dados enviados pelo frontend.
        """
        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.query_params = {}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

    def test_init_with_patch_always_includes_feature_collection(self):
        """
        Em requisições PATCH, feature_collection deve sempre estar disponível
        para processar os dados enviados pelo frontend.
        """
        mock_request = Mock()
        mock_request.method = "PATCH"
        mock_request.query_params = {}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

    def test_init_with_put_always_includes_feature_collection(self):
        """
        Em requisições PUT, feature_collection deve sempre estar disponível
        para processar os dados enviados pelo frontend.
        """
        mock_request = Mock()
        mock_request.method = "PUT"
        mock_request.query_params = {}

        serializer = ReportingSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

    def test_reporting_object_serializer_always_includes_feature_collection(self):
        """
        ReportingObjectSerializer sempre inclui feature_collection,
        independente de query params ou método HTTP.
        """
        # Teste sem request
        serializer = ReportingObjectSerializer()
        assert "feature_collection" in serializer.fields

        # Teste com GET sem include_geometry
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {}

        serializer = ReportingObjectSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

        # Teste com GET com include_geometry=false
        mock_request.query_params = {"include_geometry": "false"}
        serializer = ReportingObjectSerializer(context={"request": mock_request})
        assert "feature_collection" in serializer.fields

    def test_init_with_retrieve_action_always_includes_feature_collection(self):
        """
        Quando a action é 'retrieve', feature_collection deve sempre estar disponível,
        mesmo sem include_geometry=true.
        """
        mock_request = Mock()
        mock_request.method = "GET"
        mock_request.query_params = {}

        mock_view = Mock()
        mock_view.action = "retrieve"

        serializer = ReportingSerializer(
            context={"request": mock_request, "view": mock_view}
        )
        assert "feature_collection" in serializer.fields
