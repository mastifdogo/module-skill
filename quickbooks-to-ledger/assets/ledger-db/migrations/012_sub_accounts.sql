-- Sub-accounts: an account may sit under a parent of the same type and
-- currency (so a parent's total is one kind of balance in one currency).
-- Both a parent and its sub-accounts can be posted to. Reports show the
-- hierarchy with a total for each parent.

ALTER TABLE accounts ADD COLUMN parent_id BIGINT REFERENCES accounts (id) ON DELETE RESTRICT;
ALTER TABLE accounts ADD CONSTRAINT accounts_parent_not_self CHECK (parent_id <> id);
CREATE INDEX accounts_parent_idx ON accounts (parent_id) WHERE parent_id IS NOT NULL;

CREATE FUNCTION trg_accounts_parent() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    p     accounts%ROWTYPE;
    up    BIGINT;
    depth INT := 1;
BEGIN
    IF NEW.parent_id IS NOT NULL THEN
        SELECT * INTO p FROM accounts WHERE id = NEW.parent_id;
        IF p.type <> NEW.type OR p.currency <> NEW.currency THEN
            RAISE EXCEPTION 'account % must have the same type and currency as its parent %', NEW.code, p.code
                  USING ERRCODE = 'check_violation', CONSTRAINT = 'accounts_parent_same_kind';
        END IF;
        -- Walk up: no loops, and at most 5 levels.
        up := NEW.parent_id;
        WHILE up IS NOT NULL LOOP
            IF up = NEW.id THEN
                RAISE EXCEPTION 'account % cannot be under one of its own sub-accounts', NEW.code
                      USING ERRCODE = 'check_violation', CONSTRAINT = 'accounts_parent_no_cycle';
            END IF;
            depth := depth + 1;
            IF depth > 5 THEN
                RAISE EXCEPTION 'accounts can be nested at most 5 levels deep'
                      USING ERRCODE = 'check_violation', CONSTRAINT = 'accounts_parent_depth';
            END IF;
            SELECT parent_id INTO up FROM accounts WHERE id = up;
        END LOOP;
    END IF;
    -- A parent's type and currency can't drift away from its sub-accounts'.
    IF TG_OP = 'UPDATE' AND (NEW.type <> OLD.type OR NEW.currency <> OLD.currency)
       AND EXISTS (SELECT 1 FROM accounts c WHERE c.parent_id = NEW.id AND (c.type <> NEW.type OR c.currency <> NEW.currency)) THEN
        RAISE EXCEPTION 'account % has sub-accounts; its type and currency cannot be changed', NEW.code
              USING ERRCODE = 'check_violation', CONSTRAINT = 'accounts_parent_same_kind';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER accounts_parent
    BEFORE INSERT OR UPDATE OF parent_id, type, currency ON accounts
    FOR EACH ROW EXECUTE FUNCTION trg_accounts_parent();
