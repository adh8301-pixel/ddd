# 투표 앱 v1 명세

근거 문서: [REQUIREMENTS.md](REQUIREMENTS.md)

## 1. 범위

질문 하나와 선택지 2~5개로 된 투표를 한 번에 하나만 운영한다. 사용자는 닉네임을 입력하고 선택지 하나에 투표하며, 결과를 표로 본다.

제외: 그래프, 로그인, 중복 투표 방지, 여러 투표 동시 운영, 투표 마감.

## 2. 기술 스택

- Python 3.10+
- Flask (서버 렌더링, Jinja2 템플릿)
- SQLite (표준 라이브러리 `sqlite3`, DB 파일은 `vote.db`)
- JavaScript 없이 HTML form만으로 동작한다.

## 3. 디렉터리 구조

```
vote-app/
├── app.py            # Flask 앱, 라우트, 검증
├── db.py             # DB 연결, 스키마 초기화, 조회/저장 함수
├── schema.sql        # 테이블 정의
├── requirements.txt  # flask
├── templates/
│   ├── base.html
│   ├── create.html
│   ├── vote.html
│   └── results.html
├── static/
│   └── style.css
├── tests/
│   └── test_app.py
└── docs/
```

## 4. 데이터 모델

```sql
CREATE TABLE poll (
    id         INTEGER PRIMARY KEY,
    question   TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE option (
    id       INTEGER PRIMARY KEY,
    poll_id  INTEGER NOT NULL REFERENCES poll(id) ON DELETE CASCADE,
    label    TEXT NOT NULL,
    position INTEGER NOT NULL          -- 0부터, 입력 순서
);

CREATE TABLE vote (
    id         INTEGER PRIMARY KEY,
    option_id  INTEGER NOT NULL REFERENCES option(id) ON DELETE CASCADE,
    nickname   TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- `poll` 테이블에는 행이 최대 1개만 있다.
- 새 투표를 만들 때는 한 트랜잭션 안에서 `DELETE FROM poll`(CASCADE로 option, vote도 삭제)을 실행한 뒤 새로 INSERT한다.
- 연결할 때마다 `PRAGMA foreign_keys = ON`을 실행한다.

## 5. 라우트

| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | `/` | 투표가 있으면 `/vote`, 없으면 `/create`로 리다이렉트 |
| GET | `/create` | 투표 만들기 폼. 기존 투표가 있으면 "기존 투표와 결과가 삭제됩니다" 경고 표시 |
| POST | `/create` | 검증 후 저장하고 `/vote`로 리다이렉트. 실패하면 400과 함께 폼을 다시 렌더링(입력값 유지, 오류 메시지) |
| GET | `/vote` | 질문, 선택지 라디오 버튼, 닉네임 입력칸, 결과 보기 링크. 투표가 없으면 `/create`로 리다이렉트 |
| POST | `/vote` | 검증 후 vote INSERT하고 `/results`로 리다이렉트. 실패하면 400과 함께 폼을 다시 렌더링 |
| GET | `/results` | 결과 표. 투표가 없으면 `/create`로 리다이렉트 |

POST 성공 뒤에는 항상 303 리다이렉트를 돌려준다(Post/Redirect/Get). 새로고침해도 중복 제출되지 않게 하기 위해서다.

## 6. 폼 필드와 검증

### POST /create

| 필드 | 규칙 | 오류 메시지 |
|---|---|---|
| `question` | 앞뒤 공백을 제거한 뒤 1~200자 | "질문을 입력하세요." / "질문은 200자 이하로 입력하세요." |
| `option` (최대 5개, 같은 name) | 각 항목의 앞뒤 공백을 제거하고 빈 항목을 버린 뒤 2~5개. 각 1~100자 | "선택지는 2개 이상 5개 이하로 입력하세요." / "선택지는 100자 이하로 입력하세요." |

- 폼에는 선택지 입력칸 5개를 고정으로 둔다. 위 2개는 `required` 속성을 준다.
- 같은 내용의 선택지가 중복되면 거부한다: "같은 선택지가 중복되었습니다."

### POST /vote

| 필드 | 규칙 | 오류 메시지 |
|---|---|---|
| `nickname` | 앞뒤 공백을 제거한 뒤 1~20자 | "닉네임을 입력하세요." / "닉네임은 20자 이하로 입력하세요." |
| `option_id` | 현재 투표에 속한 option의 id | "선택지를 골라주세요." |

- 같은 닉네임으로 여러 번 투표할 수 있다(중복 허용).
- 브라우저 검증(`required`)이 있더라도 서버에서 반드시 다시 검증한다.

## 7. 결과 계산과 표시

선택지마다 다음을 계산한다.

- 득표수 = 해당 option의 vote 행 수
- 비율 = 득표수 / 총 투표수 × 100, 소수점 첫째 자리에서 반올림(예: `33.3%`). 총 투표수가 0이면 모두 `0.0%`
- 투표자 = 해당 option의 nickname 목록, 투표한 순서대로 쉼표로 구분. 같은 닉네임이 여러 번 나올 수 있다.

표 형식:

| 선택지 | 득표수 | 비율 | 투표자 |
|---|---|---|---|
| 짜장면 | 3 | 60.0% | 민수, 지원, 현우 |
| 짬뽕 | 2 | 40.0% | 서연, 민수 |

- 행 순서는 선택지를 입력한 순서(`position`)를 따른다. 득표순으로 정렬하지 않는다.
- 표 아래에 "총 N표"를 표시한다.
- 투표가 0건이면 표는 그대로 보여주고, 투표자 칸은 `-`로 표시한다.
- 결과 페이지에 "투표하러 가기" 링크와 "새 투표 만들기" 링크를 둔다.

## 8. 보안과 기본 처리

- 모든 사용자 입력은 Jinja2 자동 이스케이프로 출력한다(`|safe` 사용 금지).
- SQL은 항상 `?` 파라미터 바인딩을 사용한다.
- CSRF 보호는 v1에서 생략한다(로그인이 없고 로컬 실습용이기 때문).

## 9. 인수 조건

1. 투표가 없는 상태에서 `/`에 접속하면 `/create`로 이동한다.
2. 질문과 선택지 2개를 입력해 만들면 `/vote`에 질문과 선택지 2개가 보인다.
3. 선택지를 1개만 채우거나 6개 이상 보내면 400과 오류 메시지가 표시되고, 아무것도 저장되지 않는다.
4. 닉네임 없이 투표하면 400과 "닉네임을 입력하세요."가 표시된다.
5. 다른 투표의 option_id나 존재하지 않는 option_id로 투표하면 400이 반환된다.
6. "민수"가 A에, "지원"이 A에, "서연"이 B에 투표하면 결과는 A 2표 66.7% "민수, 지원", B 1표 33.3% "서연", 총 3표다.
7. 같은 닉네임으로 두 번 투표하면 두 표 모두 집계된다.
8. 새 투표를 만들면 이전 질문, 선택지, 투표 기록이 모두 사라진다.
9. 닉네임에 `<script>`를 입력해도 결과 페이지에 문자 그대로 표시된다.
10. 투표 직후 결과 페이지에서 새로고침해도 표가 추가되지 않는다.

## 10. 실행 방법

```
pip install -r requirements.txt
flask --app app init-db   # 스키마 생성
flask --app app run
```

테스트: `pytest` (Flask test client와 임시 DB 파일을 사용한다)

---

## 11. v2 추가 기능

v1에서 제외했던 마감과 그래프를 추가하고, 화면에 만든 사람 이름을 표시한다.

### 11.1 투표 마감 시간

- `poll.closes_at TEXT`: `YYYY-MM-DDTHH:MM`, 서버 현지 시각. `NULL`이면 마감 없음.
- `/create` 폼에 `datetime-local` 입력칸(`closes_at`)을 선택 항목으로 추가한다.
  - 형식이 틀리면 400, "마감 시간 형식이 올바르지 않습니다."
  - 현재 시각 이전이면 400, "마감 시간은 현재 시각 이후로 설정하세요."
- 현재 시각이 `closes_at` 이후이면 마감된 것으로 본다.
  - `GET /vote`: 투표 폼 대신 "투표가 마감되었습니다." 표시
  - `POST /vote`: 403, 저장하지 않음
  - `/results`: "마감됨 (시각)" / "진행 중 · 마감 (시각)" / "진행 중 · 마감 없음"
- 예전 DB 파일에 `closes_at` 컬럼이 없으면 앱이 시작할 때 `ALTER TABLE`로 추가한다.

### 11.2 결과 그래프

- 결과 표 위에 가로 막대 그래프를 표시한다. 선택지끼리 비교하기 쉽고, 긴 선택지 이름도 잘리지 않기 때문이다.
- HTML/CSS만 사용한다(`width: N%`). 막대 길이는 비율과 같다.
- 막대 위에 "선택지 이름"과 "N표 · N.N%"를 표시한다.
- 최다 득표 선택지(동점이면 모두)는 강조색으로 표시한다. 0표뿐이면 강조하지 않는다.

### 11.3 만든 사람 이름

- 모든 화면 상단 헤더에 "만든 사람: 안동현"을 표시한다. 이름은 `app.py`의 `AUTHOR_NAME`에서 바꾼다.

### 11.4 코드 리뷰 반영

- `option_id`를 `int()` 변환이 실패하면 거부한다(`²` 같은 유니코드 숫자가 500을 내던 문제).
- 비율은 `Decimal`의 `ROUND_HALF_UP`으로 반올림한다(6.25% → 6.3%).
- 투표 저장 중 선택지가 삭제되어 `IntegrityError`가 나면 `/vote`로 303 리다이렉트한다.
