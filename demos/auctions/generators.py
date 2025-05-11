import random
import json
from faker import Faker
from records import Person, Item
fake = Faker()

adjectives = ['Vintage', 'Modern', 'Rare', 'Antique', 'Brand-New']
nouns = ['Chair', 'Painting', 'Laptop', 'Book', 'Watch']
categories = ['Electronics', 'Books', 'Clothing', 'Art', 'Furniture']

def generate_item(item_id):
    name = f"{random.choice(adjectives)} {random.choice(nouns)}"
    item = Item(item_id = item_id,
                name = name,
                description = f"A {name.lower()} in excellent condition.",
                category = random.choice(categories),
                starting_bid = round(random.uniform(10, 1000), 2),
                reserve_price = round(random.uniform(50, 1500), 2),
                seller_id = 0)
    return item


def generate_person(person_id, role='bidder'):
    person = Person(person_id = person_id,
                    role = role,
                    name = fake.name(),
                    address = fake.address().replace('\n', ', '),
                    email = fake.email(),
                    phone = fake.phone_number()
                    )
    return person

