from dataclasses import dataclass, field, asdict
from collections import defaultdict
from typing import Optional
from copy import deepcopy
import sqlite3
import json
import logging
from pathlib import Path

from dev_tools.feature_db import FeatureDB

features_loaded = False
features_obj = None

registry = None

files_root = Path(Path(__file__).parent.parent, 'captures', 'features', 'docs',)
                 
def bool_converter(value):
    return bool(int(value))

@dataclass
class FeatureDefinition:
    name: str
    # the target_branch propert is only used during trace build, and is ephemeral
    target_branch: Optional['FeatureBranch'] = None
    branches: Optional[dict['FeatureBranch']] = field(default_factory=dict)

    def get_name_snake(self):
        return "_".join((self.name).split(' '))

    def __str__(self):
        res = self.get_name_snake()
        if self.target_branch:
            res += '.' + self.target_branch.path
        return res
    
    def to_dict(self):
        data = dict(self.__dict__)
        data['branches'] = []
        del data['target_branch']
        for b in self.branches:
            if isinstance(b, dict):
                data['branches'].append(b.to_dict())
            else:
                data['branches'].append(b)
        return data
    
@dataclass
class FeatureBranch:
    feature: FeatureDefinition
    path: str

    def get_path_snake(self):
        return "_".join((self.path).split(' '))

    def to_dict(self):
        data = dict(self.__dict__)
        data['feature'] = self.feature.name
        return data
    
@dataclass
class BranchMap:
    branch: FeatureBranch
    test_id: str
    section_index: int
    ref_mode: str

    def to_dict(self):
        data = dict(self.__dict__)
        data['branch'] = self.branch.to_dict()
        return data
    
@dataclass
class FeatureMap:
    feature: FeatureDefinition
    test_id: str
    section_index: int
    ref_mode: str
    branches: Optional[list[BranchMap]] = field(default_factory=list)

    def to_dict(self):
        data = dict(self.__dict__)
        data['branches'] = []
        for b in self.branches:
            data['branches'].append(b.to_dict())
        return data
    
@dataclass
class FeatureTestMapItem:
    test_id_path: str
    section_index: int
    ref_mode:str
    feature: str
    branch: str
    
@dataclass
class FeatureTestMap:
    feature_name: str
    maps: list[FeatureTestMapItem] = field(default_factory=list)

@dataclass
class TestFeatureMap:
    test_id_path: str
    maps: list[FeatureTestMapItem] = field(default_factory=list)

        
class CustomObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'to_dict') and callable(obj.to_dict):
            return obj.to_dict()
        # Let the base class default method raise the TypeError for other types
        try:
            data = json.JSONEncoder.default(self, obj)
        except TypeError:
            data = json.JSONEncoder.default(self, obj.__dict__)
        return data
   
