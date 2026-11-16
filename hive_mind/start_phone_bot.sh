#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

# Keep Android CPU awake when screen turns off (if Termux:API / termux-wake-lock is available)
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
fi

if [ ! -f .env ]; then
  echo "No .env found! Run ./phone_setup.sh or copy .env.example to .env and add your free Groq API key:"
  echo "  cp .env.example .env"
  exit 1
fi

if [ ! -f memory/gwosc_strain/manifest.json ]; then
  echo "Fetching public GWOSC .hdf5 strain snippets..."
  python fetch_gwosc_strain.py || true
fi

echo "Starting SideQuestAI Phone Bot..."
echo "Open in your phone browser: http://127.0.0.1:8000/science"
exec python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
