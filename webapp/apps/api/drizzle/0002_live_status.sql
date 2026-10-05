ALTER TABLE "sessions" ADD COLUMN "current_state" text;--> statement-breakpoint
ALTER TABLE "sessions" ADD COLUMN "state_since" timestamp(3);--> statement-breakpoint
ALTER TABLE "sessions" ADD COLUMN "paused_since" timestamp(3);--> statement-breakpoint
ALTER TABLE "sessions" ADD COLUMN "last_heartbeat" timestamp(3);