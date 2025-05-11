#!/usr/bin/env python
import sqlite3
from pathlib import Path
import asyncio
from typing import List, Dict, Any
from nicegui import ui, app
from nicegui.events import GenericEventArguments
from records import Records, Item, Person, Sale, Bid


class UIApp():

    def __init__(self, db_dir):
        self.outer_div = None
        self.records = None
        self.db_dir = db_dir
        self.main_nav = None
        self.sale_detail_container = None
        self.person_detail_container = None

    async def start(self):
        # needs to be done in ui thread
        self.records = Records(base_dir=Path(self.db_dir), clear=False)

    async def person_detail(self, person: Dict):
        """Show sales for a person (buyer or seller)."""
        if self.person_detail_container:
            self.person_detail_container.clear()
        else:
            self.person_detail_container = ui.element('div').classes("w-full")

        person_id = person["person_id"]
        sales = self.records.get_sales_for_person(person_id)
        with self.person_detail_container:
            with ui.card().classes("w-full text-black"):
                ui.label(f"Sales for {person['name']} (ID: {person_id})").classes("text-lg font-bold")
                if sales:
                    columns = [
                        {"name": "item_id", "label": "Item ID", "field": "item_id", "sortable": True},
                        {"name": "name", "label": "Item Name", "field": "name", "sortable": True},
                        {"name": "sale_price", "label": "Sale Price", "field": "sale_price", "sortable": True},
                        {"name": "seller_id", "label": "Seller ID", "field": "seller_id", "sortable": True},
                        {"name": "buyer_id", "label": "Buyer ID", "field": "buyer_id", "sortable": True},
                        {"name": "role", "label": "Role", "field": "role", "sortable": True}
                    ]
                    table_data = [
                        {
                            **vars(sale),
                            "role": "Seller" if sale.seller_id == person_id else "Buyer"
                        }
                        for sale in sales
                    ]
                    ui.table(
                        columns=columns,
                        rows=table_data,
                        row_key="item_id",
                        title="Related Sales"
                    ).classes("w-full")
                else:
                    ui.label("No sales found.").classes("text-gray-500")

    async def sale_detail(self, sale: Dict):
        """Show details for a sale, including bidding history."""
        if self.sale_detail_container:
            self.sale_detail_container.clear()
        else:
            self.sale_detail_container = ui.element('div').classes("w-full")

        with self.sale_detail_container:
            with ui.card().classes("w-full text-black"):
                sale_obj = Sale(**sale)
                bids = self.records.get_bids_for_sale(sale_obj)
                try:
                    seller = self.records.get_person(sale["seller_id"])
                    buyer = self.records.get_person(sale["buyer_id"])
                except Exception as e:
                    ui.label(f"Error fetching person data: {e}").classes("text-red-500")
                    return

                ui.label(f"Sale: {sale['name']} (Item ID: {sale['item_id']})").classes("text-lg font-bold")
                with ui.row():
                    ui.label(f"Category: {sale['category']}")
                    ui.label(f"Sale Price: ${sale['sale_price']:.2f}")
                ui.label(f"Description: {sale['description']}")
                ui.label(f"Seller: {seller.name} (ID: {seller.person_id})")
                ui.label(f"Buyer: {buyer.name} (ID: {buyer.person_id})")

                ui.label("Bidding History").classes("text-md font-bold mt-4")
                if bids:
                    columns = [
                        {"name": "bid_id", "label": "Bid ID", "field": "bid_id", "sortable": True},
                        {"name": "bidder_name", "label": "Bidder", "field": "bidder_name", "sortable": True},
                        {"name": "bid_amount", "label": "Bid Amount", "field": "bid_amount", "sortable": True},
                        {"name": "timestamp", "label": "Time", "field": "timestamp", "sortable": True}
                    ]
                    table_data = [
                        {
                            "bid_id": bid.bid_id,
                            "bidder_name": self.records.get_person(bid.bidder_id).name,
                            "bid_amount": bid.bid_amount,
                            "timestamp": bid.time_str
                        }
                        for bid in bids
                    ]
                    ui.table(
                        columns=columns,
                        rows=table_data,
                        row_key="bid_id",
                        title="Bids"
                    ).classes("w-full")
                else:
                    ui.label("No bids found.").classes("text-gray-500")

        
