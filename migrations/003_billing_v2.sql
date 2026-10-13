-- Billing v2: From–Till periods, draft → send, GST, payments, late fees,
-- Indram GST invoices with a running number, super admin notifications.
-- Old billing data was test data only — the billing tables are dropped and rebuilt.
BEGIN;

DROP TABLE IF EXISTS notifications, invoice_counters, indram_bills,
                     flat_bill_sessions, flat_bills, monthly_bills CASCADE;

ALTER TABLE societies
    ADD COLUMN IF NOT EXISTS gstin                        varchar(15),
    ADD COLUMN IF NOT EXISTS resident_late_fee_pct        numeric(5,2) NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS resident_late_fee_grace_days integer      NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS indram_late_fee_pct          numeric(5,2) NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS indram_late_fee_grace_days   integer      NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS letterhead_s3_key            varchar(500),
    ADD COLUMN IF NOT EXISTS payee_name                   varchar(255),
    ADD COLUMN IF NOT EXISTS bank_name                    varchar(255),
    ADD COLUMN IF NOT EXISTS bank_account_no              varchar(50),
    ADD COLUMN IF NOT EXISTS bank_ifsc                    varchar(20),
    ADD COLUMN IF NOT EXISTS upi_id                       varchar(100),
    ADD COLUMN IF NOT EXISTS payment_note                 text,
    ADD COLUMN IF NOT EXISTS bill_counter                 integer      NOT NULL DEFAULT 0;

