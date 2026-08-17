from pymongo import MongoClient
from dotenv import load_dotenv
from dataclasses import asdict
import os

load_dotenv()

class MongoDB:

    def __init__(self):
        self.client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.client[os.getenv("DB_NAME")]
        self.collection = self.db[os.getenv("COLLECTION_NAME")]

    def save_post(self, post):
        self.collection.insert_one(asdict(post))