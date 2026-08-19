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

        post_dict = asdict(post)

        existing_post = self.collection.find_one({
            "author": post.author,
            "text": post.text
        })

        if existing_post:
            print(f"Skipped duplicate: {post.author}")
            return

        self.collection.insert_one(post_dict)

        print(f"Saved: {post.author}")