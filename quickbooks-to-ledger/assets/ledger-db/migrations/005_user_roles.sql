-- Roles for multi-user use:
--   admin       everything, including users, modules, backups, updates, AI and Gmail
--   bookkeeper  works in the books (entries, accounts, reconciliation, imports)
--   viewer      read-only
-- Existing users become admins (they could do everything before).
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin';
ALTER TABLE users ADD CONSTRAINT users_role CHECK (role IN ('admin', 'bookkeeper', 'viewer'));
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'bookkeeper';
