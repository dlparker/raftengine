#!/usr/bin/env python
import random
from pathlib import Path
from records import Records
from generators import generate_item, generate_person
from bidding import Bidder, simulate_auction

base_dir = Path(__file__).parent
records = Records(base_dir, clear=True)

items = [generate_item(i) for i in range(5)]

bidders = [Bidder(i, generate_person(i, 'bidder'),
                  budget=random.uniform(500, 5000),
                  aggression=random.uniform(0.2, 0.8)) for i in range(5)]
sellers = [generate_person(i + 5000, 'seller') for i in range(5)]
for bidder in bidders:
    records.add_person(bidder.person)
for seller in sellers:
    records.add_person(seller)

for item in items:
    seller = random.choice(sellers)
    item['seller_id'] = seller['person_id']
    records.add_item(item)

for item in items:
    bids, winner, final_bid  = simulate_auction(item, bidders)
    records.add_sale(item, final_bid, winner)

    from pprint import pprint
    pprint(bids)
    print('_'*80)
    pprint(winner)
    print('_'*80)
    pprint(final_bid)

