CREATE SCHEMA "public";
CREATE TYPE "user_role" AS ENUM('super_admin', 'society_admin');
CREATE TYPE "email_status" AS ENUM('pending', 'sent', 'failed');
CREATE TYPE "ticket_status" AS ENUM('open', 'in_progress', 'resolved', 'closed');
CREATE TYPE "ticket_priority" AS ENUM('low', 'medium', 'high');
CREATE TYPE "ticket_category" AS ENUM('billing', 'charger', 'rfid', 'account', 'other');
CREATE TABLE "charger_status" (
	"id" serial PRIMARY KEY,
	"charger_id" varchar(50) NOT NULL CONSTRAINT "charger_status_charger_id_key" UNIQUE,
	"charger_status" varchar(50),
	"voltage" numeric(8, 2),
	"current" numeric(8, 2),
	"energy_kwh" numeric(12, 4),
	"rfid_uid" varchar(50),
	"duration_min" integer,
	"fault_code" varchar(100),
	"temperature_c" numeric(6, 2),
	"fw_version" varchar(20),
	"device_datetime" timestamp with time zone,
	"received_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE "chargers" (
	"id" serial PRIMARY KEY,
	"flat_id" integer NOT NULL CONSTRAINT "chargers_flat_id_key" UNIQUE,
	"charger_id" varchar(50) NOT NULL CONSTRAINT "chargers_charger_id_key" UNIQUE,
	"fw_version" varchar(20),
	"is_active" boolean DEFAULT true,
	"last_seen_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE "charging_sessions" (
	"id" serial PRIMARY KEY,
	"session_id" bigint NOT NULL,
	"charger_id" varchar(50) NOT NULL,
	"rfid_uid" varchar(50),
	"start_kwhr" numeric(12, 4),
	"end_kwhr" numeric(12, 4),
	"units_consumed" numeric(12, 4),
	"status" varchar(50) DEFAULT 'active' NOT NULL,
	"fault_code" varchar(100),
	"fw_version" varchar(20),
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"ended_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now(),
	"temperature_c" numeric(6, 2),
	"msg_id" varchar(50) CONSTRAINT "charging_sessions_msg_id_key" UNIQUE,
	"start_epoch" bigint,
	"stop_epoch" bigint,
	"start_meter_kwh" numeric(10, 4),
	"end_meter_kwh" numeric(10, 4),
	"offline" boolean DEFAULT false
);
CREATE TABLE "command_logs" (
	"id" serial PRIMARY KEY,
	"charger_id" varchar(50) NOT NULL,
	"log_type" varchar(20) NOT NULL,
	"cmd" varchar(50),
	"ok" boolean,
	"reason" varchar(100),
	"rfid_uid" varchar(50),
	"slots_remaining" integer,
	"fw_version" varchar(20),
	"received_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE "flat_bills" (
	"id" serial PRIMARY KEY,
	"monthly_bill_id" integer NOT NULL UNIQUE,
	"flat_id" integer NOT NULL UNIQUE,
	"units_consumed" numeric(12, 4) DEFAULT '0' NOT NULL,
	"bill_excl_taxes" numeric(12, 2) DEFAULT '0' NOT NULL,
	"mseb_taxes" numeric(12, 2) DEFAULT '0' NOT NULL,
	"electricity_charges_incl_tax" numeric(12, 2) DEFAULT '0' NOT NULL,
	"indram_charges" numeric(12, 2) DEFAULT '0' NOT NULL,
	"total_payable" numeric(12, 2) DEFAULT '0' NOT NULL,
	"pdf_s3_key" varchar(500),
	"email_status" varchar(20) DEFAULT 'pending',
	"email_sent_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "flat_bills_monthly_bill_id_flat_id_key" UNIQUE("monthly_bill_id","flat_id")
);
CREATE TABLE "flats" (
	"id" serial PRIMARY KEY,
	"society_id" integer NOT NULL UNIQUE,
	"flat_number" varchar(50) NOT NULL UNIQUE,
	"owner_name" varchar(255),
	"email" varchar(255),
	"created_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "flats_society_id_flat_number_key" UNIQUE("society_id","flat_number")
);
CREATE TABLE "heartbeats" (
	"id" serial PRIMARY KEY,
	"session_id" bigint NOT NULL,
	"charger_id" varchar(50) NOT NULL,
	"status" varchar(50),
	"fault_code" varchar(100),
	"fw_version" varchar(20),
	"received_at" timestamp with time zone DEFAULT now(),
	"temperature_c" numeric(6, 2),
	"device_datetime" timestamp with time zone
);
CREATE TABLE "monthly_bills" (
	"id" serial PRIMARY KEY,
	"society_id" integer NOT NULL UNIQUE,
	"billing_month" date NOT NULL UNIQUE,
	"tariff" numeric(10, 4) NOT NULL,
	"total_bill_amount" numeric(12, 2) NOT NULL,
	"total_units_consumed" numeric(12, 4) NOT NULL,
	"effective_unit_rate" numeric(10, 4) NOT NULL,
	"due_date" date NOT NULL,
	"bill_photo_s3_key" varchar(500),
	"created_by" integer,
	"created_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "monthly_bills_society_id_billing_month_key" UNIQUE("society_id","billing_month")
);
CREATE TABLE "orphan_messages" (
	"id" serial PRIMARY KEY,
	"charger_id" varchar(50),
	"session_id" bigint,
	"event" varchar(100),
	"payload" jsonb,
	"is_reviewed" boolean DEFAULT false,
	"received_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE "pending_commands" (
	"id" serial PRIMARY KEY,
	"charger_id" varchar(50) NOT NULL,
	"cmd" varchar(20) NOT NULL,
	"flat_id" integer,
	"rfid_uid" varchar(50),
	"rfid_card_id" integer,
	"status" varchar(20) DEFAULT 'pending' NOT NULL,
	"reason" varchar(100),
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"resolved_at" timestamp with time zone,
	"society_id" integer,
	"attempts" integer DEFAULT 0 NOT NULL,
	"last_sent_at" timestamp with time zone
);
CREATE TABLE "rfid_cards" (
	"id" serial PRIMARY KEY,
	"flat_id" integer NOT NULL,
	"uid" varchar(50) NOT NULL CONSTRAINT "rfid_cards_uid_key" UNIQUE,
	"label" varchar(100),
	"is_active" boolean DEFAULT true,
	"created_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE "societies" (
	"id" serial PRIMARY KEY,
	"name" varchar(255) NOT NULL,
	"address" text,
	"created_at" timestamp with time zone DEFAULT now()
);
CREATE TABLE "society_admins" (
	"user_id" integer,
	"society_id" integer,
	"assigned_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "society_admins_pkey" PRIMARY KEY("user_id","society_id")
);
CREATE TABLE "ticket_comments" (
	"id" serial PRIMARY KEY,
	"ticket_id" integer NOT NULL,
	"author_id" integer,
	"body" text NOT NULL,
	"is_internal" boolean NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE "tickets" (
	"id" serial PRIMARY KEY,
	"title" varchar(255) NOT NULL,
	"description" text NOT NULL,
	"status" ticket_status NOT NULL,
	"priority" ticket_priority NOT NULL,
	"category" ticket_category NOT NULL,
	"created_by_id" integer,
	"society_id" integer,
	"assigned_to_id" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"resolved_at" timestamp with time zone
);
CREATE TABLE "users" (
	"id" serial PRIMARY KEY,
	"email" varchar(255) NOT NULL CONSTRAINT "users_email_key" UNIQUE,
	"hashed_password" varchar(255) NOT NULL,
	"full_name" varchar(255),
	"role" varchar NOT NULL,
	"is_active" boolean DEFAULT true,
	"created_at" timestamp with time zone DEFAULT now()
);
CREATE UNIQUE INDEX "charger_status_charger_id_key" ON "charger_status" ("charger_id");
CREATE UNIQUE INDEX "charger_status_pkey" ON "charger_status" ("id");
CREATE UNIQUE INDEX "chargers_charger_id_key" ON "chargers" ("charger_id");
CREATE UNIQUE INDEX "chargers_flat_id_key" ON "chargers" ("flat_id");
CREATE UNIQUE INDEX "chargers_pkey" ON "chargers" ("id");
CREATE UNIQUE INDEX "charging_sessions_msg_id_key" ON "charging_sessions" ("msg_id");
CREATE UNIQUE INDEX "charging_sessions_pkey" ON "charging_sessions" ("id");
CREATE UNIQUE INDEX "uq_charging_sessions_charger_session" ON "charging_sessions" ("charger_id", "session_id");
CREATE INDEX "idx_sessions_charger_id" ON "charging_sessions" ("charger_id");
CREATE INDEX "idx_sessions_started_at" ON "charging_sessions" ("started_at");
CREATE INDEX "idx_sessions_status" ON "charging_sessions" ("status");
CREATE INDEX "ix_charging_sessions_msg_id" ON "charging_sessions" ("msg_id");
CREATE UNIQUE INDEX "command_logs_pkey" ON "command_logs" ("id");
CREATE INDEX "ix_command_logs_charger" ON "command_logs" ("charger_id");
CREATE INDEX "ix_command_logs_received" ON "command_logs" ("received_at");
CREATE UNIQUE INDEX "flat_bills_monthly_bill_id_flat_id_key" ON "flat_bills" ("monthly_bill_id","flat_id");
CREATE UNIQUE INDEX "flat_bills_pkey" ON "flat_bills" ("id");
CREATE INDEX "idx_flat_bills_flat" ON "flat_bills" ("flat_id");
CREATE INDEX "idx_flat_bills_monthly" ON "flat_bills" ("monthly_bill_id");
CREATE UNIQUE INDEX "flats_pkey" ON "flats" ("id");
CREATE UNIQUE INDEX "flats_society_id_flat_number_key" ON "flats" ("society_id","flat_number");
CREATE UNIQUE INDEX "heartbeats_pkey" ON "heartbeats" ("id");
CREATE INDEX "idx_heartbeats_session" ON "heartbeats" ("session_id");
CREATE UNIQUE INDEX "monthly_bills_pkey" ON "monthly_bills" ("id");
CREATE UNIQUE INDEX "monthly_bills_society_id_billing_month_key" ON "monthly_bills" ("society_id","billing_month");
CREATE UNIQUE INDEX "orphan_messages_pkey" ON "orphan_messages" ("id");
CREATE INDEX "ix_pending_commands_charger_cmd" ON "pending_commands" ("charger_id","cmd","status");
CREATE INDEX "ix_pending_commands_status" ON "pending_commands" ("status","expires_at");
CREATE UNIQUE INDEX "pending_commands_pkey" ON "pending_commands" ("id");
CREATE UNIQUE INDEX "rfid_cards_pkey" ON "rfid_cards" ("id");
CREATE UNIQUE INDEX "rfid_cards_uid_key" ON "rfid_cards" ("uid");
CREATE UNIQUE INDEX "societies_pkey" ON "societies" ("id");
CREATE UNIQUE INDEX "society_admins_pkey" ON "society_admins" ("user_id","society_id");
CREATE UNIQUE INDEX "ticket_comments_pkey" ON "ticket_comments" ("id");
CREATE UNIQUE INDEX "tickets_pkey" ON "tickets" ("id");
CREATE UNIQUE INDEX "users_email_key" ON "users" ("email");
CREATE UNIQUE INDEX "users_pkey" ON "users" ("id");
ALTER TABLE "charger_status" ADD CONSTRAINT "charger_status_charger_id_fkey" FOREIGN KEY ("charger_id") REFERENCES "chargers"("charger_id") ON DELETE CASCADE;
ALTER TABLE "chargers" ADD CONSTRAINT "chargers_flat_id_fkey" FOREIGN KEY ("flat_id") REFERENCES "flats"("id") ON DELETE CASCADE;
ALTER TABLE "charging_sessions" ADD CONSTRAINT "charging_sessions_charger_id_fkey" FOREIGN KEY ("charger_id") REFERENCES "chargers"("charger_id");
ALTER TABLE "flat_bills" ADD CONSTRAINT "flat_bills_flat_id_fkey" FOREIGN KEY ("flat_id") REFERENCES "flats"("id") ON DELETE CASCADE;
ALTER TABLE "flat_bills" ADD CONSTRAINT "flat_bills_monthly_bill_id_fkey" FOREIGN KEY ("monthly_bill_id") REFERENCES "monthly_bills"("id") ON DELETE CASCADE;
ALTER TABLE "flats" ADD CONSTRAINT "flats_society_id_fkey" FOREIGN KEY ("society_id") REFERENCES "societies"("id") ON DELETE CASCADE;
ALTER TABLE "heartbeats" ADD CONSTRAINT "heartbeats_session_id_fkey" FOREIGN KEY ("charger_id", "session_id") REFERENCES "charging_sessions"("charger_id", "session_id") ON DELETE CASCADE;
ALTER TABLE "monthly_bills" ADD CONSTRAINT "monthly_bills_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "users"("id");
ALTER TABLE "monthly_bills" ADD CONSTRAINT "monthly_bills_society_id_fkey" FOREIGN KEY ("society_id") REFERENCES "societies"("id") ON DELETE CASCADE;
ALTER TABLE "pending_commands" ADD CONSTRAINT "pending_commands_flat_id_fkey" FOREIGN KEY ("flat_id") REFERENCES "flats"("id") ON DELETE CASCADE;
ALTER TABLE "pending_commands" ADD CONSTRAINT "pending_commands_rfid_card_id_fkey" FOREIGN KEY ("rfid_card_id") REFERENCES "rfid_cards"("id") ON DELETE CASCADE;
ALTER TABLE "rfid_cards" ADD CONSTRAINT "rfid_cards_flat_id_fkey" FOREIGN KEY ("flat_id") REFERENCES "flats"("id") ON DELETE CASCADE;
ALTER TABLE "society_admins" ADD CONSTRAINT "society_admins_society_id_fkey" FOREIGN KEY ("society_id") REFERENCES "societies"("id") ON DELETE CASCADE;
ALTER TABLE "society_admins" ADD CONSTRAINT "society_admins_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE;
ALTER TABLE "ticket_comments" ADD CONSTRAINT "ticket_comments_author_id_fkey" FOREIGN KEY ("author_id") REFERENCES "users"("id") ON DELETE SET NULL;
ALTER TABLE "ticket_comments" ADD CONSTRAINT "ticket_comments_ticket_id_fkey" FOREIGN KEY ("ticket_id") REFERENCES "tickets"("id") ON DELETE CASCADE;
ALTER TABLE "tickets" ADD CONSTRAINT "tickets_assigned_to_id_fkey" FOREIGN KEY ("assigned_to_id") REFERENCES "users"("id") ON DELETE SET NULL;
ALTER TABLE "tickets" ADD CONSTRAINT "tickets_created_by_id_fkey" FOREIGN KEY ("created_by_id") REFERENCES "users"("id") ON DELETE SET NULL;
ALTER TABLE "tickets" ADD CONSTRAINT "tickets_society_id_fkey" FOREIGN KEY ("society_id") REFERENCES "societies"("id") ON DELETE SET NULL;