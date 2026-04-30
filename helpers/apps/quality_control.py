from tempfile import NamedTemporaryFile

from django.core.files.base import ContentFile
from openpyxl import load_workbook

from helpers.apps.artesp_excel import datetime_to_date
from helpers.strings import get_obj_from_path


def get_select_options_value(api_name, reference_value, instance):
    """
    Access a field with select options to get the value that corresponds to the reference value.
    Returns an empty string if there's a problem.
    """
    try:
        form_fields = instance.occurrence_type.form_fields["fields"]
        relevant_field = next(
            field
            for field in form_fields
            if form_fields and field["apiName"] == api_name
        )
        return next(
            option["name"]
            for option in relevant_field["selectOptions"]["options"]
            if option["value"] == str(reference_value)
        )
    except Exception:
        return ""


def get_form_data(obj, field_name, direct_access=False):
    """
    Helper function to access form_data while assuring that
    falsy values are turned into None
    """
    if direct_access:
        data_dict = obj
    else:
        data_dict = obj.form_data
    data = get_obj_from_path(data_dict, field_name)
    return data if data else None  # Turns falsy data into None


def generate_exported_file(instance):
    """
    Gathers all the data needed for the export, fills the excel template
    and uploads it to S3
    """

    # Data gathering
    reporting_assays = instance.reporting.reporting_quality_assays.all()
    export_metadata = get_obj_from_path(
        instance.reporting.company.metadata, "sisqualiExport"
    )
    export_metadata = export_metadata if export_metadata else {}

    templ_wb = load_workbook(
        filename="apps/quality_control/templates/export_template.xlsm",
        read_only=False,
        keep_vba=True,
    )
    templ_ws = templ_wb["ENSAIO"]

    # Assays & Samples
    granulometry_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Granulometria"
    ).first()
    granulometry_sample = (
        granulometry_assay.quality_sample if granulometry_assay else None
    )
    granulometry_project = (
        granulometry_sample.quality_project if granulometry_sample else None
    )
    try:
        granulometry_mass_collect = (
            get_form_data(granulometry_sample, "massCollect")[0]
            if granulometry_sample
            else None
        )
    except Exception:
        granulometry_mass_collect = None

    teor_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Teor"
    ).first()

    rice_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Rice"
    ).first()

    dui_assay = reporting_assays.filter(occurrence_type__name__icontains="DUI").first()

    iri_assay = reporting_assays.filter(occurrence_type__name__icontains="IRI").first()

    mancha_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Mancha de areia"
    ).first()

    cp_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Vazios (CP's)"
    ).first()

    densimetro_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Vazios (Densímetros)"
    ).first()

    tx_ligante_res_assay = reporting_assays.filter(
        occurrence_type__name__icontains="Taxa ligante residual"
    ).first()

    # -- Header --
    # Concessionária
    templ_ws["D2"] = instance.reporting.company.name
    # Rodovia
    road = (
        get_obj_from_path(granulometry_mass_collect, "road")
        if granulometry_mass_collect
        else None
    )
    templ_ws["D3"] = road if road else None
    # Construtora
    templ_ws["D4"] = (
        granulometry_sample.construction_firm.name
        if granulometry_sample and granulometry_sample.construction_firm
        else None
    )
    # Obra
    service_and_constructions = (
        get_obj_from_path(granulometry_mass_collect, "serviceAndConstructions")
        if granulometry_mass_collect
        else None
    )
    templ_ws["D5"] = service_and_constructions if service_and_constructions else None
    # Local (km / est.)
    start_km = (
        get_obj_from_path(granulometry_mass_collect, "startKm")
        if granulometry_mass_collect
        else None
    )
    end_km = (
        get_obj_from_path(granulometry_mass_collect, "endKm")
        if granulometry_mass_collect
        else None
    )
    templ_ws["D6"] = (
        "{} ao {}".format(start_km, end_km)
        if granulometry_mass_collect and start_km and end_km
        else None
    )
    # Local da coleta
    templ_ws["D7"] = (
        get_obj_from_path(granulometry_mass_collect, "collectionKm")
        if granulometry_mass_collect
        else None
    )
    # Pista
    lane = (
        get_obj_from_path(granulometry_mass_collect, "lane")
        if granulometry_mass_collect
        else None
    )
    templ_ws["D8"] = lane if lane else None
    # Faixa
    mass_collect_range = (
        get_obj_from_path(granulometry_mass_collect, "range")
        if granulometry_mass_collect
        else None
    )
    templ_ws["F8"] = mass_collect_range if mass_collect_range else None
    # Certificado
    templ_ws["I2"] = granulometry_sample.number if granulometry_sample else None
    # Data da aplicação
    templ_ws["I3"] = (
        datetime_to_date(granulometry_sample.collected_at)
        if granulometry_sample
        else None
    )
    # Rec. da massa no Lab.
    templ_ws["I4"] = (
        datetime_to_date(granulometry_sample.received_at)
        if granulometry_sample
        else None
    )
    # Camada
    layer = (
        get_obj_from_path(granulometry_mass_collect, "layer")
        if granulometry_mass_collect
        else None
    )
    templ_ws["I6"] = layer if layer else None
    # Projeto
    templ_ws["I7"] = (
        granulometry_sample.quality_project.project_number
        if granulometry_sample and granulometry_sample.quality_project
        else None
    )
    # Usina
    templ_ws["I8"] = (
        granulometry_sample.construction_plant.name
        if granulometry_sample and granulometry_sample.construction_plant
        else None
    )
    # Métodos de Ensaio
    assay_methods = get_obj_from_path(export_metadata, "assayMethods")
    methods_cells = ["M{}".format(row) for row in list(range(2, 8 + 1))]
    for i, cell in enumerate(methods_cells):
        templ_ws[cell] = assay_methods[i] if i < len(assay_methods) else None

    # -- Project data --
    # Teor de CAP
    templ_ws["B11"] = (
        get_form_data(granulometry_project, "capPercentReferenceValue")
        if granulometry_project
        else None
    )
    # Massa Específica Aparente
    templ_ws["D11"] = (
        get_form_data(granulometry_project, "meaReferenceValue")
        if granulometry_project
        else None
    )
    # Massa Específica Máxima
    templ_ws["G11"] = (
        get_form_data(granulometry_project, "metReferenceValue")
        if granulometry_project
        else None
    )
    # Massa Específica Efetiva
    templ_ws["J11"] = (
        get_form_data(granulometry_project, "effectiveMeReferenceValue")
        if granulometry_project
        else None
    )
    # Volume de Vazios
    templ_ws["M11"] = (
        get_form_data(granulometry_project, "vvPercentReferenceValue")
        if granulometry_project
        else None
    )
    # VAM
    templ_ws["O11"] = (
        get_form_data(granulometry_project, "vamReferenceValue")
        if granulometry_project
        else None
    )
    # VCA
    templ_ws["P11"] = (
        get_form_data(granulometry_project, "vcbPercentReferenceValue")
        if granulometry_project
        else None
    )
    # Validade
    templ_ws["Q11"] = granulometry_project.expires_at if granulometry_project else None

    # -- Equipment --
    # Mufla
    templ_ws["C13"] = (
        get_form_data(granulometry_project, "stove") if granulometry_project else None
    )
    # Última calibração
    templ_ws["G13"] = (
        get_form_data(granulometry_project, "stoveLastCalibration")
        if granulometry_project
        else None
    )
    # Certificado
    templ_ws["J13"] = (
        get_form_data(granulometry_project, "stoveCertificate")
        if granulometry_project
        else None
    )
    # Balanças
    templ_ws["C14"] = (
        get_form_data(granulometry_project, "balance") if granulometry_project else None
    )
    # Cert
    templ_ws["H14"] = (
        get_form_data(granulometry_project, "balanceCertificate")
        if granulometry_project
        else None
    )
    # Última calibração
    templ_ws["N14"] = (
        get_form_data(granulometry_project, "balanceLastCalibration")
        if granulometry_project
        else None
    )
    # Peneiras
    templ_ws["D15"] = (
        get_form_data(granulometry_project, "sieve") if granulometry_project else None
    )
    # Última calibração
    templ_ws["L15"] = (
        get_form_data(granulometry_project, "sieveLastCalibration")
        if granulometry_project
        else None
    )
    # Certificados
    templ_ws["D16"] = (
        get_form_data(granulometry_project, "sieveCertificate")
        if granulometry_project
        else None
    )
    # Densímetro
    templ_ws["Q13"] = (
        get_form_data(granulometry_project, "densimeter")
        if granulometry_project
        else None
    )
    # Certificado Dens
    templ_ws["Q14"] = (
        get_form_data(granulometry_project, "densimeterCertificate")
        if granulometry_project
        else None
    )
    # Última calibração
    templ_ws["Q15"] = (
        get_form_data(granulometry_project, "densimeterLastCalibration")
        if granulometry_project
        else None
    )
    # Offset utilizado
    templ_ws["Q16"] = (
        get_form_data(granulometry_project, "densimeterOffset1")
        if granulometry_project
        else None
    )
    templ_ws["R16"] = (
        get_form_data(granulometry_project, "densimeterOffset2")
        if granulometry_project
        else None
    )

    # -- Results (Center) --
    def get_results_cells(pt1_column, pt2_column):
        """
        Combines the available rows with the columns for both parts of
        the section
        """
        available_rows = list(range(20, 39 + 1))
        return ["{}{}".format(pt1_column, row) for row in available_rows] + [
            "{}{}".format(pt2_column, row) for row in available_rows
        ]

    first_column_cells = get_results_cells("H", "M")
    second_column_cells = get_results_cells("I", "N")
    third_column_cells = get_results_cells("J", "O")
    fourth_column_cells = get_results_cells("K", "P")
    fifth_column_cells = get_results_cells("L", "Q")

    def fill_center_results_cells(available_cells, empty_list, field):
        """
        Goes through available cells and fills with all the data
        of the field contained inside the items in empty_list
        """
        for (empty, cell) in zip(empty_list, available_cells):
            empty_data = get_obj_from_path(empty, field)
            templ_ws[cell] = empty_data if empty_data else None

    if cp_assay:
        empty_list = get_form_data(cp_assay, "empty")

        # Change header text
        templ_ws["K19"] = "Espessura (cm)"
        templ_ws["P19"] = "Espessura (cm)"
        templ_ws["L19"] = "% Vazios"
        templ_ws["Q19"] = "% Vazios"

        # Nº CP
        fill_center_results_cells(first_column_cells, empty_list, "cp")
        # Km/Est
        fill_center_results_cells(second_column_cells, empty_list, "km")
        # MEA
        fill_center_results_cells(third_column_cells, empty_list, "theoreticalDensity")
        # Espessura (cm)
        fill_center_results_cells(fourth_column_cells, empty_list, "height")
        # % Vazios
        fill_center_results_cells(fifth_column_cells, empty_list, "emptyIndex")
    elif densimetro_assay:
        empty_list = get_form_data(densimetro_assay, "empty")

        # Nº CP
        fill_center_results_cells(first_column_cells, empty_list, "cp")
        # Km/Est (especial case)
        for (empty, cell) in zip(empty_list, second_column_cells):
            empty_km = get_obj_from_path(empty, "km")
            empty_position = get_obj_from_path(empty, "position")
            templ_ws[cell] = (
                "{}+{}".format(empty_km, empty_position)
                if empty_km and empty_position
                else None
            )
        # MEA
        fill_center_results_cells(third_column_cells, empty_list, "theoreticalDensity")
        # Vazios (%) Mínimo
        fill_center_results_cells(fourth_column_cells, empty_list, "minValue")
        # Vazios (%) Máximo
        fill_center_results_cells(fifth_column_cells, empty_list, "maxValue")

    # CAP
    templ_ws["J40"] = get_form_data(teor_assay, "average") if teor_assay else None

    # RICE
    templ_ws["J41"] = get_form_data(rice_assay, "average1") if rice_assay else None

    # DUI
    templ_ws["J42"] = get_form_data(dui_assay, "finalValue") if dui_assay else None

    # IRI
    templ_ws["L40"] = get_form_data(iri_assay, "finalValue") if iri_assay else None

    # M Esp Efetiva
    templ_ws["L41"] = get_form_data(rice_assay, "average2") if rice_assay else None

    # Tx. Ligante Residual
    templ_ws["P40"] = (
        get_form_data(tx_ligante_res_assay, "finalValue")
        if tx_ligante_res_assay
        else None
    )

    # Largural Total Aplicada
    total_width = get_form_data(instance.reporting, "width")
    templ_ws["P41"] = "{} Metros".format(total_width) if total_width else None

    # Mancha de areia
    mancha_average = get_form_data(mancha_assay, "average") if mancha_assay else None
    templ_ws["P42"] = "{}".format(mancha_average) if mancha_average else None

    # Volume Total Aplicado
    width = get_form_data(instance.reporting, "width")
    length = get_form_data(instance.reporting, "length")
    height = get_form_data(instance.reporting, "height")
    templ_ws["Q41"] = (
        "{} M³".format(width * length * height) if width and length and height else None
    )

    # -- Results (Left) --
    def process_left_results(column_letter, base_field_name, obj, direct_access=False):
        """
        Helper function to fill left results depending on column and field name
        """
        cells = ["{}{}".format(column_letter, row) for row in range(20, 29 + 1)]
        fields = ["{}{}".format(base_field_name, count) for count in range(1, 10 + 1)]
        for (cell, field) in zip(cells, fields):
            templ_ws[cell] = (
                get_form_data(obj, field, direct_access=direct_access) if obj else None
            )

    # ASTM
    process_left_results("B", "astm", granulometry_project)
    # mm
    process_left_results("C", "mm", granulometry_project)

    # Passante Encontrado (%)
    try:
        granulometry_assay_item = (
            get_form_data(granulometry_assay, "granulometryAssay")[0]
            if granulometry_assay
            else None
        )
    except Exception:
        granulometry_assay_item = {}
    process_left_results(
        "D",
        "passanPercentageSieve",
        granulometry_assay_item,
        direct_access=True,
    )
    # Projeto (%)
    process_left_results("E", "referenceValue", granulometry_project)
    # Lim. Inf (%)
    process_left_results("F", "minValue", granulometry_project)
    # Lim. Sup (%)
    process_left_results("G", "maxValue", granulometry_project)

    # -- Results (Right) --
    # Lote
    templ_ws["R19"] = get_select_options_value(
        "lot", instance.reporting.lot, instance.reporting
    )
    # Certificado Vazios
    templ_ws["R23"] = (
        granulometry_sample.responsible.get_full_name()
        if granulometry_sample and granulometry_sample.responsible
        else None
    )

    # Comprimento
    templ_ws["R28"] = "{} metros".format(length) if length else None

    # Espessura de campo
    field_width = (
        get_form_data(densimetro_assay, "fieldWidth") if densimetro_assay else None
    )
    templ_ws["R33"] = "{} m".format(field_width) if field_width else None

    # Espessura do projeto
    templ_ws["R37"] = "{} m".format(width) if width else None

    # -- Statistical Analysis --
    volumetry_assay = cp_assay if cp_assay else densimetro_assay
    # Nº Amostras
    templ_ws["J44"] = (
        get_form_data(volumetry_assay, "sampleNumber") if volumetry_assay else None
    )

    # Const. K
    templ_ws["J45"] = (
        get_form_data(volumetry_assay, "kConstant") if volumetry_assay else None
    )

    if cp_assay:
        # Change headers
        templ_ws["K44"] = "Média"
        templ_ws["K45"] = ""

        templ_ws["L44"] = (
            get_form_data(volumetry_assay, "average") if volumetry_assay else None
        )
    elif densimetro_assay:
        # Média Max
        templ_ws["L44"] = (
            get_form_data(volumetry_assay, "averageMax") if volumetry_assay else None
        )
        # Média Min
        templ_ws["L45"] = (
            get_form_data(volumetry_assay, "averageMin") if volumetry_assay else None
        )

    # X Máx
    templ_ws["N44"] = (
        get_form_data(volumetry_assay, "xMax") if volumetry_assay else None
    )
    # X Min
    templ_ws["N45"] = (
        get_form_data(volumetry_assay, "xMin") if volumetry_assay else None
    )
    # Desvio Padrão
    templ_ws["P44"] = get_form_data(cp_assay, "stdDev") if cp_assay else None

    # Condição do Lote
    templ_ws["Q45"] = (
        get_form_data(volumetry_assay, "result") if volumetry_assay else None
    )

    # -- Assay Evaluation --
    num_approved = 0
    num_approved_required = 5

    # Teor
    teor_evaluation = get_form_data(teor_assay, "result") if teor_assay else None
    teor_evaluation = teor_evaluation.lower() if teor_evaluation else None
    if teor_evaluation is None:
        teor_evaluation = "Aguardando Teor"
    elif teor_evaluation == "aprovado":
        num_approved += 1
        teor_evaluation = "Teor Aprovado"
    else:
        teor_evaluation = "Restrição em Teor"

    # Granulometria
    granulometry_evaluation = (
        get_form_data(granulometry_assay, "result") if granulometry_assay else None
    )
    granulometry_evaluation = (
        granulometry_evaluation.lower() if granulometry_evaluation else None
    )
    if granulometry_evaluation is None:
        granulometry_evaluation = "Aguardando Granulometria"
    elif granulometry_evaluation == "aprovado":
        num_approved += 1
        granulometry_evaluation = "Granulometria Aprovada"
    else:
        granulometry_evaluation = "Restrição em granulometria"

    # Volumetria
    volumetry_evaluation = (
        get_form_data(volumetry_assay, "result") if volumetry_assay else None
    )
    volumetry_evaluation = (
        volumetry_evaluation.lower() if volumetry_evaluation else None
    )
    if volumetry_evaluation is None:
        volumetry_evaluation = "Aguardando Volumetria"
    elif volumetry_evaluation == "aprovado":
        num_approved += 1
        volumetry_evaluation = "Volumetria Aprovada"
    else:
        volumetry_evaluation = "Restrição na volumetria"

    # Ensaio de mancha aprovado
    mancha_evaluation = get_form_data(mancha_assay, "result") if mancha_assay else None
    mancha_evaluation = mancha_evaluation.lower() if mancha_evaluation else None
    if mancha_evaluation is None:
        mancha_evaluation = "Aguardando ensaio de mancha"
    elif mancha_evaluation == "aprovado":
        num_approved += 1
        mancha_evaluation = "Ensaio de mancha aprovado"
    else:
        mancha_evaluation = "Restrição em ensaio de mancha"

    # Perfilômetro aprovado
    iri_evaluation = get_form_data(iri_assay, "result") if iri_assay else None
    iri_evaluation = iri_evaluation.lower() if iri_evaluation else None
    if iri_evaluation is None:
        iri_evaluation = "Aguardando ensaio de IRI"
    elif iri_evaluation == "aprovado":
        num_approved += 1
        iri_evaluation = "Ensaio de IRI aprovado"
    else:
        iri_evaluation = "Restrição em ensaio de IRI"

    if num_approved == num_approved_required:
        templ_ws["D46"] = "Aprovado"
    else:
        templ_ws["D46"] = "*{}* *{}* *{}* *{}* *{}*".format(
            teor_evaluation,
            granulometry_evaluation,
            volumetry_evaluation,
            mancha_evaluation,
            iri_evaluation,
        )

    # Parecer final do ensaio
    templ_ws["I49"] = instance.reporting.technical_opinion

    # -- Save new file to instance --
    with NamedTemporaryFile() as temp_file:
        templ_wb.save(temp_file.name)
        filename = temp_file.name.split("/")[-1]
        instance.exported_file.save(filename + ".xlsm", ContentFile(temp_file.read()))