CREATE TABLE monthly_bills (
	id SERIAL NOT NULL,
	meter_id INTEGER NOT NULL,
	period_from DATE NOT NULL,
	period_till DATE NOT NULL,
	billing_month DATE NOT NULL,
	tariff NUMERIC(10, 4) NOT NULL,
	total_bill_amount NUMERIC(12, 2) NOT NULL,
	total_units_consumed NUMERIC(12, 4) NOT NULL,
	effective_unit_rate NUMERIC(10, 4) NOT NULL,
	due_date DATE NOT NULL,
	bill_photo_s3_key VARCHAR(500),
	status VARCHAR(20) DEFAULT 'draft' NOT NULL,
	sent_at TIMESTAMP WITH TIME ZONE,
	cancelled_at TIMESTAMP WITH TIME ZONE,
	replaces_id INTEGER,
	reminder_sent_at TIMESTAMP WITH TIME ZONE,
	created_by INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(meter_id) REFERENCES meters (id) ON DELETE CASCADE,
	FOREIGN KEY(replaces_id) REFERENCES monthly_bills (id) ON DELETE SET NULL,
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE INDEX ix_monthly_bills_meter_id ON monthly_bills (meter_id);
CREATE UNIQUE INDEX uq_monthly_bills_meter_draft ON monthly_bills (meter_id) WHERE status = 'draft';
CREATE UNIQUE INDEX uq_monthly_bills_meter_sent_from ON monthly_bills (meter_id, period_from) WHERE status = 'sent';

CREATE TABLE flat_bills (
	id SERIAL NOT NULL,
	monthly_bill_id INTEGER NOT NULL,
	flat_id INTEGER NOT NULL,
	bill_number VARCHAR(30),
	flat_number VARCHAR(50) NOT NULL,
	owner_name VARCHAR(255),
	email VARCHAR(255),
	charger_id VARCHAR(50),
	rfid_uids JSONB DEFAULT '[]' NOT NULL,
	units_consumed NUMERIC(12, 4) NOT NULL,
	adjustment_units NUMERIC(12, 4) NOT NULL,
	bill_excl_taxes NUMERIC(12, 2) NOT NULL,
	mseb_taxes NUMERIC(12, 2) NOT NULL,
	electricity_charges_incl_tax NUMERIC(12, 2) NOT NULL,
	indram_rate NUMERIC(10, 4) NOT NULL,
	indram_charges NUMERIC(12, 2) NOT NULL,
	indram_cgst NUMERIC(12, 2) NOT NULL,
	indram_sgst NUMERIC(12, 2) NOT NULL,
	indram_total NUMERIC(12, 2) NOT NULL,
	total_payable NUMERIC(12, 2) NOT NULL,
	payment_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
	late_fee_pct NUMERIC(5, 2),
	late_fee NUMERIC(12, 2) DEFAULT '0' NOT NULL,
	marked_unpaid_at TIMESTAMP WITH TIME ZONE,
	paid_at TIMESTAMP WITH TIME ZONE,
	pdf_s3_key VARCHAR(500),
	late_pdf_s3_key VARCHAR(500),
	receipt_pdf_s3_key VARCHAR(500),
	email_status VARCHAR(20) NOT NULL,
	email_sent_at TIMESTAMP WITH TIME ZONE,
	reminder_sent_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(monthly_bill_id) REFERENCES monthly_bills (id) ON DELETE CASCADE,
	FOREIGN KEY(flat_id) REFERENCES flats (id) ON DELETE CASCADE,
	UNIQUE (bill_number)
);
CREATE INDEX ix_flat_bills_flat_id ON flat_bills (flat_id);
CREATE INDEX ix_flat_bills_monthly_bill_id ON flat_bills (monthly_bill_id);

CREATE TABLE flat_bill_sessions (
	flat_bill_id INTEGER NOT NULL,
	session_id INTEGER NOT NULL,
	is_adjustment BOOLEAN NOT NULL,
	PRIMARY KEY (flat_bill_id, session_id),
	FOREIGN KEY(flat_bill_id) REFERENCES flat_bills (id) ON DELETE CASCADE,
	FOREIGN KEY(session_id) REFERENCES charging_sessions (id) ON DELETE CASCADE
);
CREATE INDEX ix_flat_bill_sessions_session_id ON flat_bill_sessions (session_id);

CREATE TABLE indram_bills (
	id SERIAL NOT NULL,
	society_id INTEGER NOT NULL,
	monthly_bill_id INTEGER NOT NULL,
	invoice_number VARCHAR(30) NOT NULL,
	billing_month DATE NOT NULL,
	period_from DATE NOT NULL,
	period_till DATE NOT NULL,
	total_units NUMERIC(12, 4) NOT NULL,
	indram_rate NUMERIC(10, 4) NOT NULL,
	total_indram_amount NUMERIC(12, 2) NOT NULL,
	late_flag BOOLEAN DEFAULT 'false' NOT NULL,
	late_fee_pct NUMERIC(5, 2),
	late_fee NUMERIC(12, 2) DEFAULT '0' NOT NULL,
	cgst NUMERIC(12, 2) NOT NULL,
	sgst NUMERIC(12, 2) NOT NULL,
	total_payable NUMERIC(12, 2) NOT NULL,
	society_gstin VARCHAR(15),
	due_date DATE NOT NULL,
	status VARCHAR(20) DEFAULT 'issued' NOT NULL,
	payment_status VARCHAR(20) DEFAULT 'unpaid' NOT NULL,
	paid_at TIMESTAMP WITH TIME ZONE,
	replaces_id INTEGER,
	pdf_s3_key VARCHAR(500),
	receipt_pdf_s3_key VARCHAR(500),
	email_status VARCHAR(20) NOT NULL,
	email_sent_at TIMESTAMP WITH TIME ZONE,
	reminder_sent_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(society_id) REFERENCES societies (id) ON DELETE CASCADE,
	FOREIGN KEY(monthly_bill_id) REFERENCES monthly_bills (id) ON DELETE CASCADE,
	UNIQUE (invoice_number),
	FOREIGN KEY(replaces_id) REFERENCES indram_bills (id) ON DELETE SET NULL
);
CREATE INDEX ix_indram_bills_monthly_bill_id ON indram_bills (monthly_bill_id);
CREATE INDEX ix_indram_bills_society_id ON indram_bills (society_id);

CREATE TABLE invoice_counters (
	financial_year VARCHAR(7) NOT NULL,
	last_no INTEGER NOT NULL,
	PRIMARY KEY (financial_year)
);

CREATE TABLE notifications (
	id SERIAL NOT NULL,
	type VARCHAR(30) NOT NULL,
	society_id INTEGER NOT NULL,
	flat_id INTEGER,
	flat_bill_id INTEGER,
	charger_id VARCHAR(50),
	message TEXT NOT NULL,
	is_read BOOLEAN DEFAULT 'false' NOT NULL,
	actioned_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(society_id) REFERENCES societies (id) ON DELETE CASCADE,
	FOREIGN KEY(flat_id) REFERENCES flats (id) ON DELETE SET NULL,
	FOREIGN KEY(flat_bill_id) REFERENCES flat_bills (id) ON DELETE SET NULL
);
CREATE INDEX ix_notifications_created_at ON notifications (created_at);
CREATE INDEX ix_notifications_society_id ON notifications (society_id);

COMMIT;
