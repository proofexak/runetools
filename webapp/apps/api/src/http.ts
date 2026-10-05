import type { FastifyReply } from "fastify";
import { z, type ZodType } from "zod";

export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function parse<T extends ZodType>(schema: T, value: unknown): z.output<T> {
  const r = schema.safeParse(value ?? {});
  if (!r.success) {
    const issue = r.error.issues[0];
    const where = issue?.path.length ? `${issue.path.join(".")}: ` : "";
    throw new HttpError(400, `${where}${issue?.message ?? "invalid request"}`);
  }
  return r.data;
}

export const ok = (reply: FastifyReply) => reply.send({ ok: true });
