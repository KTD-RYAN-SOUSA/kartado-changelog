from copy import deepcopy

import pytest

from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from helpers.apps.ccr_report_utils.form_data import (
    get_form_array_iterator,
    new_get_form_data,
)

INNER_FIELDS = [
    {
        "order": 1,
        "apiName": "innerTextAreaField",
        "dataType": "textArea",
        "displayName": "Inner Text Area Field",
    },
    {
        "order": 2,
        "apiName": "innerSelectField",
        "dataType": "select",
        "displayName": "Inner Select Field",
        "selectOptions": {
            "options": [
                {"name": "Inner Select Option 1", "value": "innOpt1"},
                {"name": "Inner Select Option 2", "value": "innOpt2"},
            ]
        },
    },
    {
        "order": 3,
        "apiName": "innerImagesField",
        "dataType": "innerImagesArray",
        "displayName": "Inner Images Array Field",
    },
]

FORM_FIELDS = {
    "id": 1,
    "name": "ReportingFixture",
    "fields": [
        {
            "id": 1,
            "apiName": "numberField",
            "dataType": "number",
            "displayName": "Number Field",
        },
        {
            "id": 2,
            "apiName": "stringField",
            "dataType": "string",
            "displayName": "String Field",
        },
        {
            "id": 4,
            "apiName": "textAreaField",
            "dataType": "textArea",
            "displayName": "Text Area Field",
        },
        {
            "id": 5,
            "unit": "timestamp",
            "apiName": "timestampField",
            "dataType": "timestamp",
            "displayName": "Timestamp Field",
        },
        {
            "id": 6,
            "apiName": "selectField",
            "dataType": "select",
            "displayName": "Select Field",
            "selectOptions": {
                "options": [
                    {"name": "Option 1", "value": "opt1"},
                    {"name": "Option 2", "value": "opt2"},
                ]
            },
        },
        {
            "id": 7,
            "apiName": "imagesField",
            "dataType": "innerImagesArray",
            "displayName": "Images Array Field",
        },
        {
            "id": 8,
            "apiName": "arrayOfObjectsField",
            "dataType": "arrayOfObjects",
            "displayName": "Array of Objects Field",
            "innerFields": INNER_FIELDS,
        },
    ],
}

NUMBER_VALUE = 1
STRING_VALUE = "String"
TEXT_AREA_VALUE = "Text 1"
TIMESTAMP_VALUE = "2024-03-12T13:10:00.000Z"
SELECT_VALUE = "Option 1"
SELECT_RAW_VALUE = "opt1"
IMAGES_VALUE = [
    "18402b7c-01d8-423a-a3b9-d1996ca81e56",
    "31233ae6-ed9f-44d3-948e-ad0d926f036b",
]
INNER_TEXT_1_VALUE = "InnerText 1"
INNER_SELECT_1_VALUE = "Inner Select Option 1"
INNER_SELECT_1_RAW_VALUE = "innOpt1"
INNER_IMAGE_1_VALUE = ["46d1a832-3f4f-45b8-89e5-4d89d3e16c44"]

INNER_TEXT_2_VALUE = "InnerText 2"
INNER_SELECT_2_VALUE = "Inner Select Option 2"
INNER_SELECT_2_RAW_VALUE = "innOpt2"
INNER_IMAGE_2_VALUE = [
    "6a347154-5b73-49db-943a-9a8376023585",
    "5d533506-94dd-40ba-91a9-02db2ca295be",
]

FIRST_OBJECT_VALUE = {
    "inner_text_area_field": INNER_TEXT_1_VALUE,
    "inner_select_field": INNER_SELECT_1_RAW_VALUE,
    "inner_images_field": INNER_IMAGE_1_VALUE,
}

SECOND_OBJECT_VALUE = {
    "inner_text_area_field": INNER_TEXT_2_VALUE,
    "inner_select_field": INNER_SELECT_2_RAW_VALUE,
    "inner_images_field": INNER_IMAGE_2_VALUE,
}

ARRAY_OF_OBJECTS_VALUE = [FIRST_OBJECT_VALUE, SECOND_OBJECT_VALUE]

FILLED_FORM_DATA = {
    "number_field": NUMBER_VALUE,
    "string_field": STRING_VALUE,
    "text_area_field": TEXT_AREA_VALUE,
    "timestamp_field": TIMESTAMP_VALUE,
    "select_field": SELECT_RAW_VALUE,
    "images_field": IMAGES_VALUE,
    "array_of_objects_field": ARRAY_OF_OBJECTS_VALUE,
}


def create_reporting(form_data: dict):
    reporting = Reporting()
    reporting.occurrence_type = OccurrenceType()

    reporting.form_data = form_data
    reporting.occurrence_type.form_fields = FORM_FIELDS

    return reporting


