import os
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
documents = _client[os.getenv("MONGO_DB", "squalide_db")]["documents"]
