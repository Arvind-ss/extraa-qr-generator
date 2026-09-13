-- Migration for a database where server/schema.sql was already run before
-- 2026-09-13. Adds the printed text columns. Safe to run more than once, and
-- safe to skip entirely if you have not created the tables yet -- schema.sql
-- already contains everything below.
--
--   psql "$DATABASE_URL" -f server/migration_001_printed_text.sql

BEGIN;

ALTER TABLE qr_profiles
    ADD COLUMN IF NOT EXISTS name_font     text    NOT NULL DEFAULT 'rob.ttf',
    ADD COLUMN IF NOT EXISTS code_font     text    NOT NULL DEFAULT 'rob.ttf',
    ADD COLUMN IF NOT EXISTS name_size     integer NOT NULL DEFAULT 48,
    ADD COLUMN IF NOT EXISTS code_size     integer NOT NULL DEFAULT 80,
    ADD COLUMN IF NOT EXISTS name_tracking integer NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS code_tracking integer NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'qr_profiles_sizes_are_sane') THEN
        ALTER TABLE qr_profiles
            ADD CONSTRAINT qr_profiles_sizes_are_sane
            CHECK (name_size BETWEEN 12 AND 160
                   AND code_size BETWEEN 12 AND 160),
            ADD CONSTRAINT qr_profiles_tracking_is_sane
            CHECK (name_tracking BETWEEN -10 AND 40
                   AND code_tracking BETWEEN -10 AND 40),
            ADD CONSTRAINT qr_profiles_fonts_are_filenames
            CHECK (name_font !~ '[/\\]' AND code_font !~ '[/\\]'
                   AND name_font NOT LIKE '%..%' AND code_font NOT LIKE '%..%');
    END IF;
END
$$;

COMMIT;

-- After running this, re-track the table in Hasura (Data -> qr_profiles ->
-- Modify -> the new columns need adding to the qr_support select permission).
SELECT id, name, name_font, name_size, code_size, name_tracking
FROM qr_profiles;
