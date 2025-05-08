
class SnapShot:

    def __init__(self, last_index, last_term):
        self.last_index = last_index
        self.last_term = last_term
        self.data = []
        self.items_per_chunk = 2

    async def get_last_index(self):
        return self.last_index
    
    async def get_last_term(self):
        return self.last_term

    async def add_data_item(self, item):
        self.data.append(item)
        
    async def get_chunk(self, offset=0):
        done = False
        limit = offset + self.items_per_chunk
        if limit >= len(self.data):
            done = True
        data = self.data[offset:limit + 1]
        return data, limit + 1, done

    async def save_chunk(self, data, offset=0):
        if len(self.data) != offset:
            raise Exception('cannot store data out of order')
        self.data.extend(data)

