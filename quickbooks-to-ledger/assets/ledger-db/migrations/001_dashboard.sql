-- Dashboard notifications and to-dos, posted by modules (and by Ledger
-- itself, e.g. the updater). Unlike the books these rows are not
-- immutable: they are opened, updated, dismissed/done and cleaned up.
--
-- Migrations run once each, as the owner role, inside a transaction (so no
-- BEGIN/COMMIT here). The app role's grants live in db/grants.sql, which is
-- re-applied after migrations.

CREATE TABLE dashboard_items (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Who posted it: a module id, or 'ledger'.
    source     TEXT        NOT NULL,
    kind       TEXT        NOT NULL,
    -- The poster's own identifier, so re-posting updates instead of duplicating.
    key        TEXT        NOT NULL,
    title      TEXT        NOT NULL,
    body       TEXT        NOT NULL DEFAULT '',
    level      TEXT        NOT NULL DEFAULT 'info',
    -- A link inside Ledger, e.g. /apps/invoicing.
    link       TEXT        NOT NULL DEFAULT '',
    due_date   DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    -- Dismissed (notification) or done (to-do), and by whom.
    closed_at  TIMESTAMPTZ,
    closed_by  BIGINT      REFERENCES users (id) ON DELETE RESTRICT,

    CONSTRAINT dashboard_items_source_format CHECK (source ~ '^[a-z][a-z0-9-]{1,31}$'),
    CONSTRAINT dashboard_items_kind          CHECK (kind IN ('notification', 'todo')),
    CONSTRAINT dashboard_items_key_length    CHECK (length(key) BETWEEN 1 AND 100),
    CONSTRAINT dashboard_items_title_length  CHECK (length(btrim(title)) BETWEEN 1 AND 200),
    CONSTRAINT dashboard_items_body_length   CHECK (length(body) <= 2000),
    CONSTRAINT dashboard_items_level         CHECK (level IN ('info', 'success', 'warning', 'danger')),
    CONSTRAINT dashboard_items_link_local    CHECK (link = '' OR (link ~ '^/' AND link !~ '^//' AND link !~ '^/\\' AND length(link) <= 300)),
    CONSTRAINT dashboard_items_unique_key    UNIQUE (source, kind, key)
);

CREATE INDEX dashboard_items_open_idx ON dashboard_items (kind, closed_at, created_at DESC);
