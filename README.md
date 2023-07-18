# jsonschema2crateo
A utility to convert BioSchemas JSON Schemas into Crate-O profiles for populating RO-Crate files

## Repositories
- JSONschema2CrateO: <https://github.com/alex-ip/jsonschema2crateo>
- BioSchemas <https://github.com/Australian-Text-Analytics-Platform/bioschemas_specifications/> 
(Forked from <https://github.com/BioSchemas/specifications>)
- Crate-O: <https://github.com/Language-Research-Technology/crate-o>

## Information on formats:
- RO-crate: <https://www.researchobject.org/ro-crate/>
- JSONschema: <https://json-schema.org/>
- JSON-LD: <https://json-ld.org/>
- JSON: <https://json.org/>

## Usage
```bash
python -m jsonschema2crateo <input file or URL> <output file>
```

For example:
```bash
python -m jsonschema2crateo https://github.com/Australian-Text-Analytics-Platform/bioschemas_specifications/raw/ATAP_Jupyter_Enhancements_proposed/ComputationalTool/jsonld/ComputationalTool_v1.1-DRAFT.json computationalTool_crate-o_profile.json
```