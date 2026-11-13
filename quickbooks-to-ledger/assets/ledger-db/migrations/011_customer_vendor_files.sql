-- Modules can also hand each other customer and vendor lists (e.g. from a
-- migration out of other bookkeeping software).
ALTER TABLE module_files DROP CONSTRAINT module_files_kind;
ALTER TABLE module_files ADD CONSTRAINT module_files_kind CHECK (kind IN ('transaction', 'receipt', 'statement', 'bill', 'customer', 'vendor'));
