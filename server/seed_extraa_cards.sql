-- Seeds the one profile the MVP ships with. Safe to re-run: it will not
-- overwrite a profile you have since edited through the admin UI.
--
--   psql "$DATABASE_URL" -f server/seed_extraa_cards.sql
--
-- This is the same configuration as profiles/extraa_cards.json, which stays in
-- the app as the offline fallback.

INSERT INTO qr_profiles (
    id, name, renderer, required_columns,
    qr_content, top_text, bottom_text, filename,
    output_format, unique_columns, validation, active, created_by, updated_by,
    name_font, code_font, name_size, code_size, name_tracking, code_tracking
) VALUES (
    'extraa_cards',
    'Extraa Cards',
    'standard',
    '["name", "qr_code"]'::jsonb,
    'https://www.extraacards.com/cards/{qr_code}',
    '{name}',
    '{qr_code}',
    '{qr_code}.png',
    -- 'jpeg' is deliberate. The reference renderer encodes JPEG into a .png
    -- filename; see docs/PROFILE_MAPPING.md. Changing this changes every card.
    'jpeg',
    '["qr_code"]'::jsonb,
    '{"qr_code": {"length": 6, "charset": "alnum"}}'::jsonb,
    true,
    'seed',
    'seed',
    -- Roboto at 48/80. The historical cards were Geist Mono at 36/60; see
    -- docs/PROFILE_MAPPING.md for why that changed.
    'rob.ttf', 'rob.ttf', 48, 80, 5, 0
)
ON CONFLICT (id) DO NOTHING;

SELECT id, name, version, active, name_font, name_size, code_size
FROM qr_profiles WHERE id = 'extraa_cards';
