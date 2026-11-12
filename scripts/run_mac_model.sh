#!/bin/sh
# NX-005: bounded, local text smoke test; no server or automatic download.
set -eu

if [ "$#" -gt 1 ]; then
    echo 'Usage: sh scripts/run_mac_model.sh ["prompt"]' >&2
    exit 2
fi

nexus_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
nexus_runtime="$nexus_root/local/build/llama-metal/bin/llama-completion"
nexus_model="$nexus_root/models/Qwen3.8-27B-Q4_K_M.gguf"

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo 'This smoke test requires native macOS arm64; see docs/mac-metal.md.' >&2
    exit 1
fi
if [ ! -x "$nexus_runtime" ] || [ ! -f "$nexus_model" ]; then
    echo 'Build or verified model missing; follow docs/mac-metal.md first.' >&2
    exit 1
fi

exec "$nexus_runtime" \
    --model "$nexus_model" --offline --device MTL0 --n-gpu-layers all \
    --fit off --ctx-size 1024 --batch-size 128 --ubatch-size 128 --threads 4 \
    --predict 128 --seed 42 --temp 0 --jinja --conversation --single-turn \
    --reasoning off --no-display-prompt --color off \
    --prompt "${1:-Antworte nur mit: Hallo vom Mac.}"
