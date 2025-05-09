import sqlite3
from pathlib import Path

def bool_converter(value):
    return bool(int(value))

class Catalog:
    def __init__(self, base_dir, clear=False):
        self.db_path = Path(base_dir, 'auction.db')
        if self.db_path.exists() and clear:
            self.db_path.unlink()
        sqlite3.register_converter('BOOLEAN', bool_converter)
        self.db = sqlite3.connect(self.db_path,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row

        c = self.db.cursor()

        # Create tables
        c.execute('''CREATE TABLE if not exists items
        (item_id INTEGER PRIMARY KEY, name TEXT, description TEXT, category TEXT, starting_bid REAL, reserve_price REAL, seller_id INTEGER)''')
        c.execute('''CREATE TABLE if not exists people
        (person_id INTEGER PRIMARY KEY, role TEXT, name TEXT, address TEXT, email TEXT, phone TEXT)''')
        self.db.commit()

    def add_item(self, item):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (item['item_id'], item['name'], item['description'],
                        item['category'], item['starting_bid'],
                        item['reserve_price'], item['seller_id']))
        
        self.db.commit()
        cursor.close()

    def add_person(self, person):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO people VALUES (?, ?, ?, ?, ?, ?)",
                       (person['person_id'], person['role'], person['name'], 
                        person['address'], person['email'],
                        person['phone']))
        
        self.db.commit()
        cursor.close()

    def close(self):
        self.db.close()
        self.db = None
