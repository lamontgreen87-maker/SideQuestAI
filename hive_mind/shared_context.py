class SharedKnowledge:
    """
    A simple repository for drones to share discovered knowledge.
    """
    def __init__(self):
        self.data = {}

    def update(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)
