import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, field
import datetime

def adapt_date_iso(val):
    """Adapt datetime.date to ISO 8601 date."""
    return val.isoformat()

def adapt_datetime_iso(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat()

def adapt_datetime_epoch(val):
    """Adapt datetime.datetime to Unix timestamp."""
    return int(val.timestamp())

sqlite3.register_adapter(datetime.date, adapt_date_iso)
sqlite3.register_adapter(datetime.datetime, adapt_datetime_iso)
sqlite3.register_adapter(datetime.datetime, adapt_datetime_epoch)

def convert_date(val):
    """Convert ISO 8601 date to datetime.date object."""
    return datetime.date.fromisoformat(val.decode())

def convert_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.datetime.fromisoformat(val.decode())

def convert_timestamp(val):
    """Convert Unix epoch timestamp to datetime.datetime object."""
    return datetime.datetime.fromtimestamp(int(val))

sqlite3.register_converter("date", convert_date)
sqlite3.register_converter("datetime", convert_datetime)
sqlite3.register_converter("timestamp", convert_timestamp)

def bool_converter(value):
    return bool(int(value))
sqlite3.register_converter('BOOLEAN', bool_converter)

@dataclass
class Item:
    item_id: int
    name: str
    description:str
    category:str
    starting_bid:float
    reserve_price:float
    seller_id: int
    
@dataclass
class Person:
    person_id: int
    role:str
    name:str
    address:str
    email:str
    phone:str

@dataclass
class Sale:
    item_id: int
    name: str
    description:str
    category:str
    sale_price:float
    seller_id: int
    buyer_id: int

@dataclass
class Bid:
    item_id: int
    bidder_id: int
    bid_amount:float
    bid_id: int = field(default=None)
    bidtime: datetime.datetime = field(default=None)
    time_str: str = field(default=None)
    
    def __post_init__(self):
        if self.bidtime:
            self.time_str = self.bidtime.strftime("%c")

class Records:
    
    def __init__(self, base_dir, clear=False):
        self.db_path = Path(base_dir, 'auction.db')
        if self.db_path.exists() and clear:
            self.db_path.unlink()
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
        c.execute('''CREATE TABLE if not exists sales
        (item_id INTEGER PRIMARY KEY, name TEXT, description TEXT, category TEXT, sale_price REAL, seller_id INTEGER, buyer_id INTEGER)''')
        c.execute('''CREATE TABLE if not exists bids
        (bid_id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, bidder_id INTEGER, bid_amount REAL, bidtime datetime)''')
        self.db.commit()

    def add_item(self, item:Item):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (item.item_id, item.name, item.description,
                        item.category, item.starting_bid,
                        item.reserve_price, item.seller_id))
        
        self.db.commit()
        cursor.close()
        return self.get_item(item.item_id)

    def get_item(self, item_id):
        cursor = self.db.cursor()
        cursor.execute("select * from items where item_id = ?", [item_id,])
        row = cursor.fetchone()
        cursor.close()
        return Item(**row)

    def delete_item(self, item):
        cursor = self.db.cursor()
        cursor.execute("delete from items where item_id = ?", [item.item_id,])
        cursor.close()

    def get_random_item(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM items ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        return Item(**row)
        
    def add_person(self, person):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO people VALUES (?, ?, ?, ?, ?, ?)",
                       (person.person_id, person.role, person.name, 
                        person.address, person.email,
                        person.phone))
        
        self.db.commit()
        cursor.close()
        return self.get_person(person.person_id)

    def get_person(self, person_id):
        cursor = self.db.cursor()
        cursor.execute("select * from people where person_id = ?", [person_id,])
        row = cursor.fetchone()
        cursor.close()
        return Person(**row)

    def add_sale(self, item, price, buyer_id):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (item.item_id, item.name, item.description,
                        item.category, price,
                        item.seller_id, buyer_id))
        self.db.commit()
        cursor.close()
        return self.get_sale(item.item_id)

    def get_sale(self, item_id):
        cursor = self.db.cursor()
        cursor.execute("select * from sales where item_id = ?", [item_id,])
        row = cursor.fetchone()
        cursor.close()
        return Sale(**row)

    def add_bid(self, item, bidder_id, bid_amount):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO bids (item_id, bidder_id, bid_amount, bidtime) VALUES (?, ?, ?, ?)",
                       (item.item_id, bidder_id, bid_amount, datetime.datetime.now().isoformat()))
        self.db.commit()
        bid_id = cursor.lastrowid
        cursor.close()
        return self.get_bid(bid_id)

    def get_bid(self, bid_id):
        cursor = self.db.cursor()
        cursor.execute("select * from bids where bid_id = ?", [bid_id,])
        row = cursor.fetchone()
        cursor.close()
        return Bid(**row)

    def get_bids_for_sale(self, sale):
        cursor = self.db.cursor()
        cursor.execute("select * from bids where item_id = ? order by bidtime", [sale.item_id,])
        res = []
        for row in cursor.fetchall():
            res.append(Bid(**row))
        cursor.close()
        return res

    def fetch_items(self, offset: int, limit: int) -> List[Item]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM items LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        cursor.close()
        return [Item(**row) for row in rows]

    def fetch_people(self, offset: int, limit: int) -> List[Person]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM people LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        cursor.close()
        return [Person(**row) for row in rows]

    def fetch_sales(self, offset: int, limit: int) -> List[Sale]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM sales LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        cursor.close()
        return [Sale(**row) for row in rows]

    def fetch_bids(self, offset: int, limit: int) -> List[Bid]:
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM bids LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        cursor.close()
        return [Bid(**row) for row in rows]

    def count_rows(self, table: str) -> int:
        cursor = self.db.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    def get_sales_for_person(self, person_id: int) -> List[Sale]:
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT * FROM sales WHERE seller_id = ? OR buyer_id = ?",
            (person_id, person_id)
        )
        rows = cursor.fetchall()
        cursor.close()
        return [Sale(**row) for row in rows]

    def close(self):
        self.db.close()
        self.db = None
