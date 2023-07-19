import json
import re
import urllib.request
from typing import Optional, Dict, Tuple, List, Union

import requests

EXPAND_CONTEXT = True

TYPE_MAPPING = {
    "string": "Text",
    "boolean": "Boolean",
}

PROPERTY_MAPPING = {
    "identifier": "@id"
}

DATASET_CLASS = {
    "definition": "override",
    "subClassOf": [],
    "inputs": [
        {
            "id": "http://schema.org/mentions",
            "name": "mentions",
            "help": "The Classes, Properties etc",
            "type": [
                "rdfs:Class",
                "rdf:Property",
                "definedTerm",
                "definedTermSet"
            ],
            "multiple": True
        },
        {
            "id": "http://schema.org/name",
            "name": "name",
            "label": "Name",
            "help": "The name of this ontology",
            "required": True,
            "multiple": False,
            "type": [
                "Text"
            ]
        },
        {
            "id": "http://schema.org/author",
            "name": "author",
            "help": "The person or organization responsible for creating this collection of data",
            "type": [
                "Person",
                "Organization"
            ],
            "multiple": True
        },
        {
            "id": "http://schema.org/publisher",
            "name": "publisher",
            "help": "The organization responsible for releasing this collection of data",
            "type": [
                "Organization"
            ],
            "multiple": True
        },
        {
            "id": "http://schema.org/description",
            "name": "description",
            "help": "An abstract of the collection. Include as much detail as possible about the motivation and use of "
                    "the collection, including things that we do not yet have properties for",
            "type": [
                "TextArea"
            ],
            "multiple": False
        }
    ]
}

