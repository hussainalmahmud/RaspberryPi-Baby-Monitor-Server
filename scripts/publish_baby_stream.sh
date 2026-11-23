#!/usr/bin/env bash
set -euo pipefail

RTSP_PORT="${RTSP_PORT:-8554}"
MIC_DEVICE="${MIC_DEVICE:-plughw:CARD=Device,DEV=0}"
API_URL="http://127.0.0.1:9997/v3/paths/get/baby"
ffmpeg_pid=""

waited_seconds=0
while [ "${waited_seconds}" -lt 30 ]; do
    if arecord -l 2>/dev/null | grep -q "USB PnP Sound Device"; then
        break
    fi
    sleep 1
    waited_seconds=$((waited_seconds + 1))
done

amixer -c Device sset Mic 12 >/dev/null 2>&1 || true
amixer -c Device sset "Auto Gain Control" off >/dev/null 2>&1 || true

stop_ffmpeg() {
    if [ -n "${ffmpeg_pid}" ] && kill -0 "${ffmpeg_pid}" 2>/dev/null; then
        kill "${ffmpeg_pid}" 2>/dev/null || true
        sleep 1
        kill -9 "${ffmpeg_pid}" 2>/dev/null || true
    fi
}

trap stop_ffmpeg INT TERM EXIT

ffmpeg -hide_banner -loglevel warning \
    -thread_queue_size 1024 \
    -fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0 \
    -timeout 15000000 -rtsp_transport tcp -i "rtsp://127.0.0.1:${RTSP_PORT}/cam" \
    -thread_queue_size 8192 -f alsa -channels 1 -sample_rate 48000 \
    -i "${MIC_DEVICE}" \
    -map 0:v:0 -map 1:a:0 \
    -c:v copy \
    -af aresample=async=1 \
    -c:a libopus -application lowdelay -b:a 24k -ac 1 -ar 48000 \
    -muxdelay 0 -muxpreload 0 \
    -pkt_size 1200 \
    -f rtsp -rtsp_transport tcp "rtsp://127.0.0.1:${RTSP_PORT}/baby" &
ffmpeg_pid=$!

slept_seconds=0
while [ "${slept_seconds}" -lt 20 ]; do
    if ! kill -0 "${ffmpeg_pid}" 2>/dev/null; then
        wait "${ffmpeg_pid}" || true
        exit 1
    fi
    sleep 1
    slept_seconds=$((slept_seconds + 1))
done

while kill -0 "${ffmpeg_pid}" 2>/dev/null; do
    if ! curl -sf "${API_URL}" | grep -q '"ready":true'; then
        echo "baby path is not ready; restarting publisher" >&2
        stop_ffmpeg
        exit 1
    fi
    sleep 8
done

wait "${ffmpeg_pid}"
exit_code=$?
ffmpeg_pid=""
exit "${exit_code}"
