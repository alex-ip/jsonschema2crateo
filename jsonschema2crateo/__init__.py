import json
from typing import Optional, Dict, Tuple

TYPE_MAPPING = {
    "string": "Text",
}

PROPERTY_MAPPING = {
    "identifier": "@id"
}


def property_is_multiple(property_values: Dict,
                         ) -> bool:
    """
    Return True if property can hold multiple values
    :param property_values:
    :return: bool, True if property can hold multiple values, False otherwise
    """
    return bool(
        (property_type := property_values.get("type")) and (property_type == "array")
        or
        (
                (oneOf := property_values.get("oneOf")) and
                any(
                    [(oneOf_type := oneOf_item.get("type")) and (oneOf_type == "array")
                     for oneOf_item in oneOf]
                )
        )
    )


class JSONSchema2CrateO:
    """
    JSONSchema2CrateO class definition encapsulating utilitiies for translating JSONSchema to CrateO
    """

    def __init__(self,
                 input_json_schema_path: Optional[str] = None,
                 output_crateo_profile_path: Optional[str] = None,
                 version: Optional[str] = None,
                 ) -> None:
        self.input_json_schema_path: Optional[str] = input_json_schema_path
        self.output_crateo_profile_path: Optional[str] = output_crateo_profile_path
        self.version: str = version or "0.0.0"

        self.input_json_schema: Dict = {}
        self.output_crateo_profile: Dict = {}

        if input_json_schema_path:
            self.load(version)

        if output_crateo_profile_path:
            self.output_crateo_profile = self.translate(self.input_json_schema)
            self.write()

    def load(self,
             input_json_schema_path: Optional[str] = None,
             version: Optional[str] = None,
             ) -> None:

        if input_json_schema_path:
            self.input_json_schema_path = input_json_schema_path

        if version:
            self.version = version

        assert self.input_json_schema_path, 'No input_json_schema_path provided'

        with open(self.input_json_schema_path, 'r') as input_json_schema_file:
            self.input_json_schema = json.loads(input_json_schema_file.read())

    """
    "name": {
        "description": "The name of the item.",
        "type": "string",
        "owl:cardinality": "one"
    },
    {
      "id": "http://schema.org/name",
      "name": "name",
      "label": "Name",
      "help": "The name of this dataset",
      "required": true,
      "multiple": false,
      "type": [
        "Text"
      ]
    },
    """

    """
    "author": {
        "description": "The author of this content or rating. Please note that author is special in that HTML 5 provides a special mechanism for indicating authorship via the rel tag. That is equivalent to this and may be used interchangeably.",
        "anyOf": [
            {
                "$ref": "#/definitions/organization"
            },
            {
                "type": "array",
                "items": {
                    "$ref": "#/definitions/organization"
                }
            },
            {
                "$ref": "#/definitions/person"
            },
            {
                "type": "array",
                "items": {
                    "$ref": "#/definitions/person"
                }
            }
        ],
        "owl:cardinality": "many"
    },
    {
      "id": "http://schema.org/author",
      "name": "author",
      "help": "The person or organization responsible for creating this collection of data",
      "type": [
        "Person",
        "Organization"
      ],
      "multiple": true
    },
    """

    def property2input(self,
                       property_name: str,
                       property_values: Dict,
                       input_required: bool = False,
                       ) -> Dict:
        """
        Convert a BioSchemas definition into a Crate-O class definition
        :param property_name: str, Name of property
        :param property_values: Dict,
        :param input_required: bool = False,
        :return: crateo_input
        """
        crateo_input = {
            "id": PROPERTY_MAPPING.get(property_name, property_name),
            "name": PROPERTY_MAPPING.get(property_name, property_name),
            "label": property_name,
            "help": "",
            "required": input_required,
            "multiple": property_is_multiple(property_values),
        }

        return crateo_input

    def definition2class(self,
                         definition_name: str,
                         definition_values: Dict,
                         ) -> Tuple[str, Dict]:
        """
        Convert a BioSchemas definition into a Crate-O class definition
        :param definition_name:
        :param definition_values:
        :return: Tuple[str, Dict], crateo_class_name, crateo_class
        """
        crateo_class = {
            "definition": "override",
            "subClassOf": [],
            "inputs": [
                self.property2input(property_name,
                                    property_values,
                                    (property_name in definition_values.get("required", []))
                                    )
                for property_name, property_values in definition_values.get("properties", {}).items()
            ]
        }

        return definition_name.title(), crateo_class

    def translate(self, input_json_schema: Dict) -> Dict:
        """
        Function to translate input JSON schema to an output Crate-O profile
        :param input_json_schema:
        :return: output_crateo_profile
        """
        crateo_profile = {}
        input_graph = input_json_schema["@graph"]
        for subgraph in input_graph:
            if subgraph["@type"] == "rdfs:Class":
                input_validation = subgraph.get("$validation")
                if input_validation:
                    input_properties = input_validation["properties"]
                    input_definitions = input_validation["definitions"]

                    crateo_classes = {}
                    for definition_name, definition_values in input_definitions.items():
                        crateo_class_name, crateo_class = self.definition2class(definition_name, definition_values)
                        crateo_classes[crateo_class_name] = crateo_class

                    crateo_profile["classes"] = crateo_classes

        return crateo_profile

    def write(self,
              output_crateo_profile_path: Optional[str] = None
              ) -> None:
        assert self.output_crateo_profile, "Empty output_crateo_profile"

        if output_crateo_profile_path:
            self.output_crateo_profile_path = output_crateo_profile_path

        assert self.output_crateo_profile_path, 'No output_crateo_profile_path provided'

        with open(self.output_crateo_profile_path, 'w') as output_crateo_profile_file:
            output_crateo_profile_file.write(json.dumps(self.output_crateo_profile, indent='\t'))
