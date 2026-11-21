import json
from pathlib import Path
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


class SessionStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "sessions.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created_at TEXT, name TEXT, status TEXT, metadata TEXT)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, name, metadata, status="ready"):
        identifier = uuid.uuid4().hex
        self.path(identifier).mkdir()
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                       (identifier, datetime.now(timezone.utc).isoformat(), name, status, json.dumps(metadata)))
        return self.get(identifier)

    def path(self, identifier):
        if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
            raise KeyError(identifier)
        return self.root / identifier

    def get(self, identifier):
        self.path(identifier)
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        return result

    def list(self):
        with self.connect() as db:
            identifiers = [r[0] for r in db.execute("SELECT id FROM sessions ORDER BY created_at DESC")]
        return [self.get(i) for i in identifiers]

    def update(self, identifier, status, metadata=None):
        current = self.get(identifier)
        with self.connect() as db:
            db.execute("UPDATE sessions SET status=?, metadata=? WHERE id=?",
                       (status, json.dumps(metadata if metadata is not None else current["metadata"]), identifier))
        return self.get(identifier)
