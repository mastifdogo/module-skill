-- Per-user preferences. sidebar: [{"id": "core:journal", "hidden": false}, ...]
-- in display order; items not listed (e.g. a newly installed module) are
-- shown after the listed ones.
CREATE TABLE user_settings (
    user_id    BIGINT      PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    sidebar    JSONB       NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT user_settings_sidebar_array CHECK (jsonb_typeof(sidebar) = 'array')
);
