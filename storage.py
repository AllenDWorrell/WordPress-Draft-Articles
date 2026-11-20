"""Local SQLite persistence for issues, active state, and draft history."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION=1


class Repository:
    def __init__(self,root):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'the-current.db'
        self._initialize()
        self.migrate_json()

    def connect(self):
        connection=sqlite3.connect(self.path,timeout=30)
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    @contextmanager
    def connection(self):
        connection=self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    project_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS active_issue (
                    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                    issue_id TEXT
                );
                CREATE TABLE IF NOT EXISTS draft_history (
                    draft_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
            """)
            connection.execute(
                'INSERT OR REPLACE INTO schema_meta(key,value) VALUES (?,?)',
                ('schema_version',str(SCHEMA_VERSION)),
            )

    def migrate_json(self):
        with self.connection() as connection:
            count=connection.execute('SELECT COUNT(*) FROM issues').fetchone()[0]
        if count:
            return
        for path in sorted(self.root.glob('*/project.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            try:
                project=json.loads(path.read_text('utf8'))
                if project.get('id'):
                    self.save_project(project)
            except (json.JSONDecodeError,OSError):
                continue
        active_path=self.root/'active-issue.json'
        if active_path.exists():
            try:
                self.set_active_issue(json.loads(active_path.read_text('utf8')))
            except (json.JSONDecodeError,OSError):
                pass
        history_path=self.root/'wordpress-drafts.json'
        if history_path.exists():
            try:
                history=json.loads(history_path.read_text('utf8'))
                for key,value in history.items():
                    self.set_draft(key,value)
            except (json.JSONDecodeError,OSError):
                pass

    def save_project(self,project):
        issue_id=project['id']
        with self.connection() as connection:
            connection.execute(
                'INSERT INTO issues(id,project_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) '
                'ON CONFLICT(id) DO UPDATE SET project_json=excluded.project_json,'
                'updated_at=CURRENT_TIMESTAMP',
                (issue_id,json.dumps(project,ensure_ascii=False,sort_keys=True)),
            )

    def load_project(self,issue_id):
        with self.connection() as connection:
            row=connection.execute(
                'SELECT project_json FROM issues WHERE id=?',(issue_id,)
            ).fetchone()
        if not row:
            raise ValueError('Issue not found.')
        return json.loads(row[0])

    def issue_exists(self,issue_id):
        with self.connection() as connection:
            return connection.execute(
                'SELECT 1 FROM issues WHERE id=?',(issue_id,)
            ).fetchone() is not None

    def saved_projects(self):
        with self.connection() as connection:
            rows=connection.execute(
                'SELECT project_json FROM issues ORDER BY updated_at DESC'
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def set_active_issue(self,issue_id):
        with self.connection() as connection:
            connection.execute(
                'INSERT INTO active_issue(singleton,issue_id) VALUES(1,?) '
                'ON CONFLICT(singleton) DO UPDATE SET issue_id=excluded.issue_id',
                (issue_id,),
            )

    def active_issue(self):
        with self.connection() as connection:
            row=connection.execute(
                'SELECT issue_id FROM active_issue WHERE singleton=1'
            ).fetchone()
        return row[0] if row else None

    def draft_history(self):
        with self.connection() as connection:
            rows=connection.execute(
                'SELECT draft_key,value_json FROM draft_history'
            ).fetchall()
        return {key:json.loads(value) for key,value in rows}

    def set_draft(self,draft_key,value):
        with self.connection() as connection:
            connection.execute(
                'INSERT INTO draft_history(draft_key,value_json) VALUES(?,?) '
                'ON CONFLICT(draft_key) DO UPDATE SET value_json=excluded.value_json',
                (draft_key,json.dumps(value,ensure_ascii=False)),
            )

    def delete_draft(self,draft_key):
        with self.connection() as connection:
            connection.execute(
                'DELETE FROM draft_history WHERE draft_key=?',(draft_key,)
            )

    def set_taxonomy(self,kind,values):
        with self.connection() as connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS taxonomy (kind TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at TEXT NOT NULL)'
            )
            connection.execute(
                'INSERT INTO taxonomy(kind,value_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) '
                'ON CONFLICT(kind) DO UPDATE SET value_json=excluded.value_json,updated_at=CURRENT_TIMESTAMP',
                (kind,json.dumps(values,ensure_ascii=False)),
            )

    def taxonomy(self,kind):
        with self.connection() as connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS taxonomy (kind TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at TEXT NOT NULL)'
            )
            row=connection.execute(
                'SELECT value_json FROM taxonomy WHERE kind=?',(kind,)
            ).fetchone()
        return json.loads(row[0]) if row else []

    def set_setting(self,key,value):
        with self.connection() as connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)'
            )
            connection.execute(
                'INSERT INTO settings(key,value) VALUES(?,?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (key,value),
            )

    def get_setting(self,key,default=''):
        with self.connection() as connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)'
            )
            row=connection.execute(
                'SELECT value FROM settings WHERE key=?',(key,)
            ).fetchone()
        return row[0] if row else default
