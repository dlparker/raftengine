from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional
from copy import deepcopy
import sqlite3
import logging
from pathlib import Path
features_loaded = False
features_obj = None

registry = None
files_root = Path(Path(__file__).parent, 'feature_docs')
                 
def bool_converter(value):
    return bool(int(value))

@dataclass
class FeatureDefinition:
    name: str
    target_branch: Optional['FeatureBranch'] = None
    branches: Optional[dict['FeatureBranch']] = field(default_factory=dict)

    def get_name_snake(self):
        return "_".join((self.name).split(' '))
    
@dataclass
class FeatureBranch:
    feature: FeatureDefinition
    path: str
    parent: Optional['FeatureBranch'] = None
    children: Optional[dict['FeatureBranch']] = field(default_factory=dict)

    def get_path_snake(self):
        return "_".join((self.path).split(' '))
    
class FeatureRegistry:
    
    def __init__(self, db_path=None):
        self.features = dict()
        self.logger = logging.getLogger("FeatureRegistry")
        if db_path is None:
            self.db = None
            return
        self.db_path = Path(db_path)
        sqlite3.register_converter('BOOLEAN', bool_converter)
        self.db = sqlite3.connect(self.db_path,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row
        self.ensure_tables()
        self.reload_from_db()

    def get_raft_feature(self, name, branch_path=None):
        # API
        feat = self.features.get(name, None)
        if not feat:
            feat = self.add_feature(name)
        # We want to return a tuned feature definition, one that only has the requested branch elements.
        branch = None
        if branch_path is not None and branch_path not in feat.branches:
            branch = self.add_feature_branch(feat, branch_path)
        f_copy = deepcopy(feat)
        f_copy.target_branch = deepcopy(branch)
        return f_copy

    def add_test_to_feature(self, feature, mode, test_name, test_path, subtest=None):
        # API
        self.db_save_test_feature(feature, mode, test_name, test_path, subtest=None)
        
    def add_feature(self, name):
        feat = FeatureDefinition(name=name)
        self.features[name] = feat
        self.db_add_feature(feat)
        self.build_feature_file(feat)
        self.logger.debug("created feature definition for %s", name)
        return feat
    
    def add_feature_branch(self, feature, branch_path):
        cur_path = []
        full_path = branch_path.split('.')
        for branch_name in full_path:
            cur_path.append(branch_name)
            cur_id = ".".join(cur_path)
            if len(full_path) > len(cur_path) and cur_id not in feature.branches:
                self.add_feature_branch(feature, cur_id)
        if len(full_path) > 1:
            par_id = ".".join(full_path[:-1])
            parent = feature.branches[par_id]
        else:
            parent = None
        branch = FeatureBranch(feature, cur_id,  parent)
        feature.branches[cur_id] = branch
        self.build_feature_branch_file(branch)
        self.db_add_feature_branch(branch)
        self.logger.debug("created feature branch definition for %s->%s", feature.name, branch_path)
        return branch
    
    def build_feature_file(self, feature):
        dir_path = Path(files_root, "docs", feature.get_name_snake())
        if not dir_path.exists():
            dir_path.mkdir(parents=True)
        org_path = Path(dir_path, feature.get_name_snake() + "_narative.org")
        if not org_path.exists():
            with open(org_path, 'w') as f:
                f.write(" *TBD*\n")
        rst_path = Path(dir_path, feature.get_name_snake() + "_narative.rst")
        if not rst_path.exists():
            with open(rst_path, 'w') as f:
                f.write(f".. {feature.get_name_snake()}:\n\n")
                f.write(" **TBD**\n")
        return dir_path
    
    def build_feature_branch_file(self, branch):
        f_dir_path = self.build_feature_file(branch.feature)
        dir_path = Path(f_dir_path, "branches")
        if not dir_path.exists():
            dir_path.mkdir()
        org_path = Path(dir_path, branch.get_path_snake() + "_narative.org")
        if not org_path.exists():
            with open(org_path, 'w') as f:
                f.write(" *TBD*\n")
        rst_path = Path(dir_path, branch.get_path_snake() + "_narative.rst")
        if not rst_path.exists():
            with open(rst_path, 'w') as f:
                f.write(f".. {branch.feature.get_name_snake()}.{branch.get_path_snake()}:\n\n")
                f.write(" **TBD**\n")
        return dir_path
        
    def db_add_feature(self, feature):
        cursor = self.db.cursor()
        sql = "insert into features (name) values (?)"
        params = [feature.name, ]
        cursor.execute(sql, params)
        self.db.commit()
        cursor.close()

    def db_add_feature_branch(self, feature_branch):
        cursor = self.db.cursor()
        sql = "select feature_id from features where name = ?"
        cursor.execute(sql, [feature_branch.feature.name,])
        row = cursor.fetchone()
        feature_id = row[0]
        parent_id = None
        if feature_branch.parent is not None:
            sql = "select branch_id from feature_branches where path = ?"
            params = [feature_branch.parent.path,]
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                parent_id = row[0]
        sql = "insert into feature_branches (path, feature_id, parent_branch_id) values (?, ?, ?)"
        params = [feature_branch.path, feature_id, parent_id]
        cursor.execute(sql, params)
        self.db.commit()
        cursor.close()

    def reload_from_db(self):
        cursor = self.db.cursor()
        cursor2 = self.db.cursor()
        cursor3 = self.db.cursor()
        sql = "select * from features"

        # this code depends on reading things in the right order
        # so that a branch that has a parent will always be read
        # after the parent has been read, so it will already
        # be present in memory
        cursor.execute(sql)
        for row in cursor.fetchall():
            feat = FeatureDefinition(name=row['name'])
            self.features[feat.name] = feat
            sql2 = "select * from feature_branches where feature_id = ? order by branch_id"
            cursor2.execute(sql2, [row['feature_id'],])
            for row in cursor2.fetchall():
                path = row['path']
                if row['parent_branch_id'] is None:
                    parent = None
                else:
                    sql3 = "select * from feature_branches where branch_id = ?"
                    cursor3.execute(sql3, [row['parent_branch_id'],])
                    row = cursor3.fetchone()
                    parent = feat.branches[row['path']] 
                feat.branches[path] = FeatureBranch(feat, path, parent)
        
    def db_save_test_feature(self, feature, mode, test_name, test_path, subtest=None):
        cursor = self.db.cursor()
        sql = "select feature_id from features where name = ?"
        cursor.execute(sql, [feature.name,])
        row = cursor.fetchone()
        feature_id = row[0]
        test_id_path = test_path.split('/')[-1] + "." + test_name
        sql =  "select test_id from tests where test_id_path = ?"
        cursor.execute(sql, [test_id_path,])
        row = cursor.fetchone()
        if row:
            test_id = row[0]
        else:
            sql = "insert into tests (test_id_path) values (?)"
            cursor.execute(sql, [test_id_path,])
            test_id = cursor.lastrowid
        if mode.startswith('use'):
            rel = "uses"
        elif mode.startswith('tes'):
            rel = "tests"
        else:
            raise Exception(f'cannot translate "{mode}"')
        sql = "insert or replace into feature_test_mappings (feature_id, test_id, relationship) values (?,?,?)"
        cursor.execute(sql, [feature_id, test_id, mode])

        if feature.target_branch:
            sql = "select branch_id from feature_branches where path = ?"
            cursor.execute(sql, [feature.target_branch.path,])
            row = cursor.fetchone()
            branch_id = row[0]
            sql = "insert or replace into branch_test_mappings (branch_id, test_id, relationship) values (?,?,?)"
            cursor.execute(sql, [branch_id, test_id, mode])
        self.db.commit()
        cursor.close()
        
    def ensure_tables(self):
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS features (
                feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_branches (
                branch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                feature_id INTEGER NOT NULL,
                parent_branch_id INTEGER NULL,
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (parent_branch_id) REFERENCES feature_branches(parent_branch_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id_path TEXT UNIQUE NOT NULL  -- e.g., test_elections_1.test_pre_vote_reject_1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_test_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                relationship TEXT NOT NULL CHECK (relationship IN ('tests', 'uses')),
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (test_id) REFERENCES tests(test_id),
                UNIQUE (feature_id, test_id, relationship)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branch_test_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                relationship TEXT NOT NULL CHECK (relationship IN ('tests', 'uses')),
                FOREIGN KEY (branch_id) REFERENCES branches(branch_id),
                FOREIGN KEY (test_id) REFERENCES tests(test_id),
                UNIQUE (branch_id, test_id, relationship)
            )
        """)
        self.db.commit()
        cursor.close()

        
if not registry:
    registry = FeatureRegistry(db_path=Path(files_root, "feature.db"))


    
    
