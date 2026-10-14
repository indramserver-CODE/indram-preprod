-- Indram invoice total rounded to the nearest rupee, as on Indram's own invoices.
ALTER TABLE indram_bills ADD COLUMN IF NOT EXISTS rounding numeric(12,2) NOT NULL DEFAULT 0;