class ClassListPage():
    def __init__(self, ui_app, cls):
        self.ui_app = ui_app
        self.records = ui_app.records
        self.cls = cls

    def get_item_columns(self):
        columns = [
            {"name": "item_id", "label": "Item ID", "field": "item_id", "sortable": False},
            {"name": "name", "label": "Name", "field": "name", "sortable": False},
            {"name": "description", "label": "Description", "field": "description", "sortable": False},
            {"name": "category", "label": "Category", "field": "category", "sortable": False},
            {"name": "starting_bid", "label": "Starting Bid", "field": "starting_bid", "sortable": False},
            {"name": "reserve_price", "label": "Reserve Price", "field": "reserve_price", "sortable": False},
            {"name": "seller_id", "label": "Seller ID", "field": "seller_id", "sortable": False}
        ]
        return columns
        
    def get_item_paginator(self):
        return {'rowsPerPage': 10, 'rowsNumber': self.records.count_rows("items"), 'page': 1}
        
    async def get_item_data(self, offset, rows_per_page):
        return self.records.fetch_items(offset, rows_per_page)

    def get_sale_columns(self):
        columns = [
            {"name": "item_id", "label": "Item ID", "field": "item_id", "sortable": False},
            {"name": "name", "label": "Name", "field": "name", "sortable": False},
            {"name": "description", "label": "Description", "field": "description", "sortable": False},
            {"name": "category", "label": "Category", "field": "category", "sortable": False},
            {"name": "sale_price", "label": "Sale Price", "field": "sale_price", "sortable": False},
            {"name": "seller_id", "label": "Seller ID", "field": "seller_id", "sortable": False},
            {"name": "buyer_id", "label": "Buyer ID", "field": "buyer_id", "sortable": False}
        ]
        return columns
        
    def get_sale_paginator(self):
        return {'rowsPerPage': 10, 'rowsNumber': self.records.count_rows("sales"), 'page': 1}
        
    async def get_sale_data(self, offset, rows_per_page):
        return self.records.fetch_sales(offset, rows_per_page)

    def get_person_columns(self):
        columns = [
            {"name": "person_id", "label": "Person ID", "field": "person_id", "sortable": False},
            {"name": "role", "label": "Role", "field": "role", "sortable": False},
            {"name": "name", "label": "Name", "field": "name", "sortable": False},
            {"name": "address", "label": "Address", "field": "address", "sortable": False},
            {"name": "email", "label": "Email", "field": "email", "sortable": False},
            {"name": "phone", "label": "Phone", "field": "phone", "sortable": False}
        ]
        return columns
        
    def get_person_paginator(self):
        return {'rowsPerPage': 10, 'rowsNumber': self.records.count_rows("people"), 'page': 1}
        
    async def get_person_data(self, offset, rows_per_page):
        return self.records.fetch_people(offset, rows_per_page)
    
    def get_bid_columns(self):
        columns = [
            {"name": "bid_id", "label": "Bid ID", "field": "bid_id", "sortable": False},
            {"name": "item_id", "label": "Item ID", "field": "item_id", "sortable": False},
            {"name": "bidder_id", "label": "Bidder ID", "field": "bidder_id", "sortable": False},
            {"name": "bid_amount", "label": "Bid Amount", "field": "bid_amount", "sortable": False},
            {"name": "timestamp", "label": "Time", "field": "time_str", "sortable": False}
        ]
        return columns

    def get_bid_paginator(self):
        return {'rowsPerPage': 10, 'rowsNumber': self.records.count_rows("bids"), 'page': 1}
        
    async def get_bid_data(self, offset, rows_per_page):
        return self.records.fetch_bids(offset, rows_per_page)
        
    async def setup_page(self):
        if self.cls == Item:
            columns = self.get_item_columns()
            pagination = self.get_item_paginator()
            row_getter = self.get_item_data
            row_key = "item_id"
        elif self.cls == Person:
            columns = self.get_person_columns()
            pagination = self.get_person_paginator()
            row_getter = self.get_person_data
            row_key = "person_id"
        elif self.cls == Sale:
            columns = self.get_sale_columns()
            pagination = self.get_sale_paginator()
            row_getter = self.get_sale_data
            row_key = "item_id"
        elif self.cls == Bid:
            columns = self.get_bid_columns()
            pagination = self.get_bid_paginator()
            row_getter = self.get_bid_data
            row_key = "bid_id"
        else:
            raise Exception(f"not implemented for class {self.cls}")
        
        async def get_rows():
            nonlocal pagination
            page = pagination['page']
            rows_per_page = pagination['rowsPerPage']
            offset = (page - 1) * rows_per_page
            rows = await row_getter(offset, rows_per_page)
            return rows
        
        async def on_request(e: GenericEventArguments) -> None:
            nonlocal pagination
            pagination = e.args['pagination']
            rows = await get_rows()
            table.pagination.update(pagination)
            table.update_rows(rows)

        if self.cls == Person:
            selection="single"
            on_select=lambda e: self.ui_app.person_detail(e.selection[0])
        elif self.cls == Sale:
            selection="single"
            on_select=lambda e: self.ui_app.sale_detail(e.selection[0])
        else:
            selection=None
            on_select=None
        table = ui.table(columns=columns, rows=await get_rows(),
                         row_key=row_key, selection=selection, on_select=on_select,
                         pagination=pagination).classes("w-full")
        table.on('request', on_request)
        

