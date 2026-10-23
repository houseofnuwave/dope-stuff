CREATE TABLE IF NOT EXISTS photo_write_intents (
 target_key TEXT NOT NULL,
 file_path TEXT NOT NULL,
 operation_id TEXT NOT NULL,
 phase TEXT NOT NULL CHECK(phase IN ('staging','cleanup')),
 created_at BIGINT NOT NULL,
 next_attempt_at BIGINT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT '',
 PRIMARY KEY (target_key, file_path)
);
CREATE INDEX IF NOT EXISTS idx_photo_write_operation
 ON photo_write_intents(target_key,operation_id);
CREATE INDEX IF NOT EXISTS idx_photo_write_retry
 ON photo_write_intents(target_key,phase,next_attempt_at,created_at);
CREATE INDEX IF NOT EXISTS idx_item_photos_path ON item_photos(file_path);
CREATE INDEX IF NOT EXISTS idx_items_photo_path ON items(photo_path);
