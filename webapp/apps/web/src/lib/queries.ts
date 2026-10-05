import type {
  AccountsResponse, BotStatsResponse, FeedEvent, LiveConfig, LiveControl, Overview, SessionDetail, SessionsQuery,
  SessionsResponse, SettingsResponse, VaultStatus,
} from "@runetools/shared";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, qs } from "./api";
import { controlPhase } from "./live-view";

export const keys = {
  overview: (account?: string) => ["overview", account ?? null] as const,
  sessions: (q: SessionsQuery) => ["sessions", q] as const,
  session: (id: number) => ["session", id] as const,
  bots: (account?: string, since?: string) => ["bots", account ?? null, since ?? null] as const,
  accounts: ["accounts"] as const,
  vault: ["vault"] as const,
  settings: ["settings"] as const,
  liveConfig: ["live-config"] as const,
  liveControl: ["live-control"] as const,
};

export const useOverview = (account?: string, opts: { enabled?: boolean } = {}) => useQuery({
  ...opts,
  queryKey: keys.overview(account),
  queryFn: () => api.get<Overview>(`/api/overview${qs({ account })}`),
  placeholderData: keepPreviousData,
  // liveness ages out without any new log line: a killed bot (90 s without a heartbeat) leaves within 2 min
  refetchInterval: 30_000,
});

export const useSessions = (q: SessionsQuery) => useQuery({
  queryKey: keys.sessions(q),
  queryFn: () => api.get<SessionsResponse>(`/api/sessions${qs(q as Record<string, string | number | undefined>)}`),
  placeholderData: keepPreviousData,
});

export const useSession = (id: number) => useQuery({
  queryKey: keys.session(id),
  queryFn: () => api.get<SessionDetail>(`/api/sessions/${id}`),
});

export const useBotStats = (account?: string, since?: string) => useQuery({
  queryKey: keys.bots(account, since),
  queryFn: () => api.get<BotStatsResponse>(`/api/bots/stats${qs({ account, since })}`),
  placeholderData: keepPreviousData,
});

export const useAccounts = () => useQuery({
  queryKey: keys.accounts,
  queryFn: () => api.get<AccountsResponse>("/api/accounts"),
});

export const useVault = () => useQuery({
  queryKey: keys.vault,
  queryFn: () => api.get<VaultStatus>("/api/vault"),
  refetchInterval: 30_000,          // notice the auto-lock
});

export const useSettings = () => useQuery({
  queryKey: keys.settings,
  queryFn: () => api.get<SettingsResponse>("/api/settings"),
});

export const useLiveConfig = () => useQuery({
  queryKey: keys.liveConfig,
  queryFn: () => api.get<LiveConfig>("/api/live/config"),
  staleTime: Infinity,
});

/** Polled fast only while waiting for the bot to answer a take-control request. */
export const useLiveControl = () => useQuery({
  queryKey: keys.liveControl,
  queryFn: () => api.get<LiveControl>("/api/live/control"),
  refetchInterval: (q) => (controlPhase(q.state.data, Date.now()) === "pausing" ? 500 : 15_000),
});

/** Every bot that ever logged — the stable domain for bot colours. */
export const useAllBots = () => useQuery({
  queryKey: ["all-bots"],
  queryFn: async () => (await api.get<SessionsResponse>("/api/sessions?limit=1")).bots,
  staleTime: 5 * 60_000,
});

/** Keeps /api/events open and refetches what each event names. Returns whether it's connected. */
export function useLiveFeed(): boolean {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const es = new EventSource("/api/events");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (msg) => {
      const e = JSON.parse(msg.data) as FeedEvent;
      if (e.type === "sessions") {
        for (const k of ["overview", "sessions", "bots", "all-bots"]) qc.invalidateQueries({ queryKey: [k] });
        for (const id of e.ids) qc.invalidateQueries({ queryKey: keys.session(id) });
      } else if (e.type === "accounts") {
        qc.invalidateQueries({ queryKey: keys.accounts });
      } else if (e.type === "vault") {
        qc.invalidateQueries({ queryKey: keys.vault });
        if (!e.unlocked) qc.removeQueries({ queryKey: ["vault-entry"] });
      } else if (e.type === "live") {
        qc.invalidateQueries({ queryKey: keys.liveControl });
      }
    };
    return () => es.close();
  }, [qc]);
  return connected;
}
