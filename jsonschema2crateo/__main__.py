import os
import sys

from jsonschema2crateo import JSONSchema2CrateO


def main():
    # print(os.path.abspath(os.curdir))
    if len(sys.argv) < 3:
        os.makedirs('../temp', exist_ok=True)
        output_crateo_profile_path = '../temp/test_output.json'
    else:
        output_crateo_profile_path = sys.argv[2]

    if len(sys.argv) < 2:
        input_json_schema_path = './test_data/ComputationalTool_v1.1-DRAFT.json'
    else:
        input_json_schema_path = sys.argv[1]

    JSONSchema2CrateO(
        input_json_schema_path,
        output_crateo_profile_path
    )


if __name__ == "__main__":
    main()
