-- From 0.2.0 the module's configuration lives in Ledger's settings form
-- (ledger-module.json "settings"). This table keeps only what a form can't
-- hold: the running document numbers. Its other columns stay so the
-- module can copy the values across once (moved_to_ledger_settings), then
-- they are no longer read.
ALTER TABLE settings ADD COLUMN moved_to_ledger_settings boolean NOT NULL DEFAULT false;

-- Which taxes new lines get by default is now a flag on each tax.
ALTER TABLE taxes ADD COLUMN is_default boolean NOT NULL DEFAULT false;
UPDATE taxes t SET is_default = true FROM settings s WHERE t.id = ANY(s.default_tax_ids);

-- For Ledger's search bar.
CREATE INDEX documents_number_idx ON documents (lower(number));
CREATE INDEX customers_company_idx ON customers (lower(company));
