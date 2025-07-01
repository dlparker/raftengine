from pathlib import Path
import sqlite3
import logging

def bool_converter(value):
    return bool(int(value))

class FeatureDB:

    def __init__(self):
        dirpath = Path(Path(__file__).parent.parent, 'captures', "features")
        if not dirpath.exists():
            dirpath.mkdir(parents=True)
        self.db_path = Path(dirpath, "features.db")
        self.logger = logging.getLogger("features_db")
        ppath = self.db_path.parent
        if not ppath.exists():
            ppath.mkdir(parents=True)
        sqlite3.register_converter('BOOLEAN', bool_converter)
        self.db = sqlite3.connect(self.db_path,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row
        self.ensure_tables()

    def close(self):
        self.db.close()

    def record_test(self, test_name, test_path, description, doc_string, sections):
        cursor = self.db.cursor()
        id_path =  Path(test_path).stem + "." + test_name
        sql = "select test_id from tests where id_path = ?"
        cursor.execute(sql, [id_path,])
        row = cursor.fetchone()
        if row:
            tid = row['test_id']
            sql = "update tests set name = ?, path = ?, description = ?, doc_string = ? where test_id = ?"
            values = [test_name, test_path, description, doc_string, tid]
            cursor.execute(sql, values)
        else:
            sql = "insert into tests (name, path, id_path, description, doc_string) values (?,?,?,?,?)"
            values = [test_name, test_path, id_path, description, doc_string]
            cursor.execute(sql, values)
            tid = cursor.lastrowid
        
        for section in sections:
            sql = "select section_id from test_sections where test_id = ? and section_index = ?"
            cursor.execute(sql, [tid, section.index,])
            row = cursor.fetchone()
            if row is None:
                sql = "insert into test_sections (test_id, section_index, description, is_prep) values (?,?,?,?)"
                values = [tid, section.index, section.description, section.is_prep]
                cursor.execute(sql, values)
            else:
                sql = "update test_sections set description = ?, is_prep = ? where section_id = ?"
                values = [section.description, section.is_prep, row['section_id']]
                cursor.execute(sql, values)
        self.db.commit()

    def get_test_records(self):
        cursor = self.db.cursor()
        sel = "select * from tests"
        cursor.execute(sel)
        res = []
        for row in cursor.fetchall():
            res.append(dict(row))
        cursor.close()
        return res
    
    def get_test_section_records(self, test_path, test_name):
        cursor = self.db.cursor()
        id_path =  Path(test_path).stem + "." + test_name
        sql = "select test_id from tests where id_path = ?"
        cursor.execute(sql, [id_path,])
        row = cursor.fetchone()
        if row is None:
            raise Exception(f"no record of {test_id_path}")
        tid = row[0]
        sql = "select * from test_sections where test_id = ? order by section_index"
        cursor.execute(sql, [tid,])
        res = []
        for row in cursor.fetchall():
            res.append(dict(row))
        cursor.close()
        return res
    
    def record_test_section(self, test_name, test_path, section):
        cursor = self.db.cursor()
        id_path =  Path(test_path).stem + "." + test_name
        sql = "select test_id from tests where id_path = ?"
        cursor.execute(sql, [id_path,])
        row = cursor.fetchone()
        if row is None:
            raise Exception(f"no record of {id_path}")
        tid = row[0]
        sql = "select section_id from test_sections where test_id = ? and section_index = ?"
        cursor.execute(sql, [tid, section.index,])
        row = cursor.fetchone()
        if row is None:
            sql = "insert into test_sections (test_id, section_index, description, is_prep) values (?,?,?,?)"
            values = [tid, section.index, section.description, section.is_prep]
            cursor.execute(sql, values)
        else:
            sql = "update test_sections set description = ?, is_prep = ? where section_id = ?"
            values = [section.description, section.is_prep, row['section_id']]
            cursor.execute(sql, values)
        self.db.commit()
        
    def save_test_feature(self, feature, mode, test_name, test_path, section):
        cursor = self.db.cursor()
        test_id_path = Path(test_path).stem + "." + test_name
        sql =  "select test_id from tests where id_path = ?"
        cursor.execute(sql, [test_id_path,])
        row = cursor.fetchone()
        if not row:
            raise Exception('save test and test section before trying to save feature')
        test_id = row[0]
        sql =  "select section_id from test_sections where test_id = ? and description = ?"
        cursor.execute(sql, [test_id, section.description])
        row = cursor.fetchone()
        if not row:
            raise Exception('save test and test section before trying to save feature')
        section_id = row[0]

        sql = "select feature_id from features where name = ?"
        cursor.execute(sql, [feature.name,])
        row = cursor.fetchone()
        feature_id = row[0]

        if mode.startswith('use'):
            rel = "uses"
        elif mode.startswith('tes'):
            rel = "tests"
        else:
            raise Exception(f'cannot translate "{mode}"')
        sql = "select mapping_id from feature_test_mappings where feature_id = ? and test_id = ? and section_id = ?"
        cursor.execute(sql, [feature_id, test_id, section_id])
        if cursor.fetchone() is None:
            sql = "insert into feature_test_mappings"
            sql += " (feature_id, test_id, section_id, relationship, path, test_id_path, section_index) values (?,?,?,?,?,?,?)"
            cursor.execute(sql, [feature_id, test_id, section_id, mode, feature.name, test_id_path, section.index])

        if feature.target_branch:
            sql = "select branch_id from feature_branches where path = ?"
            cursor.execute(sql, [feature.target_branch.path])
            row = cursor.fetchone()
            branch_id = row[0]
            sql = "select mapping_id from branch_test_mappings where branch_id = ? and test_id = ? and section_id = ?"
            cursor.execute(sql, [branch_id, test_id, section_id])
            if cursor.fetchone() is None:
                sql =  "insert into branch_test_mappings "
                sql += " (feature_id, branch_id, path, test_id, section_id, relationship, test_id_path, section_index) "
                sql += " values (?, ?,?,?,?,?,?,?)"
                
                cursor.execute(sql, [feature_id, branch_id, feature.name + "." + feature.target_branch.path, test_id, section_id,
                                     mode, test_id_path, section.index])
        self.db.commit()
        cursor.close()
        
    def add_feature(self, feature):
        cursor = self.db.cursor()
        sql = "insert into features (name) values (?)"
        params = [feature.name, ]
        cursor.execute(sql, params)
        self.db.commit()
        cursor.close()

    def add_feature_branch(self, feature_branch):
        cursor = self.db.cursor()
        sql = "select feature_id from features where name = ?"
        cursor.execute(sql, [feature_branch.feature.name,])
        row = cursor.fetchone()
        feature_id = row[0]
        sql = "insert into feature_branches (path, feature_id) values (?, ?)"
        params = [feature_branch.path, feature_id]
        cursor.execute(sql, params)
        self.db.commit()
        cursor.close()

    def reload_features_from_db(self, registry):
        cursor = self.db.cursor()
        cursor2 = self.db.cursor()
        sql = "select * from features"

        cursor.execute(sql)
        for row in cursor.fetchall():
            feature = registry.add_feature(row['name'], skip_db_op=True)
            sql2 = "select * from feature_branches where feature_id = ? order by branch_id"
            cursor2.execute(sql2, [row['feature_id'],])
            for row in cursor2.fetchall():
                path = row['path']
                registry.add_feature_branch(feature, path, skip_db_op=True)

    def get_branch_maps(self, order="feature"):
        cursor = self.db.cursor()
        if order == "feature":
            sel = "select * from branch_test_mappings order by feature_id,branch_id"
        elif order == "test":
            sel = "select * from branch_test_mappings order by test_id desc,relationship,section_id"
        else:
            raise Exception(f'invalid order spec {order}')
        res = []
        cursor.execute(sel)
        cursor2 = self.db.cursor()
        for row in cursor.fetchall():
            item = dict(fbmap=dict(row))
            res.append(item)
            sel2 = 'select * from features where feature_id = ?'
            feature_id = row['feature_id']
            cursor2.execute(sel2, [feature_id,])
            frow = cursor2.fetchone()
            if not frow:
                raise Exception(f'db problem, branch map contains feature_id = {feature_id} not found in features table')
            item['feature'] = dict(frow)

            sel3 = 'select * from feature_branches where branch_id = ?'
            branch_id = row['branch_id']
            cursor2.execute(sel3, [branch_id,])
            brow = cursor2.fetchone()
            if not brow:
                raise Exception(f'db problem, branch map contains branch_id = {branch_id} not found in feature_branches table')
            item['feature_branch'] = dict(brow)
            
            sel4 = 'select * from tests where test_id = ?'
            test_id = row['test_id']
            cursor2.execute(sel4, [test_id,])
            trow = cursor2.fetchone()
            if not trow:
                raise Exception(f'db problem, branch map contains test_id = {test_id} not found in tests table')
            item['test'] = dict(trow)
            
            sel5 = 'select * from test_sections where section_id = ?'
            section_id = row['section_id']
            cursor2.execute(sel5, [section_id,])
            srow = cursor2.fetchone()
            if not srow:
                raise Exception(f'db problem, branch map contains section_id = {section_id} not found in test_sections table')
            item['test_section'] = dict(srow)
        cursor.close
        return res
            
    def clear_maps(self):
        cursor = self.db.cursor()
        sql = "delete from branch_test_mappings"
        cursor.execute(sql)
        sql = "delete from feature_test_mappings"
        cursor.execute(sql)
        self.db.commit()

    def clear_tests(self):
        cursor = self.db.cursor()
        sql = "delete from test_sections"
        cursor.execute(sql)
        sql = "delete from tests"
        cursor.execute(sql)
        self.db.commit()

    def clear_features(self):
        cursor = self.db.cursor()
        sql = "delete from feature_branches"
        cursor.execute(sql)
        sql = "delete from features"
        cursor.execute(sql)
        self.db.commit()
        
        
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
                FOREIGN KEY (feature_id) REFERENCES features(feature_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                test_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,  
                path TEXT NOT NULL,  
                description TEXT,  
                doc_string TEXT,  
                id_path TEXT UNIQUE NOT NULL  -- e.g., test_elections_1.test_pre_vote_reject_1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_sections (
                section_id INTEGER PRIMARY KEY AUTOINCREMENT,
                section_index INT,
                description TEXT,  
                is_prep BOOLEAN,  
                test_id INTEGER,
                FOREIGN KEY (test_id) REFERENCES tests(test_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_test_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_id INTEGER NOT NULL,
                test_id INTEGER,
                section_id INTEGER NOT NULL,
                path TEXT,
                test_id_path TEXT,
                section_index INTEGER,
                relationship TEXT NOT NULL CHECK (relationship IN ('tests', 'uses')),
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (section_id) REFERENCES test_sections(section_id),
                FOREIGN KEY (test_id) REFERENCES tests(test_id)
                UNIQUE (feature_id, section_id, relationship)
            )
        """)

        # This table is not normalized at all because it is the
        # easiest way for a human to do a query to get the complete
        # picture of the relationships without have to write
        # complex joins, and the dataset is small and the
        # usage simple so there is no benefit in normalizing it.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branch_test_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_id INTEGER NOT NULL,
                branch_id INTEGER NOT NULL,
                path TEXT,
                test_id INTEGER,
                section_id INTEGER NOT NULL,
                test_id_path TEXT,
                section_index INTEGER,
                relationship TEXT NOT NULL CHECK (relationship IN ('tests', 'uses')),
                FOREIGN KEY (feature_id) REFERENCES features(feature_id),
                FOREIGN KEY (branch_id) REFERENCES branches(branch_id),
                FOREIGN KEY (section_id) REFERENCES test_sections(section_id),
                FOREIGN KEY (test_id) REFERENCES tests(test_id)
                UNIQUE (branch_id, section_id, relationship)
            )
        """)
        self.db.commit()
        cursor.close()

        
