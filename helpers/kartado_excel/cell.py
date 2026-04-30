from openpyxl import LXML
from openpyxl.cell._writer import _set_attributes
from openpyxl.compat import safe_string
from openpyxl.xml.functions import XML_NS, Element, SubElement, fromstring, whitespace


def etree_write_cell(xf, worksheet, cell, styled=None):

    value, attributes = _set_attributes(cell, styled)

    el = Element("c", attributes)
    if value is None or value == "":
        xf.write(el)
        return

    if cell.data_type == "f":
        shared_formula = worksheet.formula_attributes.get(cell.coordinate, {})
        formula = SubElement(el, "f", shared_formula)
        if value is not None:
            formula.text = value[1:]
            value = None

    if cell.data_type == "s":
        if value[:23] == "__kartado_styled_string":
            el.append(fromstring(value[23:]))  # Not tested
        else:
            inline_string = SubElement(el, "is")
            text = SubElement(inline_string, "t")
            text.text = value
            whitespace(text)

    else:
        cell_content = SubElement(el, "v")
        if value is not None:
            cell_content.text = safe_string(value)

    xf.write(el)


def lxml_write_cell(xf, worksheet, cell, styled=False):
    value, attributes = _set_attributes(cell, styled)

    if value == "" or value is None:
        with xf.element("c", attributes):
            return

    with xf.element("c", attributes):
        if cell.data_type == "f":
            shared_formula = worksheet.formula_attributes.get(cell.coordinate, {})
            with xf.element("f", shared_formula):
                if value is not None:
                    xf.write(value[1:])
                    value = None

        if cell.data_type == "s":
            if value[:23] == "__kartado_styled_string":
                xf.write(fromstring(value[23:]))
            else:
                with xf.element("is"):
                    attrs = {}
                    if value != value.strip():
                        attrs["{%s}space" % XML_NS] = "preserve"
                    el = Element("t", attrs)  # lxml can't handle xml-ns
                    el.text = value
                    xf.write(el)
                    # with xf.element("t", attrs):
                    # xf.write(value)
        else:
            with xf.element("v"):
                if value is not None:
                    xf.write(safe_string(value))


if LXML:
    write_cell = lxml_write_cell
else:
    write_cell = etree_write_cell
