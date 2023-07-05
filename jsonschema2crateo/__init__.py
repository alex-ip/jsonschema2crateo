import json
import re
from typing import Optional, Dict, Tuple, List

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
        (cardinality := property_values.get("owl:cardinality")) and (cardinality == "many")
        or
        (property_type := property_values.get("type")) and (property_type == "array")
        or
        (
                (type_definition_list := property_values.get("oneOf") or  property_values.get("anyOf")) and
                any(
                    [(type_definition_type := type_definition.get("type")) and (type_definition_type == "array")
                     for type_definition in type_definition_list]
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
        self.context = {}

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

        self.context = self.input_json_schema.get("@context", {})

    def convert_type_def(self, type_definition: Dict) -> List[Dict]:
        result_list = []

        if type_ref := type_definition.get("$ref"):  # Reference to class
            type_value = re.match(
                r"#/definitions/(.*)",
                type_ref
            ).group(1).title()
            result_list.append({"type": type_value})

        elif type_value := type_definition.get("type"):
            if type(type_value) == str:
                if type_value == "array":
                    # Recursive call to process array type
                    result_list += self.convert_type_def(type_definition["items"])
                else:  # Simple type, e.g. "string"
                    result = dict(type_definition)
                    result["type"] = TYPE_MAPPING.get(result["type"], result["type"])  # Map type name if required
                    result_list.append(result)
            elif type(type_value) == dict:
                result_list += self.convert_type_def(type_value)

        # "oneOf" and "anyOf" both contain list of type definitions. Only differ in cardinality
        elif subtype_list := type_definition.get("oneOf") or type_definition.get("anyOf"):
            for subtype_definition in subtype_list:
                if description := type_definition.get("description"):
                    subtype_definition["description"] = description
                result_list += self.convert_type_def(subtype_definition)

        else:
            raise Exception(f"Unrecognised type_definition {type_definition}")

        return result_list

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
        type_dict_list = self.convert_type_def(property_values)
        type_list = sorted(set([type_dict["type"] for type_dict in type_dict_list]))
        help = (
                ', '.join(
                    sorted(set([
                        type_dict.get("description")
                        for type_dict in type_dict_list
                        if type_dict.get("description")
                    ]))
                )
                or
                ', '.join(
                    sorted(set([
                        type_dict.get("format")
                        for type_dict in type_dict_list
                        if type_dict.get("format")
                    ]))
                )
        )

        crateo_input = {
            "id": PROPERTY_MAPPING.get(property_name, property_name),
            "name": PROPERTY_MAPPING.get(property_name, property_name),
            "label": property_name,
            "help": help,
            "required": input_required,
            "multiple": property_is_multiple(property_values),
            "type": type_list,
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
        properties = (
                definition_values.get("properties", {})
                or
                definition_values.get("vocabulary", {}).get("property", {})
        )

        superclasses = definition_values.get("vocabulary", {}).get("children_of", [])

        crateo_class = {
            "definition": "override",
            "subClassOf": superclasses,
            "inputs": [
                self.property2input(property_name,
                                    property_values,
                                    (property_name in definition_values.get("required", []))
                                    )
                for property_name, property_values in properties.items()
            ]
        }

        return definition_name.title(), crateo_class

    def apply_context(self, identifier: str) -> str:
        prefix_match = re.match(r'(.+):(.*)', identifier)
        if prefix_match:
            prefix = prefix_match.group(1)
            suffix = prefix_match.group(2)
            identifier = f'{self.context[prefix]}{suffix}'

        return identifier

    def translate(self, input_json_schema: Dict) -> Dict:
        """
        Function to translate input JSON schema to an output Crate-O profile
        :param input_json_schema:
        :return: output_crateo_profile
        """
        crateo_profile = {}

        input_graph = input_json_schema["@graph"]

        crateo_classes = {}
        for subgraph in input_graph:
            class_dict = {
                "definition": "override",
            }

            crateo_classes[self.apply_context(subgraph["@id"])] = class_dict

            if rdfs_subclass := subgraph.get("rdfs:subClassOf"):
                class_dict["subClassOf"] = [self.apply_context(rdfs_subclass["@id"])],

            if input_validation := subgraph.get("$validation"):
                properties = input_validation["properties"]

                class_dict["inputs"] = [
                    self.property2input(property_name,
                                        property_values,
                                        (property_name in input_validation.get("required", []))
                                        )
                    for property_name, property_values in properties.items()
                ]

                input_definitions = input_validation["definitions"]

                # Create a class for every definition
                for definition_name, definition_values in input_definitions.items():
                    crateo_class_name, crateo_class = self.definition2class(definition_name, definition_values)
                    if crateo_class:
                        crateo_classes[self.apply_context(crateo_class_name)] = crateo_class

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
