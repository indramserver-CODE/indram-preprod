-- session_id is a per-charger counter, so it is unique only together with charger_id.
-- Demo data only: existing sessions/heartbeats/orphans are wiped.
BEGIN;

TRUNCATE heartbeats, orphan_messages, charging_sessions RESTART IDENTITY CASCADE;

ALTER TABLE heartbeats DROP CONSTRAINT IF EXISTS heartbeats_session_id_fkey;
ALTER TABLE charging_sessions DROP CONSTRAINT IF EXISTS charging_sessions_session_id_key;
DROP INDEX IF EXISTS charging_sessions_session_id_key;

ALTER TABLE charging_sessions
    ADD CONSTRAINT uq_charging_sessions_charger_session UNIQUE (charger_id, session_id);

ALTER TABLE heartbeats
    ADD CONSTRAINT heartbeats_charger_session_fkey
    FOREIGN KEY (charger_id, session_id)
    REFERENCES charging_sessions (charger_id, session_id) ON DELETE CASCADE;

COMMIT;