@pytest.fixture()
def filled_reporting():
    form_data = deepcopy(FILLED_FORM_DATA)
    return create_reporting(form_data)


@pytest.fixture()
def absent_string_field_reporting():
    form_data = deepcopy(FILLED_FORM_DATA)
    form_data.pop("string_field")
    return create_reporting(form_data)


@pytest.fixture()
def absent_array_of_objects_reporting():
    form_data = deepcopy(FILLED_FORM_DATA)
    form_data.pop("array_of_objects_field")
    return create_reporting(form_data)


@pytest.fixture()
def inner_text_field_absent_reporting():
    form_data = deepcopy(FILLED_FORM_DATA)
    form_data["array_of_objects_field"][0].pop("inner_text_area_field")
    form_data["array_of_objects_field"][1].pop("inner_text_area_field")
    return create_reporting(form_data)


class TestGetFormData:
    def test_get_form_data_unexistent_field(self, filled_reporting):
        """Test getting field not defined in the occurence type"""
        assert new_get_form_data(filled_reporting, "unexistentApiName") is None

    def test_get_form_data_absent_field(self, absent_string_field_reporting):
        """Test getting field absent in form data"""
        assert new_get_form_data(absent_string_field_reporting, "stringField") is None

    def test_get_form_data_number_field(self, filled_reporting):
        """Test getting number field in form data"""
        assert new_get_form_data(filled_reporting, "numberField") == NUMBER_VALUE

    def test_get_form_data_string_field(self, filled_reporting):
        """Test getting string field in form data"""
        assert new_get_form_data(filled_reporting, "stringField") == STRING_VALUE

    def test_get_form_data_text_area_field(self, filled_reporting):
        """Test getting text area field in form data"""
        assert new_get_form_data(filled_reporting, "textAreaField") == TEXT_AREA_VALUE

    def test_get_form_data_timestamp_field(self, filled_reporting):
        """Test getting timestamp area field in form data"""
        assert new_get_form_data(filled_reporting, "timestampField") == TIMESTAMP_VALUE

    def test_get_form_data_select_field(self, filled_reporting):
        """Test getting select area field in form data"""
        assert new_get_form_data(filled_reporting, "selectField") == SELECT_VALUE

    def test_get_form_data_raw_select_field(self, filled_reporting):
        """Test getting select field raw value in form data"""
        assert (
            new_get_form_data(filled_reporting, "selectField", raw=True)
            == SELECT_RAW_VALUE
        )

    def test_get_form_data_image_field(self, filled_reporting):
        """Test getting image field value in form data"""
        assert new_get_form_data(filled_reporting, "imagesField") == IMAGES_VALUE

    def test_get_form_data_absent_array_of_objects_field(
        self, absent_array_of_objects_reporting
    ):
        """Test getting absent array of objects in form data"""
        assert (
            new_get_form_data(absent_array_of_objects_reporting, "arrayOfObjectsField")
            is None
        )

    def test_get_form_data_array_of_objects_field(self, filled_reporting):
        """Test getting array of objects in form data"""
        assert (
            new_get_form_data(filled_reporting, "arrayOfObjectsField")
            == ARRAY_OF_OBJECTS_VALUE
        )

    def test_get_form_data_first_of_array(self, filled_reporting):
        """Test getting first index of array of objects in form data"""
        assert (
            new_get_form_data(filled_reporting, "arrayOfObjectsField__0", raw=True)
            == FIRST_OBJECT_VALUE
        )

    def test_get_form_data_second_of_array(self, filled_reporting):
        """Test getting second index of array of objects in form data"""
        assert (
            new_get_form_data(filled_reporting, "arrayOfObjectsField__1")
            == SECOND_OBJECT_VALUE
        )

    def test_get_form_data_unexistent_index_of_array(self, filled_reporting):
        """Test getting second index of array of objects in form data"""
        assert new_get_form_data(filled_reporting, "arrayOfObjectsField__2") is None

    def test_get_form_data_unexistent_array_of_objects_inner_field(
        self, filled_reporting
    ):
        """Test getting field from unexistent array of objects"""
        assert (
            new_get_form_data(
                filled_reporting, "unexistingArrayOfObjectsField__0__innerTextAreaField"
            )
            is None
        )

    def test_get_form_data_unexistent_first_inner_field(self, filled_reporting):
        """Test getting unexistent field from first index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__0__unexistentField"
            )
            is None
        )

    def test_get_form_data_absent_first_inner_field(
        self, inner_text_field_absent_reporting
    ):
        """Test getting absent field from first index of array of objects in form data"""
        assert (
            new_get_form_data(
                inner_text_field_absent_reporting,
                "arrayOfObjectsField__0__innerTextAreaField",
            )
            is None
        )

    def test_get_form_first_inner_text_area_field(self, filled_reporting):
        """Test getting inner text area field from first index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__0__innerTextAreaField"
            )
            == INNER_TEXT_1_VALUE
        )

    def test_get_form_first_inner_select_field(self, filled_reporting):
        """Test getting inner select field from first index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__0__innerSelectField"
            )
            == INNER_SELECT_1_VALUE
        )

    def test_get_form_first_inner_image_field(self, filled_reporting):
        """Test getting inner images field from first index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__0__innerImagesField"
            )
            == INNER_IMAGE_1_VALUE
        )

    def test_get_form_data_unexistent_second_inner_field(self, filled_reporting):
        """Test getting unexistent field from second index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__1__unexistentField"
            )
            is None
        )

    def test_get_form_data_absent_second_inner_field(
        self, inner_text_field_absent_reporting
    ):
        """Test getting absent field from second index of array of objects in form data"""
        assert (
            new_get_form_data(
                inner_text_field_absent_reporting,
                "arrayOfObjectsField__1__innerTextAreaField",
            )
            is None
        )

    def test_get_form_second_inner_text_area_field(self, filled_reporting):
        """Test getting inner text area field from second index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__1__innerTextAreaField"
            )
            == INNER_TEXT_2_VALUE
        )

    def test_get_form_second_inner_select_field(self, filled_reporting):
        """Test getting inner select area field from second index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__1__innerSelectField"
            )
            == INNER_SELECT_2_VALUE
        )

    def test_get_form_second_inner_image_field(self, filled_reporting):
        """Test getting inner images field from second index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__1__innerImagesField"
            )
            == INNER_IMAGE_2_VALUE
        )

    def test_get_form_data_absent_index_inner_field(self, filled_reporting):
        """Test getting field from absent index of array of objects in form data"""
        assert (
            new_get_form_data(
                filled_reporting, "arrayOfObjectsField__2__innerImagesField"
            )
            is None
        )


