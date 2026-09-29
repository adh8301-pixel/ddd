DROP TABLE IF EXISTS vote;
DROP TABLE IF EXISTS option;
DROP TABLE IF EXISTS poll;

CREATE TABLE poll (
    id         INTEGER PRIMARY KEY,
    question   TEXT NOT NULL,
    closes_at  TEXT,                   -- 'YYYY-MM-DDTHH:MM' 서버 현지 시각, NULL이면 마감 없음
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE option (
    id       INTEGER PRIMARY KEY,
    poll_id  INTEGER NOT NULL REFERENCES poll(id) ON DELETE CASCADE,
    label    TEXT NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE vote (
    id         INTEGER PRIMARY KEY,
    option_id  INTEGER NOT NULL REFERENCES option(id) ON DELETE CASCADE,
    nickname   TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
