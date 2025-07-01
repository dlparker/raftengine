#!/usr/bin/env python
from pathlib import Path
import sys
import os
sdir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(sdir))

from dev_tools.features import FeatureRegistry
registry = FeatureRegistry.get_registry()

def main():
    maps = registry.get_test_to_feature_maps()
    for ftmi in maps[:1]:
        print('-'*120)
        print(ftmi.test_id_path)
        for secitem in ftmi.maps:
            print(f"section {secitem.section_index} {secitem.ref_mode} '{secitem.feature}'.{secitem.branch}")

if __name__=="__main__":
    main()
