import json
import os.path
import re
import urllib.request
from typing import Optional, Dict, Tuple, List, Union

import requests

SCRIPT_DIR = os.path.dirname(__file__)

EXPAND_CONTEXT = True

BIOSCHEMAS_URL = "https://raw.githubusercontent.com/BioSchemas/bioschemas-dde/main/bioschemas.json"
BIOSCHEMAS_SPEC_FILE = os.path.basename(BIOSCHEMAS_URL)

TYPE_MAPPING = {
    "string": "Text",
    "boolean": "Boolean",
}

PROPERTY_MAPPING = {
    "identifier": "@id"
}

CONTEXT_OVERRIDES = {
#    "bioschemas": "https://bioschemas.org/ComputationalWorkflow#"
}

with open(os.path.join(SCRIPT_DIR, 'dataset_class.json'), 'r') as dataset_class_file:
    DATASET_CLASS = json.load(dataset_class_file)

# Define default input groups
with open(os.path.join(SCRIPT_DIR, 'input_groups.json'), 'r') as input_groups_file:
    INPUT_GROUPS = json.load(input_groups_file)

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

def get_bioschemas() -> Dict:
    """Return a dict of BioSchemas """
    bioschemas_json = None
    if os.path.isfile(BIOSCHEMAS_SPEC_FILE):
        with open(BIOSCHEMAS_SPEC_FILE, 'r') as bioschemas_spec_file:
            bioschemas_json = bioschemas_spec_file.read()
    else:
        bioschemas_json = urllib.request.urlopen(BIOSCHEMAS_URL).read().decode('utf8')
        with open(BIOSCHEMAS_SPEC_FILE, 'w') as bioschemas_spec_file:
            bioschemas_spec_file.write(bioschemas_json)

    return json.loads(bioschemas_json)

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
        self.bioschemas = get_bioschemas()

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
                       lookup_graph: List[Dict] = [],
                       expand_schema_dot_org: bool = False,
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
                # Try overrides first
                if prefix_override := CONTEXT_OVERRIDES.get(context_match.group(1)):
                    return f'{prefix_override}{context_match.group(2)}'

                # Don't expand schema.org unless forced
                if context_match.group(1) == self.schema_org_context and not expand_schema_dot_org:
                    new_id = context_match.group(2)
                else:
                    new_id = f'{self.context[context_match.group(1)]}{context_match.group(2)}'

                self.expanded_ids[plain_id] = new_id
                return new_id

            # Try to guess context as a last resort (Risky?)
            for context_name, context_prefix in self.context.items():

                # Ignore any prefix ending with "#". These will always return status_code = 200 even on lookup failure
                if context_prefix[-1] == '#':
                    continue

                new_id = f'{context_prefix}{plain_id}'

                # Special case for bioschemas because a failed lookup will still return a 200 response
                if context_name == 'bioschemas':
                    for bioschemas_class in self.bioschemas["@graph"]:
                        if bioschemas_class["@id"] == f"{context_name}:{plain_id}":
                            return new_id
                else:
                    response = requests.get(new_id, allow_redirects=True)
                    if response.status_code == 200:
                        self.expanded_ids[plain_id] = new_id
                        return new_id

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
                ).group(1)
                # Capitalise first letter without changing camel case
                type_value = f'{type_value[0].upper()}{type_value[1:]}'
                result_list.append({"type": type_value})

            elif type_value := type_definition.get("@type", type_definition.get("type")):
                if type(type_value) == str:
                    if type_value == "array":
                        # Recursive call to process array type
                        result_list += self.convert_type_def(type_definition["items"], lookup_graph)
                    else:  # Simple type, e.g. "string"
                        result = dict(type_definition)

                        # Check for two type definitions as found in computationalWorkflow
                        if set(["@type", "type"]).issubset(set(result.keys())):
                            result["type"] = result["@type"]
                            del result["@type"]

                        # Map type name if required
                        result["type"] = TYPE_MAPPING.get(result["type"], result["type"])
                        result_list.append(result)
                elif type(type_value) == dict:
                    result_list += self.convert_type_def(type_value, lookup_graph)

            # "oneOf" and "anyOf" both contain list of type definitions. Only differ in cardinality
            elif subtype_list := type_definition.get("oneOf") or type_definition.get("anyOf"):
                for subtype_definition in subtype_list:
                    if description := type_definition.get("description"):
                        subtype_definition["description"] = re.sub(r'\<.*?\>', '', description)  # Strip HTML tags
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
        type_list = list(set([type_dict["type"] for type_dict in type_dict_list]))
        type_list = sorted([type_value.split(':')[-1] for type_value in type_list])  # Strip context prefixes
        # Strip HTML tags
        help_value = re.sub(r'\<.*?\>', '',
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
            "id": self.expand_context(PROPERTY_MAPPING.get(property_name, property_name),
                                      lookup_graph,
                                      expand_schema_dot_org=True),  # Force expansion of schema.org identifier
            "name": PROPERTY_MAPPING.get(property_name, property_name),
            "label": re.sub("([a-z])([A-Z])", "\g<1> \g<2>", property_name).title(),  # Expand camel case to spaces
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
        class_name = f'{definition_name[0].upper()}{definition_name[1:]}'  # Capitalised short id

        # if not (class_type := definition_values.get("@type")):
        #     class_type = class_name
        #
        # class_type = self.expand_context(class_type, lookup_graph)

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
            # "id": class_type,  #TODO: Check if this is valid
            "subClassOf": [self.expand_context(superclass, lookup_graph) for superclass in superclasses],
            "inputs": [
                self.property2input(property_name,
                                    property_values,
                                    lookup_graph,
                                    (property_name in definition_values.get("required", [])),
                                    )
                for property_name, property_values in properties.items()
                if property_name not in ['identifier', '@id']
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
        dataset_class_id = "Dataset"  # Use short name
        # dataset_class_id = self.expand_context('Dataset', input_graph)  # Expand full URL
        crateo_classes = {dataset_class_id: DATASET_CLASS}

        # # Expand type identifiers
        # for input_dict in DATASET_CLASS["inputs"]:
        #     input_dict["type"] = [self.expand_context(input_type, input_graph)
        #                           for input_type in input_dict["type"]]

        for subgraph in input_graph:
            class_dict = {
                "definition": "override",
            }
            class_id = f'{subgraph["rdfs:label"][0].upper()}{subgraph["rdfs:label"][1:]}'  # Capitalised short id
            # class_id = self.expand_context(subgraph["@id"], input_graph)  # Full URL

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
                        "description": re.sub(r'\<.*?\>', '', subgraph["rdfs:comment"]),  # Strip HTML tags
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
                    if property_name not in ['identifier', '@id']
                ]

                input_definitions = input_validation["definitions"]

                # Create a class for every definition
                for definition_name, definition_values in input_definitions.items():
                    definition_class_name, definition_class = self.definition2class(definition_name, definition_values,
                                                                                    input_graph)
                    if definition_class:
                        crateo_classes[definition_class_name] = definition_class
                        # crateo_classes[self.expand_context(definition_class_name, input_graph)] = definition_class

        # root_dataset_types = [root_dataset_id]  # Don't include Dataset class
        root_dataset_types = [dataset_class_id, root_dataset_id]  # Include both root dataset class and Dataset class
        crateo_profile["rootDatasets"] = {
            "Schema": {
                "type": root_dataset_types
            }
        }

        # crateo_profile["layouts"] = {
        #     root_dataset_id:
        #         {
        #             "name": f"{root_dataset_label} values",
        #             "description": f"Inputs for {root_dataset_label}",
        #             "inputs": [class_input['name']
        #                        for class_input in crateo_classes[root_dataset_id]['inputs']
        #                        ]
        #         },
        #     dataset_class_id:
        #         {
        #             "name": "Dataset values",
        #             "description": "Inputs for Dataset",
        #             "inputs": [class_input['name']
        #                        for class_input in crateo_classes[dataset_class_id]['inputs']
        #                        ]
        #         }
        # }

        crateo_profile["inputGroups"] = INPUT_GROUPS

        # Use short class names
        crateo_profile["enabledClasses"] = [root_dataset_id] + [class_name
                                                                for class_name in ENABLED_CLASSES]
        # Expand enabled class names
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


