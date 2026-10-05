/** In-process fan-out of FeedEvents to the SSE clients (routes/events.ts). */
import { EventEmitter } from "node:events";
import type { FeedEvent } from "@runetools/shared";

export class Bus {
  private ee = new EventEmitter().setMaxListeners(0);
  emit(event: FeedEvent) { this.ee.emit("feed", event); }
  on(fn: (event: FeedEvent) => void): () => void {
    this.ee.on("feed", fn);
    return () => this.ee.off("feed", fn);
  }
}
