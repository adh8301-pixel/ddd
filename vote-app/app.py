import hmac
import os
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

import db

AUTHOR_NAME = "안동현"
MAX_OPTIONS = 5
TIME_FORMAT = "%Y-%m-%dT%H:%M"
# Vercel 서버는 UTC로 돌기 때문에 마감 시간은 항상 한국 시각으로 계산한다.
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(KST).replace(tzinfo=None)


def parse_closes_at(raw, current):
    """마감 시간 입력값을 검사한다. (저장할 문자열 또는 None, 오류 메시지 또는 None)"""
    raw = raw.strip()
    if not raw:
        return None, None
    try:
        closes_at = datetime.fromisoformat(raw)
    except ValueError:
        return None, "마감 시간 형식이 올바르지 않습니다."
    if closes_at <= current:
        return None, "마감 시간은 현재 시각 이후로 설정하세요."
    return closes_at.strftime(TIME_FORMAT), None


def is_closed(poll, current):
    return bool(poll["closes_at"]) and datetime.fromisoformat(poll["closes_at"]) <= current


def validate_poll(form, current):
    question = form.get("question", "").strip()
    labels = [s.strip() for s in form.getlist("option")]
    labels = [s for s in labels if s]
    closes_at, closes_error = parse_closes_at(form.get("closes_at", ""), current)

    errors = []
    if not question:
        errors.append("질문을 입력하세요.")
    elif len(question) > 200:
        errors.append("질문은 200자 이하로 입력하세요.")
    if not 2 <= len(labels) <= MAX_OPTIONS:
        errors.append("선택지는 2개 이상 5개 이하로 입력하세요.")
    if any(len(label) > 100 for label in labels):
        errors.append("선택지는 100자 이하로 입력하세요.")
    if len(set(labels)) != len(labels):
        errors.append("같은 선택지가 중복되었습니다.")
    if closes_error:
        errors.append(closes_error)
    return question, labels, closes_at, errors


def validate_vote(form, options):
    nickname = form.get("nickname", "").strip()
    try:
        option_id = int(form.get("option_id", ""))
    except ValueError:
        option_id = None

    errors = []
    if option_id not in {o["id"] for o in options}:
        errors.append("선택지를 골라주세요.")
    if not nickname:
        errors.append("닉네임을 입력하세요.")
    elif len(nickname) > 20:
        errors.append("닉네임은 20자 이하로 입력하세요.")
    return option_id, nickname, errors


def percent_of(count, total):
    """소수점 첫째 자리까지 반올림한 비율(Decimal)."""
    if not total:
        return Decimal("0.0")
    return (Decimal(count) * 100 / total).quantize(Decimal("0.1"), ROUND_HALF_UP)


def build_results(options, voters):
    total = sum(len(v) for v in voters.values())
    top = max((len(v) for v in voters.values()), default=0)
    rows = []
    for o in options:
        names = voters.get(o["id"], [])
        percent = percent_of(len(names), total)
        rows.append({
            "label": o["label"],
            "count": len(names),
            "percent": f"{percent}%",
            "width": percent,
            "leader": top > 0 and len(names) == top,
            "voters": ", ".join(names) or "-",
        })
    return rows, total


def check_admin_password(form, expected):
    """관리자 비밀번호가 설정되어 있을 때만 검사한다. 맞으면 None, 틀리면 오류 메시지."""
    if not expected:
        return None
    given = form.get("admin_password", "")
    if hmac.compare_digest(given.encode(), expected.encode()):
        return None
    return "관리자 비밀번호가 올바르지 않습니다."


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=str(Path(app.root_path) / "vote.db"),
        # 설정되어 있으면 Postgres(Neon)를 쓰고, 없으면 로컬 SQLite 파일을 쓴다.
        DATABASE_URL=os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL"),
        # 설정되어 있으면 투표를 만들 때 이 비밀번호를 입력해야 한다.
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
    )
    if test_config:
        app.config.update(test_config)
    if os.environ.get("VERCEL") and not app.config["DATABASE_URL"]:
        raise RuntimeError(
            "Vercel에서는 SQLite 파일에 저장할 수 없습니다. "
            "Storage 탭에서 Postgres(Neon)를 연결해 DATABASE_URL을 설정하세요."
        )
    if os.environ.get("VERCEL") and not app.config["ADMIN_PASSWORD"]:
        raise RuntimeError(
            "공개 사이트에서는 관리자 비밀번호가 필요합니다. "
            "Settings → Environment Variables에 ADMIN_PASSWORD를 추가하세요."
        )

    db.init_app(app)
    with app.app_context():
        db.ensure_schema()

    @app.context_processor
    def inject_author():
        return {
            "author": AUTHOR_NAME,
            "admin_required": bool(app.config["ADMIN_PASSWORD"]),
        }

    @app.template_filter("display_time")
    def display_time(value):
        return value.replace("T", " ")

    @app.get("/")
    def index():
        return redirect(url_for("vote" if db.get_poll() else "create"))

    @app.route("/create", methods=["GET", "POST"])
    def create():
        current = now()
        has_poll = db.get_poll() is not None
        min_closes_at = current.strftime(TIME_FORMAT)
        if request.method == "GET":
            return render_template(
                "create.html", has_poll=has_poll, question="",
                options=[""] * MAX_OPTIONS, closes_at="",
                min_closes_at=min_closes_at, errors=[],
            )

        password_error = check_admin_password(
            request.form, app.config["ADMIN_PASSWORD"]
        )
        if password_error:
            question, labels, closes_at, errors = "", [], None, [password_error]
            status = 403
        else:
            question, labels, closes_at, errors = validate_poll(request.form, current)
            status = 400
        if errors:
            raw = request.form.getlist("option")[:MAX_OPTIONS]
            raw += [""] * (MAX_OPTIONS - len(raw))
            return render_template(
                "create.html", has_poll=has_poll,
                question=request.form.get("question", ""), options=raw,
                closes_at=request.form.get("closes_at", ""),
                min_closes_at=min_closes_at, errors=errors,
            ), status

        db.replace_poll(question, labels, closes_at)
        return redirect(url_for("vote"), code=303)

    @app.route("/vote", methods=["GET", "POST"])
    def vote():
        poll = db.get_poll()
        if poll is None:
            return redirect(url_for("create"))
        options = db.get_options(poll["id"])
        closed = is_closed(poll, now())

        if request.method == "GET":
            return render_template(
                "vote.html", poll=poll, options=options, closed=closed,
                selected=None, nickname="", errors=[],
            )

        if closed:
            return render_template(
                "vote.html", poll=poll, options=options, closed=True,
                selected=None, nickname="", errors=["투표가 마감되었습니다."],
            ), 403

        option_id, nickname, errors = validate_vote(request.form, options)
        if errors:
            return render_template(
                "vote.html", poll=poll, options=options, closed=False,
                selected=option_id, nickname=request.form.get("nickname", ""),
                errors=errors,
            ), 400

        try:
            db.add_vote(option_id, nickname)
        except db.IntegrityError:
            # 검증과 저장 사이에 새 투표가 만들어져 선택지가 사라진 경우
            return redirect(url_for("vote"), code=303)
        return redirect(url_for("results"), code=303)

    @app.get("/results")
    def results():
        poll = db.get_poll()
        if poll is None:
            return redirect(url_for("create"))
        rows, total = build_results(
            db.get_options(poll["id"]), db.get_voters(poll["id"])
        )
        return render_template(
            "results.html", poll=poll, rows=rows, total=total,
            closed=is_closed(poll, now()),
        )

    return app
