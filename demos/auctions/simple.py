#!/usr/bin/env python
import random
from pathlib import Path
from records import Records
import itertools
from pprint import pprint
from generators import generate_item, generate_person
from bidding import Bidder, simulate_auction
from records import Person, Item, Bid, Sale

base_dir = Path(__file__).parent
records = Records(base_dir, clear=True)

items = [generate_item(i) for i in range(5)]

max_bidders = 5
max_sellers = 5
bidder_people = [generate_person(i, 'bidder') for i in range(max_bidders)]
sellers = [generate_person(i + len(bidder_people), 'seller') for i in range(max_sellers)]
deques = [bidder_people, sellers]
for person in itertools.chain(*deques):
    p = records.add_person(person)
    pprint(p)
    

bidders = []
for bp in bidder_people:
    bidders.append(Bidder(bp.person_id, bp, budget=random.uniform(500, 5000), aggression=random.uniform(0.2, 0.8)))

for item in items:
    seller = random.choice(sellers)
    item.seller_id  = seller.person_id
    it = records.add_item(item)
    pprint(it)

focus_item = records.get_random_item()
    
for item in items:
    bids, winner, final_bid  = simulate_auction(records, item, bidders)
    records.create_and_save_sale(item, final_bid, winner)
    # we delete the item from items table, that is only things not yet sold
    records.delete_item(item)


sale = records.get_sale(focus_item.item_id)
seller = records.get_person(sale.seller_id)
buyer = records.get_person(sale.buyer_id)
bids = records.get_bids_for_sale(sale)

print("Seller:")
pprint(seller)
print("Item:")
pprint(focus_item)
print("Buyer:")
pprint(buyer)
print("Bids:")
pprint(bids)

