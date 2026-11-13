-- Values of the settings modules declare in ledger-module.json ("settings").
-- Secret fields (API keys) are stored here too, so they are in backups.
CREATE TABLE module_settings (
    module_id  TEXT        PRIMARY KEY,
    "values"   JSONB       NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by BIGINT      REFERENCES users (id) ON DELETE SET NULL,

    CONSTRAINT module_settings_id_format CHECK (module_id ~ '^[a-z][a-z0-9-]{1,31}$'),
    CONSTRAINT module_settings_object CHECK (jsonb_typeof("values") = 'object')
);
