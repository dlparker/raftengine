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

def bool_converter(value):
    return bool(int(value))

@dataclass
class FeatureDefinition:
    name: str
    target_branch: Optional[str] = None
    branches: Optional[dict['FeatureBranch']] = field(default_factory=dict)
    
@dataclass
class FeatureBranch:
    feature: FeatureDefinition
    path: str
    parent: Optional['FeatureBranch'] = None
    children: Optional[dict['FeatureBranch']] = field(default_factory=dict)

class FeatureRegistry:
    
    def __init__(self, db_path=None):
        self.features = dict()
        self.logger = logging.getLogger("FeatureRegistry")
        if db_path is None:
            self.db = None
            return
        self.db_path = Path(db_path)
        if self.db_path.exists():
            self.db_path.unlink()
        sqlite3.register_converter('BOOLEAN', bool_converter)
        self.db = sqlite3.connect(self.db_path,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row
        self.ensure_tables()

    def get_raft_feature(self, name, branch_path=None):
        feat = self.features.get(name, None)
        if not feat:
            feat = FeatureDefinition(name=name)
            self.features[name] = feat
            if self.db:
                self.db_add_feature(feat)
            self.logger.debug("created feature definition for %s", name)
        # We want to return a tuned feature definition, one that only has the requested branch elements.
        if branch_path is not None:
            cur_path = []
            for branch_name in branch_path.split('.'):
                cur_path.append(branch_name)
                cur_id = ".".join(cur_path)
                if cur_id not in feat.branches:
                    parent = None
                    if len(cur_path) > 1:
                        par_id = ".".join(cur_path[:-1])
                        parent = feat.branches[par_id]
                    fb = FeatureBranch(feat, cur_id,  parent)
                    feat.branches[cur_id] = fb
                    if self.db:
                        self.db_add_feature_branch(fb)
                    self.logger.debug("created feature branch definition for %s->%s", name, cur_id)
        f_copy = deepcopy(feat)
        f_copy.target_branch = branch_path
        return f_copy

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
                feature_branch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                feature_id INTEGER NOT NULL,
                parent_branch_id INTEGER NULL,
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (parent_branch_id) REFERENCES feature_branches(parent_branch_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS features_info (
                feature_info_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_id INTEGER NOT NULL,
                feature_branch_id INTEGER,
                short_description, TEXT UNIQUE NOT NULL,
                description TEXT,
                thesis_references TEXT,
                rst_page TEXT,
                org_page TEXT,
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (feature_branch_id) REFERENCES feature_branches(feature_branch_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_ref TEXT UNIQUE NOT NULL  -- e.g., test_elections_1.test_pre_vote_reject_1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_test_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                relationship TEXT NOT NULL CHECK (relationship IN ('focused', 'used')),
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (test_id) REFERENCES tests(test_id),
                UNIQUE (feature_id, test_id, relationship)
            )
        """)
        self.db.commit()
        cursor.close()

    def db_add_feature(self, feature):
        cursor = self.db.cursor()
        sql = "insert into features (name) values (?)"
        cursor.execute(sql, [feature.name, ])
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
            sql = "select feature_branch_id from feature_branches where name = ?"
            cursor.execute(sql, [feature_branch.parent.path,])
            row = cursor.fetchone()
            if row:
                parent_id = row[0]
        sql = "insert into feature_branches (name, feature_id, parent_branch_id) values (?, ?, ?)"
        cursor.execute(sql, [feature_branch.path, feature_id, parent_id])
        self.db.commit()
        cursor.close()

        
if not registry:    
    registry = FeatureRegistry(db_path=Path("/tmp/feature.db"))


    
    
