permission_names = {
    "Principais recursos utilizados pelo usuário": [
        "dashboard2",
        "reporting",
        "inventory",
        "reporting_file",
        "occurrence_type",
        "job",
        "excel_import",
        "customization_menu",
    ],
    "Mapas": ["shape_file", "tile_layer"],
    "Medições e RDO": [
        "goal",
        "goal_aggregate",
        "measurement",
        "service",
        "service_specs",
        "service_usage",
        "measurement_service",
    ],
    "Acesso": [
        "company",
        "firm",
        "user_in_company",
        "user_in_firm",
        "user",
        "permission",
        "access_request",
        "approval_flow",
        "approval_step",
        "approval_transition",
    ],
    "Parametrização básica da unidade": [
        "service_order_action_status",
        "road",
        "equipment",
    ],
}

permission_types = {
    "can_view": "Visualizar",
    "can_edit": "Editar",
    "can_delete": "Deletar",
    "can_create": "Criar",
    "can_approve": "Aprovar",
    "can_view_r_d_o": "Visualizar aba RDO",
    "can_use_buttons": "Usar botões no app",
    "can_edit_resource": "Editar recursos",
    "can_create_resource": "Criar recursos",
    "can_view_price_accumulator": "Visualizar acumulador de preço",
}

queryset_types = {"all": "todos", "self": "apenas os seus", "firm": "da equipe"}

verbose_names = {
    "user": "Usuário",
    "company": "Unidade",
    "firm": "Equipe",
    "userincompany": "Associação usuário-unidade",
    "city": "Cidade",
    "location": "Localidade",
    "river": "Corpo Hídrico",
    "resource": "Recurso",
    "occurrencerecord": "Registro",
    "occurrencetype": "Formulário",
    "procedure": "Tarefa",
    "procedurefile": "Arquivo",
    "procedureresource": "Utilização de recurso",
    "serviceorder": "Serviço",
    "serviceorderaction": "Entrega",
    "serviceorderactionstatus": "Status",
    "userpermission": "Permissão",
    "watchpoint": "Ponto de monitoramento",
    "measurementbulletin": "Boletim de medição",
    "serviceorderresource": "Provisionamento de recurso",
    "administrativeinformation": "Associação objeto-serviço",
    "reporting": "Apontamento",
    "job": "Programação",
    "reportingfile": "Arquivo",
    "road": "Rodovia",
    "measurement": "Medição",
    "service": "Serviço",
    "servicespecs": "Associação serviço-formulário",
    "serviceusage": "Associação serviço-apontamento",
    "occurrencetypespecs": "Associação formulário-unidade",
    "serviceorderactionstatusspecs": "Associação status-unidade",
    "resetpasswordtoken": "Redefinição de senha",
    "log": "Log",
    "measurementservice": "Associação serviço-medição",
    "userinfirm": "Associação usuário-equipe",
    "goal": "Meta",
    "goalaggregate": "Agregado de metas",
    "file": "Arquivo",
    "contract": "Objeto",
    "monitoringplan": "Plano de monitoramento",
    "monitoringcycle": "Ciclo de monitoramento",
    "monitoringfrequency": "Frequência de monitoramento",
    "monitoringpoint": "Ponto de monitoramento",
    "monitoringcampaign": "Campanha de monitoramento",
    "monitoringrecord": "Registro de monitoramento",
    "companygroup": "Grupo de unidades",
    "accessrequest": "Solicitação de acesso",
    "tilelayer": "Camada-base de mapa",
    "shapefile": "Camada shape de mapa",
    "occurrencerecordwatcher": "Notificado de um registro",
    "approvalflow": "Fluxo de aprovação",
    "approvalstep": "Passo de aprovação",
    "approvaltransition": "Transição de aprovação",
    "canvascard": "Cartão do Canvas",
    "canvaslist": "Lista do Canvas",
    "operationalcontrol": "Controle operacinal",
    "operationalcontrolrecord": "Registro operacional",
    "materialitem": "Item material",
    "materialusage": "Utilização de item material",
    "reportingmessage": "Mensagem de apontamento",
    "reportingmessagereadreceipt": "Report de leitura de mensagem de apontamento",
    "serviceorderwatcher": "Notificado de um serviço",
    "exportrequest": "Solicitação de exportação",
    "mobilesync": "Sincronização móvel",
    "dashboard2": "Dashboard",
    "inventory": "Inventário",
    "excelimport": "Importação Excel",
    "customizationmenu": "Menu de Configurações",
    "permission": "Permissão",
}

verbose_content_types = {
    "11": "Usuário",
    "12": "Unidade",
    "13": "Equipe",
    "14": "Associação usuário-unidade",
    "15": "Cidade",
    "16": "Localidade",
    "17": "Corpo Hídrico",
    "18": "Recurso",
    "19": "Registro",
    "20": "Formulário",
    "21": "Tarefa",
    "22": "Arquivo",
    "23": "Utilização de recurso",
    "24": "Serviço",
    "25": "Entrega",
    "26": "Status",
    "27": "Permissão",
    "28": "Plano de trabalho",
    "29": "Ponto de monitoramento",
    "33": "Boletim de medição",
    "34": "Provisionamento de recurso",
    "35": "Associação objeto-serviço",
    "68": "Apontamento",
    "69": "Equipamento",
    "72": "Programação",
    "73": "Arquivo",
    "76": "Rodovia",
    "83": "Medição",
    "84": "Serviço",
    "85": "Associação serviço-formulário",
    "86": "Associação serviço-apontamento",
    "87": "Associação formulário-unidade",
    "89": "Associação status-unidade",
    "91": "Redefinição de senha",
    "93": "Log",
    "95": "Associação serviço-medição",
    "97": "Associação usuário-equipe",
    "98": "Meta",
    "100": "Agregado de metas",
    "102": "Arquivo",
    "104": "Arquivo",
    "107": "Objeto",
    "110": "Plano de monitoramento",
    "114": "Ciclo de monitoramento",
    "115": "Frequência de monitoramento",
    "116": "Ponto de monitoramento",
    "118": "Campanha de monitoramento",
    "120": "Registro de monitoramento",
    "121": "Grupo de unidades",
    "123": "Solicitação de acesso",
    "126": "Camada-base de mapa",
    "128": "Camada shape de mapa",
    "130": "Notificado de um registro",
    "131": "Fluxo de aprovação",
    "132": "Passo de aprovação",
    "135": "Transição de aprovação",
    "137": "Cartão do Canvas",
    "138": "Lista do Canvas",
    "143": "Controle operacinal",
    "144": "Registro operacional",
    "147": "Item material",
    "148": "Utilização de item material",
    "153": "Mensagem de apontamento",
    "154": "Report de leitura de mensagem de apontamento",
    "158": "Notificado de um serviço",
    "163": "Solicitação de exportação",
    "166": "Sincronização móvel",
}


def pretty_print_permission(permission_json):
    from IPython.display import Markdown, display

    for name, members in permission_names.items():
        display(Markdown("### {}".format(name)))
        for member in members:
            if member not in permission_json:
                continue
            verbose_name = verbose_names[member.replace("_", "")]
            display(Markdown("**{}**".format(verbose_name)))
            permission_obj = permission_json[member]
            permission_str = []
            queryset = None
            for key, value in permission_obj.items():
                if key == "queryset":
                    queryset = value
                elif value:
                    permission_str.append(
                        permission_types[key] if key in permission_types else key
                    )
            permission_str = "Pode " + ", ".join(permission_str)

            print(permission_str)
            if queryset:
                print("Restrição de visualização:", queryset_types[queryset])
