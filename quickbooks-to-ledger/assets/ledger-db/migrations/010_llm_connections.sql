-- Settings → LLM API can hold several connections (e.g. one for text, one
-- for images); record which one answered each call.
ALTER TABLE llm_usage ADD COLUMN connection TEXT NOT NULL DEFAULT '';
