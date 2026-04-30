""" For a notification to be valid, it needs to be defined here first """

VALID_NOTIFICATIONS = {
    "registros": {
        "informacoes_sobre_registros": {
            "time_intervals": ["DAY", "WEEK"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "OccurrenceRecord": {
                    "can_view": True,
                }
            },
        },
        "adicao_aos_notificados": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "OccurrenceRecord": {
                    "can_view": True,
                }
            },
        },
        "alteracao_de_status": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "OccurrenceRecord": {
                    "can_view": True,
                }
            },
        },
    },
    "servicos": {
        "adicao_aos_notificados": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "ServiceOrder": {
                    "can_view": True,
                },
            },
        },
        "relatorio_de_periodo": {
            "time_intervals": ["WEEK", "MONTH"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "ServiceOrder": {
                    "can_view": True,
                },
            },
        },
        "relatorio_gerencial": {
            "time_intervals": ["MONTH"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "OccurrenceRecord": {"can_view": True},
                "ServiceOrder": {"can_view": True},
                "Contract": {"can_view": True},
            },
        },
    },
    "tarefas": {
        "novas_tarefas": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "Procedure": {"can_view": True},
            },
        },
        "tarefas_pendentes": {
            "time_intervals": ["DAY", "MONTH"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "Procedure": {"can_view": True},
            },
        },
        "boletim_de_pendencias": {
            "time_intervals": ["MONTH"],
            "notification_types": ["EMAIL"],
            "required_permissions": {
                "Procedure": {"can_view": True},
            },
        },
    },
    "recursos": {
        "aprovacao_de_boletim": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "Contract": {"can_view": True},
                "MeasurementBulletin": {"can_view": True},
            },
        },
        "aprovacao_de_recursos": {
            "time_intervals": ["WEEK"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "Contract": {"can_view": True},
            },
        },
    },
    "auscultacao": {
        "novas_leituras": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "boletim_mensal": {
            "time_intervals": ["MONTH"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "boletim_semanal": {
            "time_intervals": ["WEEK"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "boletim_diario": {
            "time_intervals": ["DAY"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "novas_leituras_validadas": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "leitura_precisa_ser_refeita": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "leituras_ultrapassaram_prazo_de_validacao": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
        "outras_notificacoes": {
            "time_intervals": ["IMMEDIATE"],
            "notification_types": ["EMAIL", "PUSH"],
            "required_permissions": {
                "IntegrationConfig": {
                    "can_view": True,
                }
            },
        },
    },
}
