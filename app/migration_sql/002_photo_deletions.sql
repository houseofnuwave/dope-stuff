CREATE TABLE IF NOT EXISTS photo_deletions (
 target_key TEXT NOT NULL,
 file_path TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 last_attempt_at BIGINT NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT '',
 PRIMARY KEY (target_key, file_path)
);
CREATE INDEX IF NOT EXISTS idx_photo_deletions_retry
 ON photo_deletions(target_key, last_attempt_at, created_at);
