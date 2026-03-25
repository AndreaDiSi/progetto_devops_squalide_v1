import os
import sys
import atexit

# 1. Env var PRIMA di qualsiasi import dell'app
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/squalide_test_db"
os.environ["MONGO_DB"] = "squalide_test_db"

# 2. Aggiunge python/app/ al path così i bare import in main.py funzionano
#    (from database import ..., from mongo import ...)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from fastapi.testclient import TestClient
from main import app  # main.py è in app/, ora trovabile
from database import init_db, get_conn
from mongo import documents, _client as _mongo_client

atexit.register(_mongo_client.close)


def create_test_db():
    conn = psycopg2.connect(
        dbname="postgres", user="postgres", password="postgres",
        host="localhost", port=5432,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = 'squalide_test_db'")
        if not cur.fetchone():
            cur.execute("CREATE DATABASE squalide_test_db")
    conn.close()
    init_db()


def clean_tables():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """TRUNCATE users, groups, user_groups, invitations,
                          documents, folders, folder_documents,
                          folder_document_permissions
                   RESTART IDENTITY CASCADE"""
            )
        conn.commit()
    documents.delete_many({})


def new_client():
    return TestClient(app)


def register_and_login(client, username, email=None, password="testpass"):
    email = email or f"{username}@test.com"
    client.post("/register", data={"username": username, "email": email, "password": password})
    client.post("/login", data={"username": username, "password": password})
    return client
