#!/usr/bin/env bash
# Measure a runetools image's footprint: image size, then RAM/CPU of a running
# container — idle (display stack only) and with the RuneLite client started
# (it reaches the login screen; no account needed).
#
#   docker/measure.sh runetools:latest            # defaults
#   SAMPLES=20 CLIENT_WAIT=180 docker/measure.sh runetools:slim
#
# Prints one summary line per phase; nothing is left running afterwards.
set -euo pipefail
export LC_ALL=C   # decimal points, not commas, whatever the host locale

IMAGE="${1:?usage: docker/measure.sh <image>}"
SAMPLES="${SAMPLES:-10}"          # docker stats samples per phase
INTERVAL="${INTERVAL:-2}"         # seconds between samples
SETTLE="${SETTLE:-15}"            # seconds after start before the idle phase
CLIENT_WAIT="${CLIENT_WAIT:-150}" # seconds for RuneLite to download + reach the login screen
CLIENT_CMD="${CLIENT_CMD:-runelite}"   # command inside the image that starts the client (docker/runelite)
NAME="rt-measure-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

to_mib() {  # "123.4MiB" / "1.2GiB" / "512KiB" -> MiB
    awk -v v="$1" 'BEGIN {
        n = v + 0
        if (v ~ /GiB$/) n *= 1024; else if (v ~ /KiB$/) n /= 1024; else if (v ~ /B$/ && v !~ /iB$/) n /= 1048576
        printf "%.1f", n }'
}

sample() {  # phase label -> "label: mem avg/max MiB, cpu avg/max %"
    local label="$1" mems=() cpus=() line mem cpu
    for _ in $(seq "$SAMPLES"); do
        line=$(docker stats --no-stream --format '{{.MemUsage}}|{{.CPUPerc}}' "$NAME")
        mem=$(to_mib "${line%% /*}")
        cpu="${line##*|}"; cpu="${cpu%\%}"
        mems+=("$mem"); cpus+=("$cpu")
        sleep "$INTERVAL"
    done
    printf '%s\n' "${mems[@]}" | awk -v l="$label" -v c="$(printf '%s ' "${cpus[@]}")" '
        { s += $1; if ($1 > m) m = $1 }
        END { n = split(c, a, " "); for (i = 1; i <= n; i++) { cs += a[i]; if (a[i] > cm) cm = a[i] }
              printf "%-8s mem avg %7.1f MiB  max %7.1f MiB | cpu avg %5.1f%%  max %5.1f%%\n", l, s / NR, m, cs / n, cm }'
}

size=$(docker image inspect "$IMAGE" --format '{{.Size}}')
printf 'image    %s  %.0f MB\n' "$IMAGE" "$(awk -v s="$size" 'BEGIN { print s / 1e6 }')"

docker run -d --name "$NAME" --shm-size=1g "$IMAGE" sleep infinity >/dev/null
sleep "$SETTLE"
sample idle

docker exec -d "$NAME" sh -c "$CLIENT_CMD > /tmp/client.log 2>&1"
sleep "$CLIENT_WAIT"
if ! docker exec "$NAME" sh -c 'pgrep -f net.runelite >/dev/null'; then
    echo "client did not start — last log lines:" >&2
    docker exec "$NAME" tail -20 /tmp/client.log >&2 || true
    exit 1
fi
sample client
