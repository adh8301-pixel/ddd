-- Vercel 배포용 Postgres 스키마. schema.sql(SQLite)과 같은 구조다.
-- 서버가 켜질 때마다 실행되므로 기존 데이터를 지우지 않는다.

CREATE TABLE IF NOT EXISTS poll (
    id         SERIAL PRIMARY KEY,
    question   TEXT NOT NULL,
    closes_at  TEXT,                   -- 'YYYY-MM-DDTHH:MM' 한국 시각, NULL이면 마감 없음
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS option (
    id       SERIAL PRIMARY KEY,
    poll_id  INTEGER NOT NULL REFERENCES poll(id) ON DELETE CASCADE,
    label    TEXT NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS vote (
    id         SERIAL PRIMARY KEY,
    option_id  INTEGER NOT NULL REFERENCES option(id) ON DELETE CASCADE,
    nickname   TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
