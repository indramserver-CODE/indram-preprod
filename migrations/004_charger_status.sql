-- Live charger status on the chargers table, kept up to date from charger messages.
BEGIN;

ALTER TABLE chargers
    ADD COLUMN IF NOT EXISTS status            varchar(20) NOT NULL DEFAULT 'never_connected',
    ADD COLUMN IF NOT EXISTS fault_code        varchar(10),
    ADD COLUMN IF NOT EXISTS locked            boolean     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS lock_reasons      jsonb       NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS connection_type   varchar(10) NOT NULL DEFAULT 'hub',
    ADD COLUMN IF NOT EXISTS status_updated_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_reset_reason varchar(50);

-- Starting point until each charger's next message: heard from in the last 75 min →
-- available (or charging, from the last telemetry), otherwise offline / never connected.
UPDATE chargers c
SET    status = CASE
           WHEN c.last_seen_at IS NULL                              THEN 'never_connected'
           WHEN c.last_seen_at < now() - interval '75 minutes'      THEN 'offline'
           WHEN cs.charger_status = 'active'                        THEN 'charging'
           ELSE 'available'
       END,
       status_updated_at = now()
FROM   chargers c2
LEFT JOIN charger_status cs ON cs.charger_id = c2.charger_id
WHERE  c2.id = c.id;

COMMIT;
