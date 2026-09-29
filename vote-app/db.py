import sqlite3
from pathlib import Path

import click
from flask import current_app, g

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
PG_SCHEMA_PATH = Path(__file__).parent / "schema_postgres.sql"

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # 로컬에서 SQLite만 쓸 때는 psycopg가 없어도 된다.
    psycopg = None

IntegrityError = (sqlite3.IntegrityError,) + (
    (psycopg.IntegrityError,) if psycopg else ()
)


def use_postgres():
    return bool(current_app.config.get("DATABASE_URL"))


class PgConnection:
    """psycopg 연결을 sqlite3 연결처럼 쓸 수 있게 감싼다. (? 자리표시자, with 트랜잭션)"""

    def __init__(self, url):
        # Neon의 풀링 주소(PgBouncer)는 prepared statement를 지원하지 않으므로 끈다.
        self.conn = psycopg.connect(
            url, autocommit=True, row_factory=dict_row, prepare_threshold=None
        )

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s"), params)

    def executemany(self, sql, params_seq):
        with self.conn.cursor() as cur:
            cur.executemany(sql.replace("?", "%s"), params_seq)

    def executescript(self, script):
        self.conn.execute(script)

    def commit(self):
        pass  # autocommit 모드라 할 일이 없다.

    def close(self):
        self.conn.close()

    def __enter__(self):
        self._tx = self.conn.transaction()
        self._tx.__enter__()
        return self

    def __exit__(self, *exc):
        return self._tx.__exit__(*exc)


def get_db():
    if "db" not in g:
        if use_postgres():
            g.db = PgConnection(current_app.config["DATABASE_URL"])
        else:
            g.db = sqlite3.connect(current_app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    if use_postgres():
        get_db().executescript(
            "DROP TABLE IF EXISTS vote, option, poll;"
            + PG_SCHEMA_PATH.read_text(encoding="utf-8")
        )
    else:
        get_db().executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def ensure_schema():
    """테이블이 없으면 만든다. 데이터는 그대로 둔다."""
    if use_postgres():
        get_db().executescript(PG_SCHEMA_PATH.read_text(encoding="utf-8"))
    elif Path(current_app.config["DATABASE"]).exists():
        migrate()
    else:
        init_db()


def migrate():
    """예전 DB 파일에 없는 컬럼을 추가한다. 데이터는 그대로 둔다."""
    db = get_db()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(poll)")}
    if "closes_at" not in columns:
        db.execute("ALTER TABLE poll ADD COLUMN closes_at TEXT")
        db.commit()


@click.command("init-db")
def init_db_command():
    """테이블을 새로 만든다. 기존 데이터는 모두 삭제된다."""
    init_db()
    click.echo("DB를 초기화했습니다.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def get_poll():
    return get_db().execute(
        "SELECT id, question, closes_at FROM poll LIMIT 1"
    ).fetchone()


def get_options(poll_id):
    return get_db().execute(
        "SELECT id, label FROM option WHERE poll_id = ? ORDER BY position",
        (poll_id,),
    ).fetchall()


def replace_poll(question, labels, closes_at=None):
    """기존 투표를 지우고 새 투표를 저장한다. 한 트랜잭션으로 처리한다."""
    db = get_db()
    with db:
        db.execute("DELETE FROM poll")
        poll_id = db.execute(
            "INSERT INTO poll (question, closes_at) VALUES (?, ?) RETURNING id",
            (question, closes_at),
        ).fetchone()["id"]
        db.executemany(
            "INSERT INTO option (poll_id, label, position) VALUES (?, ?, ?)",
            [(poll_id, label, i) for i, label in enumerate(labels)],
        )


def add_vote(option_id, nickname):
    db = get_db()
    with db:
        db.execute(
            "INSERT INTO vote (option_id, nickname) VALUES (?, ?)",
            (option_id, nickname),
        )


def get_voters(poll_id):
    """선택지 id별 투표자 닉네임 목록을 투표한 순서대로 돌려준다."""
    rows = get_db().execute(
        "SELECT vote.option_id, vote.nickname FROM vote"
        " JOIN option ON option.id = vote.option_id"
        " WHERE option.poll_id = ? ORDER BY vote.id",
        (poll_id,),
    )
    voters = {}
    for row in rows:
        voters.setdefault(row["option_id"], []).append(row["nickname"])
    return voters
