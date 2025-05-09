import random
import math

def participation_probability(current_bid, starting_bid):
    multiplier = current_bid / starting_bid
    return 1 / (1 + math.exp(2 * (multiplier - 2)))  # Drops sharply after 2x

class Bidder:

    def __init__(self, bidder_id, person, budget, aggression=0.5):
        self.bidder_id = bidder_id
        self.person = person
        self.budget = budget  # Max amount bidder can spend
        self.aggression = aggression  # 0 to 1, higher means larger bid increases
        self.valuation = None  # Set per item

    def set_valuation(self, item_starting_bid):
        # Valuation is 1–3x starting bid, reflecting bidder’s perceived value
        self.valuation = random.uniform(item_starting_bid, item_starting_bid * 3)

    def propose_bid(self, current_bid, min_increment=1.0):
        # Propose a bid as a percentage increase over current bid
        max_increase = self.aggression * 0.2  # Aggressive bidders increase up to 20%
        min_increase = self.aggression * 0.01  # Cautious bidders increase at least 1%
        increase = random.uniform(min_increase, max_increase) * current_bid
        proposed_bid = round(current_bid + max(increase, min_increment), 2)
        return min(proposed_bid, self.budget)  # Respect budget

    def decide_to_bid(self, proposed_bid, current_bid, auction_progress):
        # Auction progress: 0 (start) to 1 (end)
        # Logistic function to model bid probability
        if proposed_bid > self.valuation or proposed_bid > self.budget:
            return False
        # Willingness decreases as price approaches valuation or auction nears end
        willingness = 1 / (1 + math.exp(5 * (proposed_bid / self.valuation - 0.5)))
        willingness *= (1 - auction_progress)  # Less likely to bid late
        return random.random() < willingness

def simulate_auction(item, bidders, duration=100):
    current_bid = item['starting_bid']
    highest_bidder = None
    bids = []
    
    for t in range(duration):
        auction_progress = t / duration
        active_bidders = [b for b in bidders if random.random() < 0.1]  # Subset participates
        for bidder in active_bidders:
            bidder.set_valuation(item['starting_bid'])
            proposed_bid = bidder.propose_bid(current_bid)
            prob = participation_probability(current_bid, item['starting_bid'])
            if bidder.decide_to_bid(proposed_bid, current_bid, auction_progress):
                current_bid = proposed_bid
                highest_bidder = bidder.bidder_id
                bids.append({
                    'item_id': item['item_id'],
                    'bidder_id': bidder.bidder_id,
                    'bid_amount': proposed_bid,
                    'timestamp': t
                })
    
    return bids, highest_bidder, current_bid



