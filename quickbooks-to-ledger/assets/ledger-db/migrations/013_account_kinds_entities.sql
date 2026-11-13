-- Account tags, a shared list of entities, and who an entry is with.

-- What a bank-type account is, for pickers and modules: chequing and savings
-- are asset accounts, a credit card is a liability.
ALTER TABLE accounts ADD COLUMN kind TEXT;
ALTER TABLE accounts ADD CONSTRAINT accounts_kind CHECK (
    kind IS NULL
    OR (kind IN ('chequing', 'savings') AND type = 'asset')
    OR (kind = 'credit_card' AND type = 'liability'));

-- Entities: the people and businesses the books deal with. One list shared
-- by Ledger and every module; each is a customer, a vendor, or both.
CREATE TABLE entities (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT        NOT NULL,
    is_customer BOOLEAN     NOT NULL DEFAULT FALSE,
    is_vendor   BOOLEAN     NOT NULL DEFAULT FALSE,
    email       TEXT        NOT NULL DEFAULT '',
    phone       TEXT        NOT NULL DEFAULT '',
    address     TEXT        NOT NULL DEFAULT '',
    notes       TEXT        NOT NULL DEFAULT '',
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT entities_name_length CHECK (length(btrim(name)) BETWEEN 1 AND 200 AND name = btrim(name)),
    CONSTRAINT entities_role CHECK (is_customer OR is_vendor)
);
CREATE UNIQUE INDEX entities_name_unique ON entities (lower(name));

-- The vendor an expense was paid to, or the customer an entry is about.
ALTER TABLE journal_entries ADD COLUMN entity_id BIGINT REFERENCES entities (id) ON DELETE RESTRICT;
CREATE INDEX journal_entries_entity_idx ON journal_entries (entity_id) WHERE entity_id IS NOT NULL;

-- Modules can hand each other entity lists (customers, vendors or both).
ALTER TABLE module_files DROP CONSTRAINT module_files_kind;
ALTER TABLE module_files ADD CONSTRAINT module_files_kind CHECK (kind IN ('transaction', 'receipt', 'statement', 'bill', 'customer', 'vendor', 'entity'));
