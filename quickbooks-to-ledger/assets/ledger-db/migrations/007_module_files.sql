-- Files modules hand to each other (ctx.files): bank statements, bills,
-- receipts, transaction lists. Nothing is posted to the books; the receiving
-- module decides what to do and records the outcome.
CREATE TABLE module_files (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender       TEXT        NOT NULL,
    recipient    TEXT        NOT NULL,
    kind         TEXT        NOT NULL,
    filename     TEXT        NOT NULL,
    content_type TEXT        NOT NULL DEFAULT 'application/octet-stream',
    size_bytes   INTEGER     NOT NULL,
    sha256       TEXT        NOT NULL,
    data         BYTEA       NOT NULL,
    meta         JSONB       NOT NULL DEFAULT '{}',
    note         TEXT        NOT NULL DEFAULT '',
    status       TEXT        NOT NULL DEFAULT 'new',
    result       TEXT        NOT NULL DEFAULT '',
    created_by   BIGINT      REFERENCES users (id) ON DELETE RESTRICT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT module_files_kind CHECK (kind IN ('transaction', 'receipt', 'statement', 'bill')),
    CONSTRAINT module_files_status CHECK (status IN ('new', 'accepted', 'done', 'rejected')),
    CONSTRAINT module_files_parties CHECK (sender ~ '^[a-z][a-z0-9-]{1,31}$' AND recipient ~ '^[a-z][a-z0-9-]{1,31}$'),
    CONSTRAINT module_files_filename CHECK (length(filename) BETWEEN 1 AND 255),
    CONSTRAINT module_files_size CHECK (size_bytes = octet_length(data)),
    CONSTRAINT module_files_meta CHECK (jsonb_typeof(meta) = 'object' AND length(meta::text) <= 16384),
    CONSTRAINT module_files_text CHECK (length(note) <= 2000 AND length(result) <= 2000)
);
CREATE INDEX module_files_inbox_idx ON module_files (recipient, status, created_at DESC);
CREATE INDEX module_files_outbox_idx ON module_files (sender, created_at DESC);
