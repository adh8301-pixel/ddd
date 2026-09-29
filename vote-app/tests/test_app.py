import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

import app as vote_app  # noqa: E402
import db  # noqa: E402
from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})


@pytest.fixture
def client(app):
    return app.test_client()


def query(app, sql):
    with app.app_context():
        return db.get_db().execute(sql).fetchall()


def make_poll(client, question="점심 메뉴?", options=("짜장면", "짬뽕")):
    return client.post("/create", data={"question": question, "option": list(options)})


def option_ids(app):
    return [r["id"] for r in query(app, "SELECT id FROM option ORDER BY position")]


# T1

def test_app_starts_with_empty_tables(app):
    assert query(app, "SELECT COUNT(*) FROM poll")[0][0] == 0


# T2

def test_ac1_index_redirects_to_create_when_no_poll(client):
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/create")


def test_create_poll_redirects_to_vote(client, app):
    res = make_poll(client)
    assert res.status_code == 303
    assert res.headers["Location"].endswith("/vote")
    assert client.get("/").headers["Location"].endswith("/vote")
    labels = [r["label"] for r in query(app, "SELECT label FROM option ORDER BY position")]
    assert labels == ["짜장면", "짬뽕"]


def test_create_ignores_blank_options(client, app):
    make_poll(client, options=("A", "  ", "B", "", ""))
    assert len(option_ids(app)) == 2


@pytest.mark.parametrize("data, message", [
    ({"question": "Q", "option": ["A"]}, "선택지는 2개 이상 5개 이하로 입력하세요."),
    ({"question": "Q", "option": list("ABCDEF")}, "선택지는 2개 이상 5개 이하로 입력하세요."),
    ({"question": "   ", "option": ["A", "B"]}, "질문을 입력하세요."),
    ({"question": "Q" * 201, "option": ["A", "B"]}, "질문은 200자 이하로 입력하세요."),
    ({"question": "Q", "option": ["A", "A"]}, "같은 선택지가 중복되었습니다."),
    ({"question": "Q", "option": ["A", "B" * 101]}, "선택지는 100자 이하로 입력하세요."),
])
def test_ac3_invalid_poll_is_rejected(client, app, data, message):
    res = client.post("/create", data=data)
    assert res.status_code == 400
    assert message in res.get_data(as_text=True)
    assert query(app, "SELECT COUNT(*) FROM poll")[0][0] == 0


def test_ac8_new_poll_replaces_old_poll_and_votes(client, app):
    make_poll(client)
    client.post("/vote", data={"option_id": option_ids(app)[0], "nickname": "민수"})
    assert "기존 투표와 결과가 삭제됩니다" in client.get("/create").get_data(as_text=True)

    make_poll(client, question="음료?", options=("커피", "차", "주스"))
    assert query(app, "SELECT question FROM poll")[0][0] == "음료?"
    assert query(app, "SELECT COUNT(*) FROM poll")[0][0] == 1
    assert len(option_ids(app)) == 3
    assert query(app, "SELECT COUNT(*) FROM vote")[0][0] == 0


# T3

def test_vote_and_results_redirect_to_create_without_poll(client):
    assert client.get("/vote").headers["Location"].endswith("/create")
    assert client.get("/results").headers["Location"].endswith("/create")


def test_ac2_vote_page_shows_question_and_options(client):
    make_poll(client)
    html = client.get("/vote").get_data(as_text=True)
    assert "점심 메뉴?" in html
    assert "짜장면" in html and "짬뽕" in html


def test_ac4_vote_requires_nickname(client, app):
    make_poll(client)
    res = client.post("/vote", data={"option_id": option_ids(app)[0], "nickname": "  "})
    assert res.status_code == 400
    assert "닉네임을 입력하세요." in res.get_data(as_text=True)


def test_nickname_too_long(client, app):
    make_poll(client)
    res = client.post("/vote", data={"option_id": option_ids(app)[0], "nickname": "가" * 21})
    assert res.status_code == 400
    assert "닉네임은 20자 이하로 입력하세요." in res.get_data(as_text=True)


@pytest.mark.parametrize("option_id", ["", "9999", "abc", "-1"])
def test_ac5_invalid_option_is_rejected(client, app, option_id):
    make_poll(client)
    res = client.post("/vote", data={"option_id": option_id, "nickname": "민수"})
    assert res.status_code == 400
    assert "선택지를 골라주세요." in res.get_data(as_text=True)
    assert query(app, "SELECT COUNT(*) FROM vote")[0][0] == 0


