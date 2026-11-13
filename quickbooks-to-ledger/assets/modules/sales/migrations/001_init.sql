-- Runs once, as the module's own role, in its own schema (mod_sales).
-- Money is integer cents. Quantities are thousandths (1.5 = 1500) and tax
-- rates thousandths of a percent (5% = 5000), so all arithmetic is exact.

-- Sales taxes. A line can carry several (e.g. GST + PST). `accounts` maps a
-- currency to the liability account the tax is posted to: {"CAD": "2200"}.
CREATE TABLE taxes (
    id        bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      text    NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 30),
    rate      int     NOT NULL CHECK (rate BETWEEN 0 AND 100000),
    accounts  jsonb   NOT NULL DEFAULT '{}',
    active    boolean NOT NULL DEFAULT true,
    position  int     NOT NULL DEFAULT 0
);
INSERT INTO taxes (name, rate, active, position) VALUES
    ('GST', 5000, true, 1),
    ('HST', 13000, false, 2),
    ('HST 15%', 15000, false, 3),
    ('PST', 7000, false, 4),
    ('QST', 9975, false, 5);

-- Sales categories. Each tracks to a revenue account per currency:
-- {"CAD": "4000", "USD": "4010"}. `tax_ids` (optional) are the taxes new
-- lines in this category get, e.g. none for zero-rated sales.
CREATE TABLE categories (
    id          bigint   GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text     NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 100),
    description text     NOT NULL DEFAULT '',
    accounts    jsonb    NOT NULL DEFAULT '{}',
    tax_ids     int[],
    active      boolean  NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE settings (
    id                    int     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    business_name         text    NOT NULL DEFAULT '',
    business_address      text    NOT NULL DEFAULT '',
    business_email        text    NOT NULL DEFAULT '',
    business_phone        text    NOT NULL DEFAULT '',
    tax_id                text    NOT NULL DEFAULT '',
    tax_id_label          text    NOT NULL DEFAULT 'GST/HST No.',
    invoice_prefix        text    NOT NULL DEFAULT 'INV-',
    next_invoice_number   int     NOT NULL DEFAULT 1 CHECK (next_invoice_number > 0),
    quote_prefix          text    NOT NULL DEFAULT 'QUO-',
    next_quote_number     int     NOT NULL DEFAULT 1 CHECK (next_quote_number > 0),
    estimate_prefix       text    NOT NULL DEFAULT 'EST-',
    next_estimate_number  int     NOT NULL DEFAULT 1 CHECK (next_estimate_number > 0),
    default_currency      text    NOT NULL DEFAULT 'CAD' CHECK (default_currency IN ('CAD', 'USD')),
    default_terms_days    int     NOT NULL DEFAULT 30 CHECK (default_terms_days BETWEEN 0 AND 365),
    quote_valid_days      int     NOT NULL DEFAULT 30 CHECK (quote_valid_days BETWEEN 0 AND 365),
    estimate_valid_days   int     NOT NULL DEFAULT 30 CHECK (estimate_valid_days BETWEEN 0 AND 365),
    default_tax_ids       int[]    NOT NULL DEFAULT '{}',
    footer                text    NOT NULL DEFAULT '',
    quote_terms           text    NOT NULL DEFAULT 'Prices are fixed until the date above. To accept, reply to this email.',
    estimate_terms        text    NOT NULL DEFAULT 'This is an estimate, not a fixed price. The final invoice may differ.',
    -- Ledger posting: {"CAD": {"receivable": "1200", "revenue": "4000", "bank": "1000"}, "USD": {...}}.
    -- "revenue" is used for lines without a category (or whose category has no account for the currency).
    post_to_ledger        boolean NOT NULL DEFAULT false,
    accounts              jsonb   NOT NULL DEFAULT '{}',
    -- Outgoing mail (SMTP)
    smtp_host             text    NOT NULL DEFAULT '',
    smtp_port             int     NOT NULL DEFAULT 587 CHECK (smtp_port BETWEEN 1 AND 65535),
    smtp_security         text    NOT NULL DEFAULT 'starttls' CHECK (smtp_security IN ('tls', 'starttls', 'none')),
    smtp_username         text    NOT NULL DEFAULT '',
    smtp_password         text    NOT NULL DEFAULT '',
    from_name             text    NOT NULL DEFAULT '',
    from_email            text    NOT NULL DEFAULT '',
    reply_to              text    NOT NULL DEFAULT '',
    bcc_self              boolean NOT NULL DEFAULT false,
    email_subject         text    NOT NULL DEFAULT 'Invoice {{number}} from {{business}}',
    email_body            text    NOT NULL DEFAULT E'Hello {{customer}},\n\nPlease find attached invoice {{number}} for {{total}}, due {{due_date}}.\n\nThank you for your business.\n{{business}}',
    quote_email_subject   text    NOT NULL DEFAULT '{{type}} {{number}} from {{business}}',
    quote_email_body      text    NOT NULL DEFAULT E'Hello {{customer}},\n\nPlease find attached {{type_lower}} {{number}} for {{total}}, valid until {{due_date}}.\n\nLet us know if you have any questions.\n{{business}}',
    updated_at            timestamptz NOT NULL DEFAULT now()
);
INSERT INTO settings (default_tax_ids) SELECT array_agg(id)::int[] FROM taxes WHERE name = 'GST';

