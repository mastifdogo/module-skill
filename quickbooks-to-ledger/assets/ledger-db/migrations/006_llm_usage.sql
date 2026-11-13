-- One row per call to the AI provider set under Settings → AI, by Ledger or
-- a module, for the usage table there. Old rows are pruned by the app.
CREATE TABLE llm_usage (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        TEXT        NOT NULL,
    provider      TEXT        NOT NULL,
    model         TEXT        NOT NULL DEFAULT '',
    input_tokens  INTEGER,
    output_tokens INTEGER,
    ok            BOOLEAN     NOT NULL,
    error         TEXT        NOT NULL DEFAULT '',
    duration_ms   INTEGER     NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX llm_usage_created_idx ON llm_usage (created_at);