def test_ac7_same_nickname_can_vote_twice(client, app):
    make_poll(client)
    a = option_ids(app)[0]
    client.post("/vote", data={"option_id": a, "nickname": "민수"})
    client.post("/vote", data={"option_id": a, "nickname": "민수"})
    assert query(app, "SELECT COUNT(*) FROM vote")[0][0] == 2


# T4

def test_ac6_results_table(client, app):
    make_poll(client, options=("A", "B"))
    a, b = option_ids(app)
    client.post("/vote", data={"option_id": a, "nickname": "민수"})
    client.post("/vote", data={"option_id": a, "nickname": "지원"})
    client.post("/vote", data={"option_id": b, "nickname": "서연"})

    html = client.get("/results").get_data(as_text=True)
    assert "66.7%" in html and "33.3%" in html
    assert "민수, 지원" in html
    assert "서연" in html
    assert "총 3표" in html


def test_results_with_no_votes(client):
    make_poll(client)
    html = client.get("/results").get_data(as_text=True)
    assert "0표 · 0.0%" in html
    assert 'style="width: 0.0%"' in html
    assert "총 0표" in html


def test_ac9_nickname_is_escaped(client, app):
    make_poll(client)
    client.post("/vote", data={"option_id": option_ids(app)[0], "nickname": "<script>"})
    html = client.get("/results").get_data(as_text=True)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_ac10_refreshing_results_does_not_add_votes(client, app):
    make_poll(client)
    res = client.post("/vote", data={"option_id": option_ids(app)[0], "nickname": "민수"})
    assert res.status_code == 303
    assert res.headers["Location"].endswith("/results")
    client.get("/results")
    client.get("/results")
    assert query(app, "SELECT COUNT(*) FROM vote")[0][0] == 1


# v2: 마감 시간

