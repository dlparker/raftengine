#!/usr/bin/env python
from features import registry

def main():
    maps_json = registry.get_feature_maps_as_json()
    print(maps_json)
    maps = registry.get_feature_maps()
    #nfrom pprint import pprint
    #pprint(maps)
    for tmap in maps:
        print(tmap.feature.name)
        for tname,item_list in tmap.tests.items():
            print("\t", tname)
            for item in item_list:
                print("\t", "\t", item.test_path, item.ref_mode)
                
    

if __name__=="__main__":
    main()
