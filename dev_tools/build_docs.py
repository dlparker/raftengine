#!/usr/bin/env python
from pathlib import Path
import sys
import os
from pprint import pprint
sdir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(sdir))

from dev_tools.features import FeatureRegistry
from dev_tools.trace_output import TraceOutput

registry = FeatureRegistry.get_registry()

def main():
    
    tests = registry.feature_db.get_test_records()
    for test in tests:
        print(f"{test['path']}, {test['name']}")
        jfilepath = TraceOutput.trace_file_path("json", test['path'], test['name'])
        if not jfilepath.exists():
            print(f'file {jfilepath} not found!!!')
            continue
        to = TraceOutput.from_json_file(jfilepath)
        to.write_org_file()
        to.write_org_file(include_legend=False)
        to.write_rst_file()
        to.write_csv_file()
        to.write_csv_file(digest=True)
        for section in registry.feature_db.get_test_section_records(test['path'], test['name']):
            to.write_section_puml_file(section['section_index'])

        for tfm in registry.get_test_to_feature_maps():
            if tfm.test_id_path == Path(test['path']).stem  + '.' + test['name']:
                for ftmi in tfm.maps:
                    feature = registry.features[ftmi.feature]
                    branch = feature.branches[ftmi.branch]
                    registry.build_feature_branch_file(branch)
            

if __name__=="__main__":
    main()