def future(minutes=60):
    return (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def close_poll(app):
    with app.app_context():
        conn = db.get_db()
        conn.execute("UPDATE poll SET closes_at = '2000-01-01T00:00'")
        conn.commit()


def test_create_with_deadline(client, app):
    deadline = future()
    client.post("/create", data={"question": "Q", "option": ["A", "B"], "closes_at": deadline})
    assert query(app, "SELECT closes_at FROM poll")[0][0] == deadline
    assert f"마감: {deadline.replace('T', ' ')}" in client.get("/vote").get_data(as_text=True)


def test_create_without_deadline_stores_null(client, app):
    make_poll(client)
    assert query(app, "SELECT closes_at FROM poll")[0][0] is None
    assert "마감 없음" in client.get("/results").get_data(as_text=True)


@pytest.mark.parametrize("closes_at, message", [
    ("2000-01-01T00:00", "마감 시간은 현재 시각 이후로 설정하세요."),
    ("내일", "마감 시간 형식이 올바르지 않습니다."),
])
def test_invalid_deadline_is_rejected(client, app, closes_at, message):
    res = client.post("/create", data={"question": "Q", "option": ["A", "B"], "closes_at": closes_at})
    assert res.status_code == 400
    assert message in res.get_data(as_text=True)
    assert query(app, "SELECT COUNT(*) FROM poll")[0][0] == 0


def test_closed_poll_hides_form_and_rejects_votes(client, app):
    make_poll(client)
    a = option_ids(app)[0]
    close_poll(app)

    html = client.get("/vote").get_data(as_text=True)
    assert "투표가 마감되었습니다." in html
    assert 'name="nickname"' not in html

    res = client.post("/vote", data={"option_id": a, "nickname": "민수"})
    assert res.status_code == 403
    assert query(app, "SELECT COUNT(*) FROM vote")[0][0] == 0
    assert "마감됨" in client.get("/results").get_data(as_text=True)


def test_poll_closes_when_deadline_passes(client, app, monkeypatch):
    deadline = future(10)
    client.post("/create", data={"question": "Q", "option": ["A", "B"], "closes_at": deadline})
    monkeypatch.setattr(vote_app, "now", lambda: datetime.now() + timedelta(minutes=11))
    res = client.post("/vote", data={"option_id": option_ids(app)[0], "nickname": "민수"})
    assert res.status_code == 403


def test_old_database_gets_deadline_column(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE poll (id INTEGER PRIMARY KEY, question TEXT NOT NULL,"
                 " created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    conn.close()
    app = create_app({"TESTING": True, "DATABASE": str(path)})
    columns = [r["name"] for r in query(app, "PRAGMA table_info(poll)")]
    assert "closes_at" in columns


# v2: 그래프

def test_results_show_bar_chart(client, app):
    make_poll(client, options=("A", "B"))
    a, b = option_ids(app)
    for name in ("민수", "지원"):
        client.post("/vote", data={"option_id": a, "nickname": name})
    client.post("/vote", data={"option_id": b, "nickname": "서연"})

    html = client.get("/results").get_data(as_text=True)
    assert 'aria-label="득표 그래프"' in html
    assert 'class="bar leader" style="width: 66.7%"' in html
    assert 'class="bar" style="width: 33.3%"' in html
    assert "2표 · 66.7%" in html


# v2: 만든 사람 이름

@pytest.mark.parametrize("path", ["/create", "/vote", "/results"])
def test_author_name_on_every_page(client, path):
    make_poll(client)
    assert "만든 사람: 안동현" in client.get(path).get_data(as_text=True)


# 코드 리뷰 수정

def test_unicode_digit_option_id_is_rejected(client):
    make_poll(client)
    res = client.post("/vote", data={"option_id": "²", "nickname": "민수"})
    assert res.status_code == 400


def test_percent_rounds_half_up(client, app):
    make_poll(client, options=("A", "B"))
    a, b = option_ids(app)
    client.post("/vote", data={"option_id": a, "nickname": "x"})
    for i in range(15):
        client.post("/vote", data={"option_id": b, "nickname": f"y{i}"})
    html = client.get("/results").get_data(as_text=True)
    assert "6.3%" in html and "93.8%" in html


def test_vote_for_deleted_option_does_not_crash(client, app, monkeypatch):
    make_poll(client)
    a = option_ids(app)[0]

    def fail(*args):
        raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

    monkeypatch.setattr(db, "add_vote", fail)
    res = client.post("/vote", data={"option_id": a, "nickname": "민수"})
    assert res.status_code == 303
    assert res.headers["Location"].endswith("/vote")


# v3: 관리자 비밀번호

@pytest.fixture
def admin_app(tmp_path):
    return create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "test.db"),
        "ADMIN_PASSWORD": "secret",
    })


def test_create_form_asks_password_when_set(admin_app):
    html = admin_app.test_client().get("/create").get_data(as_text=True)
    assert 'name="admin_password"' in html


def test_create_form_hides_password_when_not_set(client):
    assert 'name="admin_password"' not in client.get("/create").get_data(as_text=True)


@pytest.mark.parametrize("password", [None, "", "wrong"])
def test_create_rejects_wrong_password(admin_app, password):
    data = {"question": "Q", "option": ["A", "B"]}
    if password is not None:
        data["admin_password"] = password
    res = admin_app.test_client().post("/create", data=data)
    assert res.status_code == 403
    assert "관리자 비밀번호가 올바르지 않습니다." in res.get_data(as_text=True)
    assert query(admin_app, "SELECT COUNT(*) FROM poll")[0][0] == 0


def test_wrong_password_keeps_existing_poll(admin_app):
    c = admin_app.test_client()
    c.post("/create", data={"question": "기존", "option": ["A", "B"], "admin_password": "secret"})
    c.post("/create", data={"question": "새것", "option": ["C", "D"], "admin_password": "x"})
    assert query(admin_app, "SELECT question FROM poll")[0][0] == "기존"


def test_create_with_correct_password(admin_app):
    res = admin_app.test_client().post(
        "/create",
        data={"question": "Q", "option": ["A", "B"], "admin_password": "secret"},
    )
    assert res.status_code == 303
    assert query(admin_app, "SELECT question FROM poll")[0][0] == "Q"


def test_voting_needs_no_password(admin_app):
    c = admin_app.test_client()
    c.post("/create", data={"question": "Q", "option": ["A", "B"], "admin_password": "secret"})
    a = option_ids(admin_app)[0]
    assert c.post("/vote", data={"option_id": a, "nickname": "민수"}).status_code == 303