class FeatureRegistry:
    
    def __init__(self):
        self.features = dict()
        self.logger = logging.getLogger("FeatureRegistry")
        self.feature_db = FeatureDB()
        self.feature_db.reload_features_from_db(self)

    @classmethod
    def get_registry(cls):
        global registry
        if not registry:
            registry = cls()
        return registry
    
    def get_raft_feature(self, name, branch_path):
        # API
        feat = self.features.get(name, None)
        if not feat:
            feat = self.add_feature(name)
        # We want to return a tuned feature definition, one that only has the requested branch elements.
        branch = feat.branches.get(branch_path)
        if branch is None:
            branch = self.add_feature_branch(feat, branch_path)
        f_copy = deepcopy(feat)
        f_copy.target_branch = deepcopy(branch)
        return f_copy

    def add_test_to_feature(self, feature, mode, test_name, test_path, section):
        self.feature_db.save_test_feature(feature, mode, test_name, test_path, section)
        
    def add_feature(self, name, skip_db_op=False):
        feat = FeatureDefinition(name=name)
        self.features[name] = feat
        if not skip_db_op:
            self.feature_db.add_feature(feat)
        self.build_feature_file(feat)
        self.logger.debug("created feature definition for %s", name)
        return feat
    
    def add_feature_branch(self, feature, branch_path, skip_db_op=False):
        cur_path = []
        full_path = branch_path.split('.')
        for branch_name in full_path:
            cur_path.append(branch_name)
            cur_id = ".".join(cur_path)
            if len(full_path) > len(cur_path) and cur_id not in feature.branches:
                self.add_feature_branch(feature, cur_id, skip_db_op)
        branch = FeatureBranch(feature, cur_id)
        feature.branches[cur_id] = branch
        self.build_feature_branch_file(branch)
        if not skip_db_op:
            self.feature_db.add_feature_branch(branch)
        self.logger.debug("created feature branch definition for %s->%s", feature.name, branch_path)
        return branch
    
    def build_feature_file(self, feature):
        dir_path = Path(files_root, feature.get_name_snake())
        if not dir_path.exists():
            dir_path.mkdir(parents=True)
        rst_path = Path(dir_path, "narative.rst")
        if not rst_path.exists():
            with open(rst_path, 'w') as f:
                f.write(f":orphan:\n\n")
                f.write(" **TBD**\n")
        short_path = Path(dir_path, "short.rst")
        if not short_path.exists():
            with open(short_path, 'w') as f:
                f.write(f":orphan:\n\n")
                f.write(" **TBD**\n")
        features_path = Path(dir_path, "features.rst")
        if not features_path.exists():
            with open(features_path, 'w') as f:
                f.write(f":orphan:\n\n")
                f.write("* **section short desc**: section x.y.z\n")
                f.write("* **like next line**: section x.y.z\n")
                f.write("* **log replication**: section 3.5\n")
        return dir_path
    
    def build_feature_branch_file(self, branch):
        f_dir_path = self.build_feature_file(branch.feature)
        dir_path = Path(f_dir_path, "branches")
        if not dir_path.exists():
            dir_path.mkdir()
        branch_path = Path(dir_path, branch.get_path_snake())
        if not branch_path.exists():
            branch_path.mkdir()
        nar_path = Path(branch_path, "narative.rst")
        if not nar_path.exists():
            with open(nar_path, 'w') as f:
                f.write(f":orphan:\n\n")
                line = f"{branch.feature.get_name_snake()}.{branch.get_path_snake()}"
                line_len = len(line)
                f.write(line + "\n")
                f.write("-"*line_len + "\n")
                f.write("\n\n**TBD**\n")
        short_path = Path(branch_path, "short.rst")
        if not short_path.exists():
            with open(short_path, 'w') as f:
                f.write(f":orphan:\n\n")
                f.write(" **TBD**\n")
        features_path = Path(branch_path, "features.rst")
        if not features_path.exists():
            with open(features_path, 'w') as f:
                f.write(f":orphan:\n\n")
                f.write("* **section short desc**: section x.y.z\n")
                f.write("* **like next line**: section x.y.z\n")
                f.write("* **log replication**: section 3.5\n")
        return branch_path

    def get_feature_to_test_maps(self):
        f_map_data = self.feature_db.get_branch_maps()
        res = []
        by_feature = {}
        for item in f_map_data:
            feature_name = item['feature']['name']
            ftm = by_feature.get(feature_name, None)
            if ftm is None:
                ftm = FeatureTestMap(feature_name)
                res.append(ftm)
                by_feature[feature_name] = ftm
            ftmi = FeatureTestMapItem(test_id_path=item['test']['id_path'],
                                      section_index=item['test_section']['section_index'],
                                      ref_mode=item['fbmap']['relationship'],
                                      feature=item['feature']['name'],
                                      branch=item['feature_branch']['path'])
            ftm.maps.append(ftmi)
        return res

    def get_test_to_feature_maps(self):
        f_map_data = self.feature_db.get_branch_maps(order='test')
        res = []
        by_test = {}
        for item in f_map_data:
            test_path = item['test']['id_path']
            tfm = by_test.get(test_path, None)
            if tfm is None:
                tfm = TestFeatureMap(test_path)
                by_test[test_path] = tfm
                res.append(tfm)
            ftmi = FeatureTestMapItem(test_id_path=item['test']['id_path'],
                                      section_index=item['test_section']['section_index'],
                                      ref_mode=item['fbmap']['relationship'],
                                      feature=item['feature']['name'],
                                      branch=item['feature_branch']['path'])
            tfm.maps.append(ftmi)
        return res

    def save_maps(self, filepath):
        dump_data = dict(test_to_feature=self.get_test_to_feature_maps(),
                         feature_to_test=self.get_feature_to_test_maps())
        with open(filepath, 'w') as f:
            f.write(json.dumps(dump_data, default=lambda o:o.__dict__, indent=2))

        

    
    
