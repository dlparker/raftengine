import random
import json
from faker import Faker

fake = Faker()

adjectives = ['Vintage', 'Modern', 'Rare', 'Antique', 'Brand-New']
nouns = ['Chair', 'Painting', 'Laptop', 'Book', 'Watch']
categories = ['Electronics', 'Books', 'Clothing', 'Art', 'Furniture']

def generate_item(item_id):
    name = f"{random.choice(adjectives)} {random.choice(nouns)}"
    return {
        'item_id': item_id,
        'name': name,
        'description': f"A {name.lower()} in excellent condition.",
        'category': random.choice(categories),
        'starting_bid': round(random.uniform(10, 1000), 2),
        'reserve_price': round(random.uniform(50, 1500), 2)
    }


def generate_person(person_id, role='bidder'):
    return {
        'person_id': person_id,
        'role': role,
        'name': fake.name(),
        'address': fake.address().replace('\n', ', '),
        'email': fake.email(),
        'phone': fake.phone_number()
    }

