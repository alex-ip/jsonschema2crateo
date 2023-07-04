from jsonschema2crateo import JSONSchema2CrateO
import os

def main():
    print(os.path.abspath(os.curdir))
    os.makedirs('../temp', exist_ok=True)
    JSONSchema2CrateO(
        './test_data/ComputationalTool_v1.1-DRAFT.json',
        '../temp/test_output.json'
    )

if __name__ == "__main__":
    main()