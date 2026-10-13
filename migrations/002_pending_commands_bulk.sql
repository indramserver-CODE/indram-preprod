-- Society-wide DEACTIVATE_ALL / ACTIVATE_ALL queue: one pending_commands row per charger.
ALTER TABLE pending_commands
    ADD COLUMN IF NOT EXISTS society_id   integer,
    ADD COLUMN IF NOT EXISTS attempts     integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_sent_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_pending_commands_society_status
    ON pending_commands (society_id, status);