async def startup_spa():
    global ui_app
    await ui_app.start()
    """Run the NiceGUI app."""
    ui.colors(primary="#007bff")

    with ui.header().classes("bg-primary text-white"):
        ui.label("Auction Database Viewer").classes("text-2xl")

    with ui.tabs().classes("w-full") as tabs:
        sales_tab = ui.tab("Sales")
        people_tab = ui.tab("People")
        items_tab = ui.tab("Items")
        bids_tab = ui.tab("Bids")
        
    with ui.tab_panels(tabs, value=sales_tab).classes("w-full"):
        with ui.tab_panel(sales_tab):
            sales_page = ClassListPage(ui_app, Sale)
            await sales_page.setup_page()
            
        with ui.tab_panel(people_tab):
            people_page = ClassListPage(ui_app, Person)
            await people_page.setup_page()

        with ui.tab_panel(bids_tab):
            bid_page = ClassListPage(ui_app, Bid)
            await bid_page.setup_page()
            
        with ui.tab_panel(items_tab):
            item_page = ClassListPage(ui_app, Item)
            await item_page.setup_page()
                
async def startup_pages():
    global ui_app
    await ui_app.start()

    @ui.page('/items')
    async def home():
        global ui_app
        page = ClassListPage(ui_app, Item)
        await page.setup_page()

    @ui.page('/people')
    async def home():
        global ui_app
        page = ClassListPage(ui_app, Person)
        await page.setup_page()

    @ui.page('/sales')
    async def home():
        global ui_app
        page = ClassListPage(ui_app, Sale)
        await page.setup_page()

    @ui.page('/bids')
    async def bids():
        global ui_app
        page = ClassListPage(ui_app, Bid)
        await page.setup_page()
        
if __name__ in ("__main__", "__mp_main__"):
    db_dir = Path(__file__).parent
    ui_app = UIApp(db_dir=db_dir)
    app.on_startup(startup_spa)
    ui.run() 
