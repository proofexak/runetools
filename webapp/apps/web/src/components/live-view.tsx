import type { LiveControl } from "@runetools/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { EyeOff, Hand, Loader2, Maximize, Minimize, MonitorOff, Play, Undo2 } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { VncScreenHandle } from "react-vnc";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { controlPhase, isInteractive, NO_ANSWER_MS, vncUrl, type ControlPhase } from "@/lib/live-view";
import { keys, useLiveConfig, useLiveControl } from "@/lib/queries";
import { cn } from "@/lib/utils";

// noVNC is heavy: loaded only once someone watches
const VncScreen = lazy(() => import("react-vnc").then((m) => ({ default: m.VncScreen })));

type Conn = "connecting" | "live" | "disconnected";

const RETRY_MS = 3000;
// the small tile doesn't need full quality; fullscreen does (noVNC: 0-9)
const TILE = { quality: 3, compression: 6 };
const FULL = { quality: 6, compression: 2 };

/**
 * The bot container's screen (x11vnc through /api/live/vnc), view-only unless a human has
 * taken control — then the bot is paused first (lib/live_control.py) so pyautogui and the
 * viewer never fight over the one mouse. Collapsed until "Watch live": nothing connects to
 * VNC before that. While a human has control it stays open until they release it.
 */
export function LiveView({ watch = false }: { watch?: boolean }) {
  const [watching, setWatching] = useState(watch);
  const control = useLiveControl();
  const phase = usePhase(control.data);
  const show = watching || phase !== "released";

  return (
    <Card className="min-w-0 gap-3">
      <CardHeader className="items-center">
        <div className="grid gap-1.5">
          <CardTitle>Live view</CardTitle>
          <CardDescription>{show ? describe(phase) : "The bot's screen — connects when you watch"}</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {show && <ControlButtons phase={phase} />}
          {!show && <Button size="sm" onClick={() => setWatching(true)}><Play /> Watch live</Button>}
          {show && phase === "released" && (
            <Button variant="ghost" size="sm" onClick={() => setWatching(false)}><EyeOff /> Stop watching</Button>
          )}
        </div>
      </CardHeader>
      {show && <CardContent><Screen phase={phase} /></CardContent>}
    </Card>
  );
}

function describe(phase: ControlPhase) {
  switch (phase) {
    case "released": return "The bot's screen, view only";
    case "pausing": return "Pausing the bot — it finishes its current step first";
    case "control": return "You have control — the bot is paused until you release it";
    case "no-bot": return "You have control — no bot answered, so none is running";
  }
}

/** The phase, re-evaluated as time passes while waiting (no answer for a while = no bot). */
function usePhase(c: LiveControl | undefined): ControlPhase {
  const [now, setNow] = useState(() => Date.now());
  const phase = controlPhase(c, now);
  useEffect(() => {
    if (phase !== "pausing") return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [phase]);
  // a new request starts its own clock
  useEffect(() => { setNow(Date.now()); }, [c?.id]);
  return phase;
}

function ControlButtons({ phase }: { phase: ControlPhase }) {
  const qc = useQueryClient();
  const send = useMutation({
    mutationFn: (action: "take" | "release") => api.post<LiveControl>("/api/live/control", { action }),
    onSuccess: (data) => qc.setQueryData(keys.liveControl, data),
  });
  if (phase === "released") {
    return (
      <Button size="sm" variant="outline" disabled={send.isPending} onClick={() => send.mutate("take")}
        title="Pause the bot, then use the mouse and keyboard here">
        <Hand /> Take control
      </Button>
    );
  }
  return (
    <>
      {phase === "pausing" && <Badge variant="warning"><Loader2 className="animate-spin" /> Pausing</Badge>}
      {isInteractive(phase) && <Badge variant="success">In control</Badge>}
      <Button size="sm" disabled={send.isPending} onClick={() => send.mutate("release")}
        title="Back to view only; the bot resumes">
        <Undo2 /> Release
      </Button>
    </>
  );
}

function Screen({ phase }: { phase: ControlPhase }) {
  const config = useLiveConfig();
  const vnc = useRef<VncScreenHandle>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [conn, setConn] = useState<Conn>("connecting");
  const [fullscreen, setFullscreen] = useState(false);
  const interactive = isInteractive(phase);
  // read by the RFB callbacks, which react-vnc binds once per connection
  const settings = useRef({ interactive, fullscreen });
  settings.current = { interactive, fullscreen };

  const apply = useCallback(() => {
    const rfb = vnc.current?.rfb;
    if (!rfb) return;
    const { interactive, fullscreen } = settings.current;
    rfb.viewOnly = !interactive;
    const q = fullscreen ? FULL : TILE;
    rfb.qualityLevel = q.quality;
    rfb.compressionLevel = q.compression;
    if (interactive) rfb.focus(); else rfb.blur();
  }, []);

  useEffect(apply, [apply, interactive, fullscreen, conn]);

  // react-vnc only retries by itself when there is no onDisconnect handler
  const mounted = useRef(true);
  const retry = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => { mounted.current = false; clearTimeout(retry.current); }, []);
  const onDisconnect = useCallback((e?: CustomEvent<{ clean: boolean }>) => {
    if (!mounted.current) return;
    setConn("disconnected");
    if (e?.detail.clean) return;           // our own disconnect (reconnect / unmount)
    clearTimeout(retry.current);
    retry.current = setTimeout(() => {
      if (!mounted.current) return;
      setConn("connecting");
      vnc.current?.connect();
    }, RETRY_MS);
  }, []);

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === frame.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void frame.current?.requestFullscreen();
  };

  return (
    <div ref={frame}
      className={cn("group relative w-full min-w-0 overflow-hidden rounded-lg bg-black",
        fullscreen ? "flex items-center justify-center" : "mx-auto aspect-[16/10] max-w-3xl",
        interactive && "ring-success ring-2")}>
      {config.data && (
        <Suspense>
          <VncScreen
            ref={vnc}
            url={vncUrl()}
            className="size-full"
            viewOnly={!interactive}
            scaleViewport
            background="#000"
            qualityLevel={TILE.quality}
            compressionLevel={TILE.compression}
            rfbOptions={{ credentials: { password: config.data.password } }}
            onConnect={() => { setConn("live"); apply(); }}
            onDisconnect={onDisconnect}
            onSecurityFailure={() => setConn("disconnected")}
          />
        </Suspense>
      )}
      {conn !== "live" && (
        <div className="text-muted-foreground absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/80 text-sm">
          {conn === "connecting"
            ? <><Loader2 className="size-5 animate-spin" /> Connecting…</>
            : <>
                <MonitorOff className="size-5" />
                <span>Can't reach the bot's screen — retrying.</span>
                <span className="text-xs">Is the runetools container up, with VNC on (VNC=1)?</span>
              </>}
        </div>
      )}
      {conn === "live" && phase === "pausing" && (
        <div className="absolute inset-x-0 top-0 bg-black/70 px-3 py-1.5 text-center text-xs text-white">
          Waiting for the bot to reach its pause… (no answer in {NO_ANSWER_MS / 1000} s = no bot running)
        </div>
      )}
      <Button variant="secondary" size="icon-sm" onClick={toggleFullscreen}
        className="absolute right-2 bottom-2 opacity-0 transition-opacity group-hover:opacity-90 focus-visible:opacity-90"
        title={fullscreen ? "Exit fullscreen" : "Fullscreen"} aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}>
        {fullscreen ? <Minimize /> : <Maximize />}
      </Button>
    </div>
  );
}
