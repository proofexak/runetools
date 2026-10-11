CREATE TABLE "schedule_blocks" (
	"id" serial PRIMARY KEY NOT NULL,
	"account_id" integer NOT NULL,
	"start_at" timestamp with time zone NOT NULL,
	"end_at" timestamp with time zone NOT NULL,
	"bot" text NOT NULL,
	"launch" text NOT NULL,
	"value" text,
	"edited" boolean DEFAULT false NOT NULL
);
--> statement-breakpoint
CREATE TABLE "schedule_profiles" (
	"account_id" integer PRIMARY KEY NOT NULL,
	"enabled" boolean DEFAULT false NOT NULL,
	"timezone" text DEFAULT 'Europe/Warsaw' NOT NULL,
	"monthly_hours" integer DEFAULT 200 NOT NULL,
	"activities" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"ramp_start" date,
	"seed" integer DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "schedule_blocks" ADD CONSTRAINT "schedule_blocks_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "schedule_profiles" ADD CONSTRAINT "schedule_profiles_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "schedule_blocks_account_start" ON "schedule_blocks" USING btree ("account_id","start_at");