import unittest

import pytest

import jsonschema2crateo

MULTI_PROPERTY = {
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

SINGLE_PROPERTY = {
    "type": "string"
}


@pytest.mark.parametrize("test_name, property_values, expected_result",
                         [
                             ('Multi property test', MULTI_PROPERTY, True),
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
