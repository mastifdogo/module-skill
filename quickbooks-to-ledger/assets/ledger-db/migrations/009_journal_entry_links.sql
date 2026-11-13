-- Links from journal entries to the module records they came from or belong
-- to (an invoice, a bank transaction, a bill). Entries stay immutable; links
-- can be added later and removed by the module that made them.
CREATE TABLE journal_entry_links (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id   BIGINT      NOT NULL REFERENCES journal_entries (id) ON DELETE RESTRICT,
    module_id  TEXT        NOT NULL,
    -- The module's own key for the record, e.g. "invoice:31".
    ref        TEXT        NOT NULL,
    label      TEXT        NOT NULL,
    -- Where the record opens in Ledger, e.g. "/apps/sales?invoice=31" ('' for none).
    href       TEXT        NOT NULL DEFAULT '',
    created_by BIGINT      REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT journal_entry_links_unique UNIQUE (entry_id, module_id, ref),
    CONSTRAINT journal_entry_links_module CHECK (module_id ~ '^[a-z][a-z0-9-]{1,31}$'),
    CONSTRAINT journal_entry_links_ref CHECK (length(ref) BETWEEN 1 AND 200),
    CONSTRAINT journal_entry_links_label CHECK (length(btrim(label)) BETWEEN 1 AND 200),
    CONSTRAINT journal_entry_links_href CHECK (href = '' OR (href ~ '^/[^/\\]' AND length(href) <= 500))
);
CREATE INDEX journal_entry_links_ref_idx ON journal_entry_links (module_id, ref);
