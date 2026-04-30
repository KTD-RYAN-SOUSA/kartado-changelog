from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Company, Firm, SubCompany
from apps.constructions.models import Construction
from apps.occurrence_records.models import OccurrenceType
from apps.roads.models import Road
from apps.service_orders.models import ServiceOrderActionStatus
from apps.users.models import User
from apps.work_plans.models import Job


def get_reporting_fields(company: Company):
    reporting_fields = {
        "select_fields": {
            "custom_option_fields": [
                {
                    "field_name": "direction",
                    "label": "Sentido",
                    "source": "direction",
                    "company_permissions": [
                        {
                            "permission": "hide_reporting_location",
                            "reverse": True,
                        }
                    ],
                    "user_permissions": [],
                },
                {
                    "field_name": "lane",
                    "label": "Faixa",
                    "source": "lane",
                    "company_permissions": [
                        {
                            "permission": "hide_reporting_location",
                            "reverse": True,
                        }
                    ],
                    "user_permissions": [],
                },
                {
                    "field_name": "track",
                    "label": "Pista",
                    "source": "track",
                    "user_permissions": [],
                    "company_permissions": [
                        {"permission": "show_track", "reverse": False},
                        {
                            "permission": "hide_reporting_location",
                            "reverse": True,
                        },
                    ],
                },
                {
                    "field_name": "branch",
                    "label": "Ramo",
                    "source": "branch",
                    "user_permissions": [],
                    "company_permissions": [
                        {"reverse": False, "permission": "show_track"},
                        {
                            "permission": "hide_reporting_location",
                            "reverse": True,
                        },
                    ],
                },
                {
                    "field_name": "occurrence_type__occurrence_kind",
                    "label": "Natureza",
                    "source": "occurrence_kind",
                    "company_permissions": [],
                    "user_permissions": [],
                },
                {
                    "field_name": "lot",
                    "label": "Lote",
                    "source": "lot",
                    "company_permissions": [
                        {
                            "permission": "hide_reporting_location",
                            "reverse": True,
                        }
                    ],
                    "user_permissions": [],
                },
                {
                    "field_name": "resource",
                    "label": "Recursos Utilizados",
                    "source": "resource",
                    "company_permissions": [],
                    "user_permissions": [],
                },
            ],
            "default_select_fields": [
                {
                    "field_name": "approval_step",
                    "label": "Aprovação",
                    "queryset": ApprovalStep.objects.filter(
                        approval_flow__target_model="reportings.Reporting",
                        approval_flow__company_id=company.uuid,
                    ),
                    "company_permissions": [],
                    "user_permissions": [
                        {"model": "approval_step", "permission": "can_view"}
                    ],
                },
                {
                    "field_name": "status",
                    "label": "Status",
                    "queryset": ServiceOrderActionStatus.objects.filter(
                        kind="REPORTING_STATUS", companies__uuid=company.uuid
                    ),
                    "company_permissions": [],
                    "user_permissions": [],
                },
                {
                    "field_name": "road_name",
                    "label": "Rodovia",
                    "company_permissions": [
                        {
                            "permission": "hide_reporting_location",
                            "reverse": True,
                        }
                    ],
                    "user_permissions": [],
                    "queryset": Road.objects.filter(company__uuid=company.uuid)
                    .order_by("name")
                    .distinct("name"),
                    "value_prop": "name",
                },
                {
                    "field_name": "job",
                    "label": "Programação",
                    "company_permissions": [],
                    "user_permissions": [],
                    "queryset": Job.objects.filter(
                        company__uuid=company.uuid, archived=False
                    ),
                    "name": "title",
                },
                {
                    "field_name": "firm",
                    "label": "Equipe",
                    "queryset": Firm.objects.filter(company_id=company.uuid),
                    "company_permissions": [],
                    "user_permissions": [],
                },
                {
                    "field_name": "occurrence_type",
                    "label": "Classe",
                    "queryset": OccurrenceType.objects.filter(
                        company__uuid=company.uuid
                    ),
                    "company_permissions": [],
                    "user_permissions": [],
                },
                {
                    "field_name": "created_by",
                    "label": "Criador",
                    "queryset": User.objects.filter(companies__uuid=company.uuid),
                    "company_permissions": [],
                    "user_permissions": [],
                    "name": "full_name",
                },
                {
                    "field_name": "construction",
                    "label": "Obra",
                    "queryset": Construction.objects.filter(company_id=company.uuid),
                    "user_permissions": [
                        {"model": "construction", "permission": "can_view"}
                    ],
                    "company_permissions": [],
                },
                {
                    "field_name": "firm__subcompany",
                    "label": "Empresa",
                    "queryset": SubCompany.objects.filter(company_id=company.uuid),
                    "user_permissions": [
                        {
                            "model": "sub_company",
                            "permission": "can_view",
                        }
                    ],
                    "company_permissions": [],
                },
            ],
        },
        "date_fields": [
            {
                "field_name": "updated_at__date",
                "label": "Atualizado em",
                "company_permissions": [],
                "user_permissions": [],
            },
            {
                "field_name": "executed_at__date",
                "label": "Executado em",
                "company_permissions": [],
                "user_permissions": [],
            },
            {
                "field_name": "created_at__date",
                "label": "Data de Criação",
                "company_permissions": [],
                "user_permissions": [],
            },
            {
                "field_name": "found_at__date",
                "label": "Encontrado em",
                "company_permissions": [],
                "user_permissions": [],
            },
            {
                "field_name": "due_at__date",
                "label": "Prazo",
                "company_permissions": [],
                "user_permissions": [],
            },
            {
                "field_name": "job__start_date__date",
                "label": "Data Inicial da Programação",
                "company_permissions": [],
                "user_permissions": [],
            },
            {
                "field_name": "job__end_date__date",
                "label": "Data Final da Programação",
                "company_permissions": [],
                "user_permissions": [],
            },
        ],
        "number_fields": [
            {
                "field_name": "end_km",
                "label": "km final",
                "company_permissions": [
                    {"permission": "hide_reporting_location", "reverse": True}
                ],
                "user_permissions": [],
            },
            {
                "field_name": "project_km",
                "label": "km de projeto",
                "company_permissions": [
                    {"permission": "hide_reporting_location", "reverse": True},
                    {"permission": "show_project_km", "reverse": False},
                ],
                "user_permissions": [],
            },
            {
                "field_name": "project_end_km",
                "label": "km final de projeto",
                "company_permissions": [
                    {"permission": "hide_reporting_location", "reverse": True},
                    {"permission": "show_project_km", "reverse": False},
                ],
                "user_permissions": [],
            },
            {
                "field_name": "km",
                "label": "km",
                "company_permissions": [
                    {"permission": "hide_reporting_location", "reverse": True}
                ],
                "user_permissions": [],
            },
            {
                "field_name": "km_reference",
                "label": "km de referência",
                "company_permissions": [
                    {"permission": "hide_reporting_location", "reverse": True},
                    {"permission": "show_track", "reverse": False},
                ],
                "user_permissions": [],
            },
        ],
        "text_fields": [
            {
                "field_name": "number",
                "label": "Serial",
                "company_permissions": [],
                "user_permissions": [],
            }
        ],
        "boolean_fields": [
            {
                "field_name": "has_images_reporting",
                "label": "Utiliza Imagens",
                "company_permissions": [],
                "user_permissions": [
                    {"model": "reporting_file", "permission": "can_view"}
                ],
            },
            {
                "field_name": "has_rdo",
                "label": "Possui RDO",
                "company_permissions": [],
                "user_permissions": [
                    {"model": "multiple_daily_report", "permission": "can_view"}
                ],
            },
            {
                "field_name": "has_parent",
                "label": "Possui Inventário",
                "company_permissions": [],
                "user_permissions": [{"model": "inventory", "permission": "can_view"}],
            },
            {
                "field_name": "has_resource_reporting",
                "label": "Utiliza Recursos",
                "company_permissions": [],
                "user_permissions": [
                    {"model": "procedure_resource", "permission": "can_view"}
                ],
            },
            {
                "field_name": "reporting_quality_samples",
                "label": "Possui Amostra",
                "user_permissions": [
                    {"model": "quality_sample", "permission": "can_view"}
                ],
                "company_permissions": [],
            },
            {
                "field_name": "quality_sample_quality_assays",
                "label": "Possui Ensaios",
                "user_permissions": [
                    {"model": "quality_assay", "permission": "can_view"}
                ],
                "company_permissions": [],
            },
        ],
    }

    return reporting_fields