class TesFormDataArrayIterator:
    def test_get_form_data_array_iterator(self, filled_reporting):
        """Test getting form data array iterator"""
        it = get_form_array_iterator(filled_reporting, "arrayOfObjectsField")
        assert it.field == INNER_FIELDS
        assert it.form_data == ARRAY_OF_OBJECTS_VALUE

    def test_get_absent_array_of_objects_form_data_array_iterator(
        self, absent_array_of_objects_reporting
    ):
        """Test getting form data array iterator with absence of array of objects"""
        it = get_form_array_iterator(
            absent_array_of_objects_reporting, "arrayOfObjectsField"
        )
        assert it is None

    def test_get_form_data_array_iterator_fields(self, filled_reporting):
        """Test iterating over array of objects"""

        it = get_form_array_iterator(filled_reporting, "arrayOfObjectsField")
        values = []
        try:
            while True:
                value = it.form_data
                values.append(value)
                it.inc()
        except StopIteration as e:
            print(e)
        assert values == [FIRST_OBJECT_VALUE, SECOND_OBJECT_VALUE]

    def test_get_form_data_array_iterator_text_fields(self, filled_reporting):
        """Test iterating over array of objects collecting text fields"""

        it = get_form_array_iterator(filled_reporting, "arrayOfObjectsField")
        values = []
        try:
            while True:
                value = it.get("innerTextAreaField")
                values.append(value)
                it.inc()
        except StopIteration as e:
            print(e)
        assert values == [INNER_TEXT_1_VALUE, INNER_TEXT_2_VALUE]

    def test_get_form_data_array_iterator_select_fields(self, filled_reporting):
        """Test iterating over array of objects collecting select fields"""

        it = get_form_array_iterator(filled_reporting, "arrayOfObjectsField")
        values = []
        try:
            while True:
                value = it.get("innerSelectField")
                values.append(value)
                it.inc()
        except StopIteration as e:
            print(e)
        assert values == [INNER_SELECT_1_VALUE, INNER_SELECT_2_VALUE]

    def test_get_form_data_array_iterator_raw_select_fields(self, filled_reporting):
        """Test iterating over array of objects collecting raw select fields"""

        it = get_form_array_iterator(filled_reporting, "arrayOfObjectsField")
        values = []
        try:
            while True:
                value = it.get("innerSelectField", raw=True)
                values.append(value)
                it.inc()
        except StopIteration as e:
            print(e)
        assert values == [INNER_SELECT_1_RAW_VALUE, INNER_SELECT_2_RAW_VALUE]
