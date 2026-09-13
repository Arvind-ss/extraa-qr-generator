-- Shared QR generation profiles.
--
-- Run this yourself against the DigitalOcean managed Postgres. It creates two
-- tables, one trigger, and two roles. It touches nothing that already exists.
--
--   psql "$DATABASE_URL" -f server/schema.sql
--
-- Then track qr_profiles in Hasura and apply the permissions described in
-- server/README.md. Read that file before granting anything -- there is a
-- credential decision in it that has to be made deliberately.

BEGIN;

CREATE TABLE IF NOT EXISTS qr_profiles (
    id               text PRIMARY KEY,
    name             text NOT NULL UNIQUE,

    -- Key into the renderer registry in qrgen/renderers/__init__.py. Left
    -- unconstrained on purpose: adding a renderer is a code change, and a CHECK
    -- here would turn it into a migration too. The app rejects unknown values
    -- on load, so a bad row cannot render anything.
    renderer         text NOT NULL DEFAULT 'standard',

    required_columns jsonb NOT NULL,
    qr_content       text NOT NULL,
    top_text         text,
    bottom_text      text NOT NULL,
    filename         text NOT NULL,
    output_format    text NOT NULL DEFAULT 'jpeg',
    unique_columns   jsonb NOT NULL DEFAULT '[]'::jsonb,
    validation       jsonb NOT NULL DEFAULT '{}'::jsonb,

    active           boolean NOT NULL DEFAULT true,
    version          integer NOT NULL DEFAULT 1,

    -- Printed text style. Plain numbers and a font filename; the application
    -- refuses any font name that is not a bare file in its bundled font
    -- directory, so this can never become a path.
    name_font        text    NOT NULL DEFAULT 'rob.ttf',
    code_font        text    NOT NULL DEFAULT 'rob.ttf',
    name_size        integer NOT NULL DEFAULT 48,
    code_size        integer NOT NULL DEFAULT 80,
    name_tracking    integer NOT NULL DEFAULT 5,
    code_tracking    integer NOT NULL DEFAULT 0,

    created_by       text,
    updated_by       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),

    -- A filename template that is a path is how you get ../../ into an
    -- extraction root. The app checks this too; this is the backstop for
    -- anything that writes to the table without going through the app.
    CONSTRAINT qr_profiles_filename_is_not_a_path
        CHECK (filename !~ '[/\\]' AND filename NOT LIKE '%..%'),
    CONSTRAINT qr_profiles_columns_is_array
        CHECK (jsonb_typeof(required_columns) = 'array'
               AND jsonb_array_length(required_columns) > 0),
    CONSTRAINT qr_profiles_unique_columns_is_array
        CHECK (jsonb_typeof(unique_columns) = 'array'),
    -- Same bounds the application enforces, so a row written by anything else
    -- still cannot produce a card Pillow refuses to draw.
    CONSTRAINT qr_profiles_sizes_are_sane
        CHECK (name_size BETWEEN 12 AND 160 AND code_size BETWEEN 12 AND 160),
    CONSTRAINT qr_profiles_tracking_is_sane
        CHECK (name_tracking BETWEEN -10 AND 40
               AND code_tracking BETWEEN -10 AND 40),
    CONSTRAINT qr_profiles_fonts_are_filenames
        CHECK (name_font !~ '[/\\]' AND code_font !~ '[/\\]'
               AND name_font NOT LIKE '%..%' AND code_font NOT LIKE '%..%')
);

-- Every version ever saved. Approval tokens bind to (profile, version), so a
-- batch can always be traced back to the exact configuration that produced it.
CREATE TABLE IF NOT EXISTS qr_profile_versions (
    profile_id  text        NOT NULL,
    version     integer     NOT NULL,
    config      jsonb       NOT NULL,
    changed_by  text,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, version)
);

CREATE INDEX IF NOT EXISTS qr_profile_versions_profile_idx
    ON qr_profile_versions (profile_id, changed_at DESC);

-- Version bumping lives in the database, not the client. Two admins saving the
-- same profile from two machines cannot both write version 4.
CREATE OR REPLACE FUNCTION qr_profiles_audit() RETURNS trigger AS $$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        NEW.version    := OLD.version + 1;
        NEW.created_at := OLD.created_at;
        NEW.created_by := OLD.created_by;
        NEW.updated_at := now();
    END IF;

    INSERT INTO qr_profile_versions (profile_id, version, config, changed_by)
    VALUES (NEW.id, NEW.version, to_jsonb(NEW), NEW.updated_by);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS qr_profiles_audit_trg ON qr_profiles;
CREATE TRIGGER qr_profiles_audit_trg
    BEFORE INSERT OR UPDATE ON qr_profiles
    FOR EACH ROW EXECUTE FUNCTION qr_profiles_audit();

-- Two roles, so a leaked support credential cannot rewrite a profile and a
-- leaked credential of either kind cannot read the cards, users, or phone
-- numbers living in the rest of this database.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qr_profile_reader') THEN
        CREATE ROLE qr_profile_reader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qr_profile_writer') THEN
        CREATE ROLE qr_profile_writer NOLOGIN;
    END IF;
END
$$;

GRANT SELECT                     ON qr_profiles         TO qr_profile_reader;
GRANT SELECT                     ON qr_profile_versions TO qr_profile_reader;
GRANT SELECT, INSERT, UPDATE     ON qr_profiles         TO qr_profile_writer;
GRANT SELECT, INSERT             ON qr_profile_versions TO qr_profile_writer;

-- No DELETE is granted to anybody. Profiles are deactivated, never removed:
-- a batch generated last year must still be explicable.

COMMIT;
