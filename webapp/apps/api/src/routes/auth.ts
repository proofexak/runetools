import { ChangePasswordBody, LoginBody, SetupBody, type Me } from "@runetools/shared";
import type { FastifyInstance, FastifyReply } from "fastify";
import type { AppContext } from "../app.js";
import {
  COOKIE, SESSION_TTL_MS, checkLogin, createUser, endOtherSessions, endSession, setPassword,
  startSession, userCount, verifyPassword,
} from "../auth/auth.js";
import { users } from "../db/schema.js";
import { HttpError, ok, parse } from "../http.js";
import { eq } from "drizzle-orm";

const LIMITED = { config: { rateLimit: { max: 10, timeWindow: "1 minute" } } };

export async function authRoutes(app: FastifyInstance, { db, config }: AppContext) {
  const setCookie = (reply: FastifyReply, value: string) =>
    reply.setCookie(COOKIE, value, {
      path: "/", httpOnly: true, sameSite: "strict", secure: config.secureCookie,
      maxAge: SESSION_TTL_MS / 1000,
    });

  app.get("/api/auth/me", async (req): Promise<Me> => {
    if (req.auth) return { state: "authenticated", username: req.auth.username, csrf: req.auth.csrf };
    return (await userCount(db)) === 0 ? { state: "setup" } : { state: "anonymous" };
  });

  // First run only: creates the one app user. Refused once any user exists.
  app.post("/api/auth/setup", LIMITED, async (req, reply) => {
    const body = parse(SetupBody, req.body);
    if ((await userCount(db)) > 0) throw new HttpError(409, "already set up");
    const id = await createUser(db, body.username, body.password);
    setCookie(reply, await startSession(db, id));
    return ok(reply);
  });

  app.post("/api/auth/login", LIMITED, async (req, reply) => {
    const body = parse(LoginBody, req.body);
    const id = await checkLogin(db, body.username, body.password);
    if (id === null) throw new HttpError(401, "wrong username or password");
    setCookie(reply, await startSession(db, id));
    return ok(reply);
  });

  app.post("/api/auth/logout", async (req, reply) => {
    await endSession(db, req.auth!.sid);
    reply.clearCookie(COOKIE, { path: "/" });
    return ok(reply);
  });

  app.post("/api/auth/password", LIMITED, async (req, reply) => {
    const body = parse(ChangePasswordBody, req.body);
    const auth = req.auth!;
    const [user] = await db.select().from(users).where(eq(users.id, auth.userId));
    if (!user || !(await verifyPassword(user.passwordHash, body.current))) {
      throw new HttpError(401, "current password is wrong");
    }
    await setPassword(db, auth.userId, body.next);
    await endOtherSessions(db, auth.userId, auth.sid);
    return ok(reply);
  });
}
