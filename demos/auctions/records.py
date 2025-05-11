import sqlite3
import datetime
import shutil
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
#sqlite3.register_adapter(datetime.datetime, adapt_datetime_epoch)

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
    
    def __init__(self, base_dir, clear=False, db_file_name="auction.db"):
        self.db_path = Path(base_dir, db_file_name)
        if self.db_path.exists() and clear:
            self.db_path.unlink()
        self.db = sqlite3.connect(self.db_path,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row


        cursor = self.db.cursor()
        for command in self.get_create_commands().values():
            cursor.execute(command)
        self.db.commit()
            
    def get_create_commands(self, prefix=""):
        commands = {}
        commands['items'] = f'''CREATE TABLE if not exists {prefix}items
        (item_id INTEGER PRIMARY KEY, name TEXT, description TEXT, category TEXT, starting_bid REAL, reserve_price REAL, seller_id INTEGER)'''
        commands['people'] = f'''CREATE TABLE if not exists {prefix}people
        (person_id INTEGER PRIMARY KEY, role TEXT, name TEXT, address TEXT, email TEXT, phone TEXT)'''
        commands['sales'] = f'''CREATE TABLE if not exists {prefix}sales
        (item_id INTEGER PRIMARY KEY, name TEXT, description TEXT, category TEXT, sale_price REAL, seller_id INTEGER, buyer_id INTEGER)'''
        commands['bids'] = f'''CREATE TABLE if not exists {prefix}bids
        (bid_id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, bidder_id INTEGER, bid_amount REAL, bidtime datetime)'''
        return commands

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
        
    def get_random_sale(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM sales ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        return Sale(**row)
        
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

    def create_and_save_sale(self, item, price, buyer_id):
        sale = Sale(item.item_id, item.name, item.description, item.category,
                    price, item.seller_id, buyer_id)
        return self.add_sale(sale)
        
    def add_sale(self, sale):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (sale.item_id, sale.name, sale.description,
                        sale.category, sale.sale_price,
                        sale.seller_id, sale.buyer_id))
        self.db.commit()
        cursor.close()
        return self.get_sale(sale.item_id)

    def get_sale(self, item_id):
        cursor = self.db.cursor()
        cursor.execute("select * from sales where item_id = ?", [item_id,])
        row = cursor.fetchone()
        cursor.close()
        return Sale(**row)

    def create_and_save_bid(self, item, bidder_id, bid_amount):
        bid = Bid(item.item_id, bidder_id, bid_amount)
        return self.add_bid(bid)
        
    def add_bid(self, bid):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO bids (item_id, bidder_id, bid_amount, bidtime) VALUES (?, ?, ?, ?)",
                       (bid.item_id, bid.bidder_id, bid.bid_amount, datetime.datetime.now()))
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
        if table not in ('people', 'sales', 'items', 'bids'):
            raise Exception(f'illegal table name {table}')
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

    def take_snapshot(self):
        cursor = self.db.cursor()
        cursor.execute("BEGIN TRANSACTION")
        commands = self.get_create_commands(prefix="snap_")
        for table in ('people', 'sales', 'items', 'bids'):
            cursor.execute(f"drop table if exists snap_{table}")
            cursor.execute(commands[table])
            cursor.execute(f"insert into snap_{table} select * from {table}")
        cursor.execute("COMMIT")
        self.db.commit()
        snap_db_file = Path(self.db_path.parent, 'auction.snap_copy.db')
        copy_path = Path(snap_db_file)
        if copy_path.exists():
            copy_path.unlink()
        shutil.copy(self.db_path, copy_path)
        copy_records = Records(copy_path.parent, clear=True, db_file_name=copy_path.parts[-1])
        cursor.execute("SELECT * FROM snap_items")
        for row in  cursor.fetchall():
            item = Item(**row)
            copy_records.add_item(item)
        cursor.execute("SELECT * FROM snap_people")
        for row in  cursor.fetchall():
            person = Person(**row)
            copy_records.add_person(person)
        cursor.execute("SELECT * FROM snap_sales")
        for row in  cursor.fetchall():
            sale = Sale(**row)
            copy_records.add_sale(sale)
        cursor.execute("SELECT * FROM snap_bids")
        for row in  cursor.fetchall():
            bid = Bid(**row)
            copy_records.add_bid(bid)
            
        for table in ('people', 'sales', 'items', 'bids'):
            cursor.execute(f"drop table if exists snap_{table}")
        self.db.commit()
        return copy_records
