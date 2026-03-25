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
            # Migrazione: ricrea documents se manca mongo_doc_id (vecchio schema)
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 'mongo_doc_id'
            """)
            if not cur.fetchone():
                cur.execute("DROP TABLE IF EXISTS folder_document_permissions CASCADE")
                cur.execute("DROP TABLE IF EXISTS folder_documents CASCADE")
                cur.execute("DROP TABLE IF EXISTS folders CASCADE")
                cur.execute("DROP TABLE IF EXISTS shared_documents CASCADE")
                cur.execute("DROP TABLE IF EXISTS documents CASCADE")

            # Migrazione: ricrea le tabelle folder se hanno il vecchio schema (senza document_id)
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'folder_documents' AND column_name = 'document_id'
            """)
            if not cur.fetchone():
                cur.execute("DROP TABLE IF EXISTS folder_document_permissions CASCADE")
                cur.execute("DROP TABLE IF EXISTS folder_documents CASCADE")
                cur.execute("DROP TABLE IF EXISTS folders CASCADE")

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
                    mongo_doc_id VARCHAR(24) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER NOT NULL REFERENCES users(user_id),
                    updated_at TIMESTAMP,
                    updated_by INTEGER REFERENCES users(user_id),
                    deleted_at TIMESTAMP,
                    deleted_by INTEGER REFERENCES users(user_id)
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


                CREATE TABLE IF NOT EXISTS folders (
                    folder_id SERIAL PRIMARY KEY,
                    group_id INTEGER NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(group_id)
                );


                CREATE TABLE IF NOT EXISTS folder_documents (
                    id SERIAL PRIMARY KEY,
                    folder_id INTEGER NOT NULL REFERENCES folders(folder_id) ON DELETE CASCADE,
                    document_id INTEGER NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                    owner_id INTEGER NOT NULL REFERENCES users(user_id),
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER NOT NULL REFERENCES users(user_id),
                    updated_at TIMESTAMP,
                    updated_by INTEGER REFERENCES users(user_id),
                    deleted_at TIMESTAMP,
                    deleted_by INTEGER REFERENCES users(user_id),
                    UNIQUE(folder_id, document_id)
                );


                CREATE TABLE IF NOT EXISTS folder_document_permissions (
                    id SERIAL PRIMARY KEY,
                    folder_doc_id INTEGER NOT NULL REFERENCES folder_documents(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    can_edit BOOLEAN DEFAULT FALSE,
                    can_delete BOOLEAN DEFAULT FALSE,
                    UNIQUE(folder_doc_id, user_id)
                );
            """)
        conn.commit()