ENABLED_CLASSES = [
    "Dataset",
    "Person",
    "Organization",
    "Book",
    "ScholarlyArticle",
    "RepositoryCollection",
    "CreativeWork",
    "CollectionProtocol",
]


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
                (type_definition_list := property_values.get("oneOf") or property_values.get("anyOf")) and
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
        self.expanded_ids = {}
        self.schema_org_context = ""

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

        if re.match(r'http(s)?://', self.input_json_schema_path):
            # Web source
            self.input_json_schema = json.loads(
                urllib.request.urlopen(self.input_json_schema_path).read().decode('utf8'))
        else:
            # File source
            with open(self.input_json_schema_path, 'r') as input_json_schema_file:
                self.input_json_schema = json.loads(input_json_schema_file.read())

        self.context = self.input_json_schema.get("@context", {})

        self.schema_org_context = [context_name
                                   for context_name, context_prefix in self.context.items()
                                   if re.match(r'http(s)?:schema.org', context_prefix)
                                   ]

    def expand_context(self, plain_id: str,
                       lookup_graph: List[Dict] = []
                       ) -> str:
        """
        Convert plain identifier to full URL
        """
        # Don't process URL
        if not re.match(r'http(s)?://', plain_id):

            # Check cache
            if new_id := self.expanded_ids.get(plain_id):
                return new_id

            new_id = plain_id

            # Check lookup graph for @id with context
            if not re.match(r'(\w+):(\w+)', new_id):  # No context to expand
                for graph in lookup_graph:
                    if graph["rdfs:label"] == new_id:
                        new_id = graph["@id"]
                        break

            # Expand context if provided
            if context_match := re.match(r'(\w+):(\w+)', new_id):
                # Don't expand schema.org
                if context_match.group(1) == self.schema_org_context:
                    new_id = context_match.group(2)
                else:
                    new_id = f'{self.context[context_match.group(1)]}{context_match.group(2)}'

                self.expanded_ids[plain_id] = new_id
                return new_id

            # # Try to guess context as a last resort (Risky?)
            # for context_name, context_prefix in self.context.items():
            #     new_id = f'{context_prefix}{plain_id}'
            #
            #     response = requests.head(new_id, allow_redirects=True)
            #     if response.status_code == 200:
            #         self.expanded_ids[plain_id] = new_id
            #         return new_id

        # No change
        self.expanded_ids[plain_id] = plain_id
        return plain_id

    def convert_type_def(self,
                         type_definitions: Union[Dict, List[Dict]],
                         lookup_graph: List[Dict],
                         ) -> List[Dict]:
        """
        Convert JSONschema type definition into a Crate-O type definition
        """
        result_list = []

        # Allow for multiple type definitions
        if type(type_definitions) == dict:
            type_definitions = [type_definitions]

        for type_definition in type_definitions:
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
                        result_list += self.convert_type_def(type_definition["items"], lookup_graph)
                    else:  # Simple type, e.g. "string"
                        result = dict(type_definition)
                        # Map type name if required
                        result["type"] = TYPE_MAPPING.get(result["type"], result["type"])
                        result_list.append(result)
                elif type(type_value) == dict:
                    result_list += self.convert_type_def(type_value, lookup_graph)

            # "oneOf" and "anyOf" both contain list of type definitions. Only differ in cardinality
            elif subtype_list := type_definition.get("oneOf") or type_definition.get("anyOf"):
                for subtype_definition in subtype_list:
                    if description := type_definition.get("description"):
                        subtype_definition["description"] = description
                    result_list += self.convert_type_def(subtype_definition, lookup_graph)

            else:
                raise Exception(f"Unrecognised type_definition {type_definition}")

        return result_list

    def property2input(self,
                       property_name: str,
                       property_values: Dict,
                       lookup_graph: List[Dict],
                       input_required: bool = False,
                       ) -> Dict:
        """
        Convert a BioSchemas definition into a Crate-O class definition
        :param property_name: str, Name of property
        :param property_values: Dict,
        :param lookup_graph: List[Dict],
        :param input_required: bool = False,
        :return: crateo_input
        """
        type_dict_list = self.convert_type_def(property_values, lookup_graph)
        type_list = sorted(set([type_dict["type"] for type_dict in type_dict_list]))
        # Strip HTML tags
        help_value = re.sub(r'<.*>', '',
                            (
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
                            )

        crateo_input = {
            "id": self.expand_context(PROPERTY_MAPPING.get(property_name, property_name), lookup_graph),
            "name": PROPERTY_MAPPING.get(property_name, property_name),
            "label": re.sub("([a-z])([A-Z])","\g<1> \g<2>", property_name).title(),  # Expand camel case to spaces
            "help": help_value,
            "required": input_required,
            "multiple": property_is_multiple(property_values),
            "type": type_list,
        }

        return crateo_input

    def definition2class(self,
                         definition_name: str,
                         definition_values: Dict,
                         lookup_graph: List[Dict],
                         ) -> Tuple[str, Dict]:
        """
        Convert a BioSchemas definition into a Crate-O class definition
        :param definition_name: str
        :param definition_values: Dict
        :param lookup_graph: List[Dict]
        :return: Tuple[str, Dict], crateo_class_name, crateo_class
        """
        class_name = definition_name.title()
        if class_type := definition_values.get("@type"):
            class_name = self.expand_context(class_type, lookup_graph)

        properties = (
                definition_values.get("properties", {})
                or
                definition_values.get("vocabulary", {}).get("property", {})
        )

        superclasses = definition_values.get("vocabulary", {}).get("children_of", [])
        if type(superclasses) == str:
            superclasses = [superclasses]

        crateo_class = {
            "definition": "override",
            "subClassOf": [self.expand_context(superclass, lookup_graph) for superclass in superclasses],
            "inputs": [
                self.property2input(property_name,
                                    property_values,
                                    lookup_graph,
                                    (property_name in definition_values.get("required", [])),
                                    )
                for property_name, property_values in properties.items()
                if property_name not in['identifier', '@id']
            ]
        }

        return class_name, crateo_class

    def translate(self, input_json_schema: Dict) -> Dict:
        """
        Function to translate input JSON schema to an output Crate-O profile
        :param input_json_schema:
        :return: output_crateo_profile
        """
        crateo_profile = {}
        root_dataset_id = None

        input_graph = input_json_schema["@graph"]

        # Add compulsory Dataset class
        dataset_class_id = "Dataset"
        # dataset_class_id = self.expand_context('Dataset', input_graph)
        crateo_classes = {dataset_class_id: DATASET_CLASS}

        for input_dict in DATASET_CLASS["inputs"]:
            input_dict["type"] = [input_type
                                  for input_type in input_dict["type"]]

        for subgraph in input_graph:
            class_dict = {
                "definition": "override",
            }
            class_id = subgraph["rdfs:label"].title()
            # class_id = self.expand_context(subgraph["@id"], input_graph)

            if rdfs_superclasses := subgraph.get("rdfs:subClassOf"):
                if type(rdfs_superclasses) == dict:
                    rdfs_superclasses = [rdfs_superclasses]
                class_dict["subClassOf"] = [self.expand_context(rdfs_superclass["@id"], input_graph)
                                            for rdfs_superclass in rdfs_superclasses]

            if input_validation := subgraph.get("$validation"):
                properties = input_validation["properties"]

                # Only add classes for definitions with properties
                # Assume first class in spec is the root dataset
                if not root_dataset_id:
                    root_dataset_id = class_id
                    root_dataset_label = subgraph["rdfs:label"]

                    crateo_profile["metadata"] = {
                        "name": subgraph["rdfs:label"],
                        "description": subgraph["rdfs:comment"],
                        "version": "0.0.0"
                    }

                crateo_classes[class_id] = class_dict

                class_dict["inputs"] = [
                    self.property2input(property_name,
                                        property_values,
                                        input_graph,
                                        (property_name in input_validation.get("required", [])),
                                        )
                    for property_name, property_values in properties.items()
                    if property_name not in['identifier', '@id']
                ]

                input_definitions = input_validation["definitions"]

                # Create a class for every definition
                for definition_name, definition_values in input_definitions.items():
                    definition_class_name, definition_class = self.definition2class(definition_name, definition_values,
                                                                                    input_graph)
                    if definition_class:
                        crateo_classes[definition_class_name] = definition_class
                        # crateo_classes[self.expand_context(definition_class_name, input_graph)] = definition_class

        root_dataset_types = [root_dataset_id]
        # root_dataset_types = [root_dataset_id, dataset_class_id]
        crateo_profile["rootDatasets"] = {
            "Schema": {
                "type": ", ".join(root_dataset_types)
            }
        }

        crateo_profile["layouts"] = {
            root_dataset_id: [
                {
                    "name": f"{root_dataset_label} values",
                    "description": f"Inputs for {root_dataset_label}",
                    "inputs": [class_input['name']
                               for class_input in crateo_classes[root_dataset_id]['inputs']
                               ]
                },
                # {
                #     "name": "Dataset values",
                #     "description": "Inputs for Dataset",
                #     "inputs": [class_input['name']
                #                for class_input in crateo_classes[dataset_class_id]['inputs']
                #                ]
                # }
            ]
        }

        crateo_profile["enabledClasses"] = [root_dataset_id] + [class_name
                                                                for class_name in ENABLED_CLASSES]
        # crateo_profile["enabledClasses"] = [root_dataset_id] + [self.expand_context(class_name, input_graph)
        #                                                         for class_name in ENABLED_CLASSES]

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
