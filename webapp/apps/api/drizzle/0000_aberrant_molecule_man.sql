CREATE TABLE "accounts" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"notes" text DEFAULT '' NOT NULL,
	"active" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "accounts_name_unique" UNIQUE("name")
);
--> statement-breakpoint
CREATE TABLE "auth_sessions" (
	"id" text PRIMARY KEY NOT NULL,
	"user_id" integer NOT NULL,
	"csrf" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"expires_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE TABLE "credentials" (
	"id" serial PRIMARY KEY NOT NULL,
	"account_id" integer NOT NULL,
	"ciphertext" "bytea" NOT NULL,
	"nonce" "bytea" NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "credentials_account_id_unique" UNIQUE("account_id")
);
--> statement-breakpoint
CREATE TABLE "errors" (
	"id" serial PRIMARY KEY NOT NULL,
	"session_id" integer NOT NULL,
	"ts" timestamp(3) NOT NULL,
	"type" text,
	"message" text,
	"traceback" text,
	"state" text,
	"where" text
);
--> statement-breakpoint
CREATE TABLE "ingest_cursors" (
	"path" text PRIMARY KEY NOT NULL,
	"offset" bigint NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "sessions" (
	"id" serial PRIMARY KEY NOT NULL,
	"file" text NOT NULL,
	"stamp" text,
	"bot" text,
	"account" text,
	"pid" integer,
	"params" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"started_at" timestamp(3) NOT NULL,
	"last_event_at" timestamp(3) NOT NULL,
	"ended_at" timestamp(3),
	"final" text,
	"reason" text,
	"last_step" text,
	"active_seconds" double precision DEFAULT 0 NOT NULL,
	"paused_seconds" double precision DEFAULT 0 NOT NULL,
	"pauses" integer DEFAULT 0 NOT NULL,
	"runs" integer DEFAULT 0 NOT NULL,
	"error_count" integer DEFAULT 0 NOT NULL,
	CONSTRAINT "sessions_file_unique" UNIQUE("file")
);
--> statement-breakpoint
CREATE TABLE "settings" (
	"key" text PRIMARY KEY NOT NULL,
	"value" jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "steps" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"session_id" integer NOT NULL,
	"ts" timestamp(3) NOT NULL,
	"state" text NOT NULL,
	"result" text,
	"seconds" double precision DEFAULT 0 NOT NULL,
	"run" integer
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" serial PRIMARY KEY NOT NULL,
	"username" text NOT NULL,
	"password_hash" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_username_unique" UNIQUE("username")
);
--> statement-breakpoint
CREATE TABLE "vault_meta" (
	"id" integer PRIMARY KEY DEFAULT 1 NOT NULL,
	"salt" "bytea" NOT NULL,
	"kdf" jsonb NOT NULL,
	"check_ciphertext" "bytea" NOT NULL,
	"check_nonce" "bytea" NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "vault_meta_singleton" CHECK ("vault_meta"."id" = 1)
);
--> statement-breakpoint
ALTER TABLE "auth_sessions" ADD CONSTRAINT "auth_sessions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "credentials" ADD CONSTRAINT "credentials_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "errors" ADD CONSTRAINT "errors_session_id_sessions_id_fk" FOREIGN KEY ("session_id") REFERENCES "public"."sessions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "steps" ADD CONSTRAINT "steps_session_id_sessions_id_fk" FOREIGN KEY ("session_id") REFERENCES "public"."sessions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "accounts_one_active" ON "accounts" USING btree ("active") WHERE "accounts"."active";--> statement-breakpoint
CREATE INDEX "errors_session" ON "errors" USING btree ("session_id");--> statement-breakpoint
CREATE INDEX "sessions_started_at" ON "sessions" USING btree ("started_at");--> statement-breakpoint
CREATE INDEX "sessions_account" ON "sessions" USING btree ("account");--> statement-breakpoint
CREATE INDEX "sessions_bot" ON "sessions" USING btree ("bot");--> statement-breakpoint
CREATE INDEX "steps_session" ON "steps" USING btree ("session_id");--> statement-breakpoint
CREATE VIEW "public"."daily_activity" AS (
  SELECT s.account, s.bot, d.day::date AS day,
         sum(s.active_seconds * d.frac) / 3600 AS hours,
         sum(s.runs * d.frac) AS runs
  FROM sessions s
  CROSS JOIN LATERAL (
    SELECT g AS day,
           CASE WHEN coalesce(s.ended_at, s.last_event_at) <= s.started_at THEN 1.0
                ELSE extract(epoch FROM least(coalesce(s.ended_at, s.last_event_at), g + interval '1 day')
                                        - greatest(s.started_at, g))
                     / extract(epoch FROM coalesce(s.ended_at, s.last_event_at) - s.started_at)
           END AS frac
    FROM generate_series(date_trunc('day', s.started_at),
                         date_trunc('day', coalesce(s.ended_at, s.last_event_at)),
                         interval '1 day') AS g
  ) d
  WHERE d.frac > 0
  GROUP BY s.account, s.bot, d.day
);