from __future__ import annotations

import threading
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import settings


@dataclass(slots=True)
class Conversation:
    id: str
    analysis_id: str


class ConversationStore:
    def __init__(self, path: Path | None = None, max_conversations: int = 200) -> None:
        self.path = (path or settings.state_path).resolve()
        self.max_conversations = max_conversations
        self._lock = threading.RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if not self._initialized:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'ask',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON conversation_messages(conversation_id, id);
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(conversation_messages)"
                ).fetchall()
            }
            if "answer_json" not in columns:
                connection.execute(
                    "ALTER TABLE conversation_messages ADD COLUMN answer_json TEXT"
                )
            conversation_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(conversations)"
                ).fetchall()
            }
            if "channel" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations "
                    "ADD COLUMN channel TEXT NOT NULL DEFAULT 'ask'"
                )
            connection.commit()
            self._initialized = True
        return connection

    def _prune(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        for row in rows[self.max_conversations :]:
            connection.execute(
                "DELETE FROM conversations WHERE id = ?", (row["id"],)
            )

    def get_or_create(
        self,
        analysis_id: str,
        conversation_id: str | None,
        channel: str = "ask",
    ) -> Conversation:
        with self._lock:
            with closing(self._connect()) as connection:
                row = (
                    connection.execute(
                        "SELECT id, analysis_id, channel FROM conversations WHERE id = ?",
                        (conversation_id,),
                    ).fetchone()
                    if conversation_id
                    else None
                )
                if row is not None and row["analysis_id"] != analysis_id:
                    raise ValueError("Conversation belongs to another analysis")
                if row is not None and row["channel"] != channel:
                    raise ValueError("Conversation belongs to another workspace")
                now = time.time()
                if row is None:
                    identifier = uuid.uuid4().hex
                    connection.execute(
                        "INSERT INTO conversations("
                        "id, analysis_id, channel, created_at, updated_at"
                        ") VALUES (?, ?, ?, ?, ?)",
                        (identifier, analysis_id, channel, now, now),
                    )
                else:
                    identifier = row["id"]
                    connection.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?",
                        (now, identifier),
                    )
                self._prune(connection)
                connection.commit()
                return Conversation(id=identifier, analysis_id=analysis_id)

    def latest(self, analysis_id: str, channel: str = "ask") -> Conversation | None:
        with self._lock:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT id, analysis_id FROM conversations "
                    "WHERE analysis_id = ? AND channel = ? "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (analysis_id, channel),
                ).fetchone()
                if row is None:
                    return None
                return Conversation(id=str(row["id"]), analysis_id=str(row["analysis_id"]))

    def history(self, conversation: Conversation) -> list[dict[str, str]]:
        with self._lock:
            limit = settings.chat_history_turns * 2
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT role, content FROM ("
                    "SELECT id, role, content FROM conversation_messages "
                    "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?"
                    ") ORDER BY id ASC",
                    (conversation.id, limit),
                ).fetchall()
                return [
                    {"role": str(row["role"]), "content": str(row["content"])}
                    for row in rows
                ]

    def transcript(self, conversation: Conversation) -> list[dict[str, str | None]]:
        with self._lock:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT role, content, answer_json FROM conversation_messages "
                    "WHERE conversation_id = ? ORDER BY id ASC",
                    (conversation.id,),
                ).fetchall()
                return [
                    {
                        "role": str(row["role"]),
                        "content": str(row["content"]),
                        "answer_json": (
                            str(row["answer_json"])
                            if row["answer_json"] is not None
                            else None
                        ),
                    }
                    for row in rows
                ]

    def append_turn(
        self,
        conversation: Conversation,
        question: str,
        answer: str,
        answer_json: str | None = None,
    ) -> None:
        with self._lock:
            with closing(self._connect()) as connection:
                now = time.time()
                connection.executemany(
                    "INSERT INTO conversation_messages("
                    "conversation_id, role, content, answer_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?)",
                    (
                        (conversation.id, "user", question, None, now),
                        (conversation.id, "assistant", answer, answer_json, now),
                    ),
                )
                max_messages = settings.chat_history_turns * 2
                connection.execute(
                    "DELETE FROM conversation_messages WHERE conversation_id = ? "
                    "AND id NOT IN (SELECT id FROM conversation_messages "
                    "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?)",
                    (conversation.id, conversation.id, max_messages),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now, conversation.id),
                )
                connection.commit()


conversations = ConversationStore()
