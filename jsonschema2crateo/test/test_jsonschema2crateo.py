import unittest

import pytest

import jsonschema2crateo

MULTI_PROPERTY_ONEOF = {
    "oneOf": [
        {
            "$ref": "#/definitions/organization"
        },
        {
            "type": "array",
            "items": {
                "$ref": "#/definitions/organization"
            }
        }
    ]
}

MULTI_PROPERTY_ARRAY = {
    "type": "array",
    "items": {
        "$ref": "#/definitions/organization"
    }
}

SINGLE_PROPERTY = {
    "type": "string"
}

CARDINALITY_MANY_PROPERTY = {
    "description": "Features or modules provided by this application (and possibly required by other applications). Functionality provided by the tool. Note: Bioschemas have removed Text from the Expected Types.",
    "anyOf": [
        {
            "$ref": "#/definitions/edamOperation"
        },
        {
            "type": "array",
            "items": {
                "$ref": "#/definitions/edamOperation"
            }
        },
        {
            "type": "string",
            "format": "uri"
        },
        {
            "type": "array",
            "items": {
                "type": "string",
                "format": "uri"
            }
        }
    ],
    "owl:cardinality": "many"
}


@pytest.mark.parametrize("test_name, property_values, expected_result",
                         [
                             ('Cardinality many property test', CARDINALITY_MANY_PROPERTY, True),
                             ('Multi property oneOf test', MULTI_PROPERTY_ONEOF, True),
                             ('Multi property array test', MULTI_PROPERTY_ARRAY, True),
                             ('Single property test', SINGLE_PROPERTY, False),
                         ]
                         )
def test_property_is_multiple(test_name, property_values, expected_result):
    assert jsonschema2crateo.property_is_multiple(property_values) == expected_result


class TestJSON2CrateO(unittest.TestCase):
    def test_load(self):
        self.assertEqual(True, True)  # add assertion here

    def test_translate(self):
        self.assertEqual(True, True)  # add assertion here

    def test_write(self):
        self.assertEqual(True, True)  # add assertion here


if __name__ == '__main__':
    unittest.main()
