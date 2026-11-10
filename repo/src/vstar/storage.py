from pathlib import Path
import sqlite3
from .io import now, read_json, sha256


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.db = sqlite3.connect(root / "state.sqlite3")
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, state TEXT NOT NULL, input_hash TEXT, artifact TEXT,
            artifact_hash TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated TEXT)""")
        self.db.commit()

    def cached(self, key, fingerprint):
        row = self.db.execute("SELECT state,input_hash,artifact,artifact_hash FROM tasks WHERE id=?", (key,)).fetchone()
        if not row or row[0] != "success" or row[1] != fingerprint:
            return None
        path = self.root / row[2]
        if not path.is_file() or sha256(path) != row[3]:
            return None
        return read_json(path)

    def start(self, key, fingerprint):
        with self.db:
            self.db.execute("""INSERT INTO tasks(id,state,input_hash,attempts,updated)
                VALUES(?, 'running', ?, 1, ?) ON CONFLICT(id) DO UPDATE SET
                state='running',input_hash=excluded.input_hash,attempts=attempts+1,error=NULL,updated=excluded.updated""", (key, fingerprint, now()))

    def finish(self, key, path):
        with self.db:
            self.db.execute("UPDATE tasks SET state='success',artifact=?,artifact_hash=?,error=NULL,updated=? WHERE id=?",
                            (str(path.relative_to(self.root)), sha256(path), now(), key))

    def fail(self, key, error):
        with self.db:
            self.db.execute("UPDATE tasks SET state='failed',error=?,updated=? WHERE id=?", (str(error), now(), key))

    def close(self):
        self.db.close()
