-- Reconciling an account against a bank or card statement. A reconciliation
-- marks journal lines (transactions) as cleared; once finished, those lines
-- are the account's reconciled balance. Posted lines themselves never change.
CREATE TABLE reconciliations (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id              BIGINT      NOT NULL REFERENCES accounts (id) ON DELETE RESTRICT,
    statement_date          DATE        NOT NULL,
    -- In the account's natural sign (what the statement shows).
    statement_balance_cents BIGINT      NOT NULL,
    status                  TEXT        NOT NULL DEFAULT 'open',
    created_by              BIGINT      REFERENCES users (id) ON DELETE RESTRICT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_by             BIGINT      REFERENCES users (id) ON DELETE RESTRICT,
    finished_at             TIMESTAMPTZ,

    CONSTRAINT reconciliations_status CHECK (status IN ('open', 'finished')),
    CONSTRAINT reconciliations_finished CHECK ((status = 'finished') = (finished_at IS NOT NULL))
);

-- At most one reconciliation in progress per account.
CREATE UNIQUE INDEX reconciliations_one_open ON reconciliations (account_id) WHERE status = 'open';
CREATE INDEX reconciliations_account_idx ON reconciliations (account_id, statement_date DESC);

CREATE TABLE reconciliation_lines (
    reconciliation_id BIGINT NOT NULL REFERENCES reconciliations (id) ON DELETE CASCADE,
    transaction_id    BIGINT NOT NULL REFERENCES transactions (id) ON DELETE RESTRICT,

    PRIMARY KEY (reconciliation_id, transaction_id),
    -- A line is cleared on one statement only.
    CONSTRAINT reconciliation_lines_once UNIQUE (transaction_id)
);
