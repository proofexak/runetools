ALTER TABLE "sessions" ADD COLUMN "has_start" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "sessions" ADD COLUMN "file_mtime" timestamp with time zone;