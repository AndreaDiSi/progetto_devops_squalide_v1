import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50),
                    deleted BOOLEAN DEFAULT FALSE,
                    owners INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP
                );


                CREATE TABLE IF NOT EXISTS groups (
                    group_id SERIAL PRIMARY KEY,
                    group_owner INTEGER NOT NULL REFERENCES users(user_id),
                    group_name VARCHAR(100) NOT NULL
                );


                CREATE TABLE IF NOT EXISTS user_groups (
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    group_id INTEGER NOT NULL REFERENCES groups(group_id),
                    PRIMARY KEY (user_id, group_id)
                );


                CREATE TABLE IF NOT EXISTS invitations (
                    invitation_id SERIAL PRIMARY KEY,
                    group_id INTEGER NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
                    inviter_id INTEGER NOT NULL REFERENCES users(user_id),
                    invitee_id INTEGER NOT NULL REFERENCES users(user_id),
                    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (group_id, invitee_id)
                );


                CREATE TABLE IF NOT EXISTS documents (
                    document_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    title VARCHAR(255),
                    content TEXT,
                    file_name VARCHAR(255),
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );


                CREATE TABLE IF NOT EXISTS shared_documents (
                    share_id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES documents(document_id),
                    owner_id INTEGER NOT NULL REFERENCES users(user_id),
                    shared_with_id INTEGER NOT NULL REFERENCES users(user_id),
                    shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );


                CREATE TABLE IF NOT EXISTS saved_searches (
                    search_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    query TEXT NOT NULL,
                    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );


                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    type VARCHAR(100),
                    message TEXT,
                    is_read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB
                );


                CREATE TABLE IF NOT EXISTS action_logs (
                    log_id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id),
                    action_type VARCHAR(100),
                    entity_type VARCHAR(100),
                    entity_id INTEGER,
                    old_value TEXT,
                    new_value TEXT,
                    action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address VARCHAR(45),
                    user_agent TEXT
                );
            """)
        conn.commit()