CREATE TABLE customers (
    id          bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text    NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    company     text    NOT NULL DEFAULT '',
    email       text    NOT NULL DEFAULT '',
    cc_emails   text    NOT NULL DEFAULT '',
    phone       text    NOT NULL DEFAULT '',
    address     text    NOT NULL DEFAULT '',
    tax_id      text    NOT NULL DEFAULT '',
    currency    text    NOT NULL DEFAULT 'CAD' CHECK (currency IN ('CAD', 'USD')),
    terms_days  int     CHECK (terms_days BETWEEN 0 AND 365),
    -- Taxes for this customer's lines instead of the defaults (e.g. '{}' for an exempt or foreign customer).
    tax_ids     int[],
    notes       text    NOT NULL DEFAULT '',
    archived    boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX customers_name_idx ON customers (lower(name));

-- Invoices, quotes and estimates. Each kind has its own numbering and statuses:
--   invoice:          draft → (posting) → open → paid, or open → void
--   quote / estimate: draft → sent → accepted / declined; accepted → converted (to an invoice)
-- For quotes and estimates, due_date is the "valid until" date.
CREATE TABLE documents (
    id               bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text    NOT NULL CHECK (kind IN ('invoice', 'quote', 'estimate')),
    number           text    NOT NULL,
    customer_id      bigint  NOT NULL REFERENCES customers (id),
    status           text    NOT NULL DEFAULT 'draft',
    issue_date       date    NOT NULL,
    due_date         date    NOT NULL CHECK (due_date >= issue_date),
    currency         text    NOT NULL CHECK (currency IN ('CAD', 'USD')),
    po_number        text    NOT NULL DEFAULT '',
    notes            text    NOT NULL DEFAULT '',
    subtotal_cents   bigint  NOT NULL DEFAULT 0,
    tax_cents        bigint  NOT NULL DEFAULT 0,
    total_cents      bigint  NOT NULL DEFAULT 0,
    paid_cents       bigint  NOT NULL DEFAULT 0 CHECK (paid_cents >= 0),
    journal_entry_id bigint,
    void_entry_id    bigint,
    source_id        bigint  REFERENCES documents (id),   -- the quote/estimate an invoice came from
    converted_id     bigint  REFERENCES documents (id),   -- the invoice a quote/estimate became
    issued_at        timestamptz,
    sent_at          timestamptz,
    decided_at       timestamptz,
    created_by       text    NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, number),
    CHECK (CASE kind WHEN 'invoice' THEN status IN ('draft', 'posting', 'open', 'paid', 'void')
                     ELSE status IN ('draft', 'sent', 'accepted', 'declined', 'converted') END)
);
CREATE INDEX documents_customer_idx ON documents (customer_id);
CREATE INDEX documents_kind_idx ON documents (kind, status, due_date);

-- `taxes` is a snapshot of the line's taxes when it was saved
-- ([{"id": 1, "name": "GST", "rate": 5000}]), so later rate changes don't
-- alter existing documents.
CREATE TABLE document_lines (
    id               bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id      bigint  NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    position         int     NOT NULL,
    category_id      bigint  REFERENCES categories (id),
    description      text    NOT NULL CHECK (length(description) BETWEEN 1 AND 1000),
    quantity         bigint  NOT NULL CHECK (quantity > 0),
    unit_price_cents bigint  NOT NULL,
    taxes            jsonb   NOT NULL DEFAULT '[]',
    amount_cents     bigint  NOT NULL
);
CREATE INDEX document_lines_document_idx ON document_lines (document_id, position);
CREATE INDEX document_lines_category_idx ON document_lines (category_id);

CREATE TABLE payments (
    id               bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id      bigint  NOT NULL REFERENCES documents (id),
    payment_date     date    NOT NULL,
    amount_cents     bigint  NOT NULL CHECK (amount_cents > 0),
    method           text    NOT NULL DEFAULT '',
    reference        text    NOT NULL DEFAULT '',
    journal_entry_id bigint,
    created_by       text    NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX payments_document_idx ON payments (document_id);

CREATE TABLE email_log (
    id          bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint  REFERENCES documents (id) ON DELETE CASCADE,
    recipients  text    NOT NULL,
    subject     text    NOT NULL,
    ok          boolean NOT NULL,
    error       text    NOT NULL DEFAULT '',
    sent_by     text    NOT NULL,
    sent_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX email_log_document_idx ON email_log (document_id);
