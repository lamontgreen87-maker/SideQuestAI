#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

echo "[1/4] Updating Termux packages..."
pkg update -y && pkg upgrade -y
pkg install -y python python-pip python-numpy python-scipy git nodejs
pkg install -y python-h5py || true

echo "[2/4] Installing Python dependencies..."
pip install --no-input fastapi uvicorn requests pydantic emcee gwosc
python -c "import h5py" 2>/dev/null || pip install --no-input h5py || echo "Note: h5py optional on Termux; GWTC catalog + core bot will still run."

echo "[3/4] Downloading public GWOSC .hdf5 strain snippets..."
if [ ! -f memory/gwosc_strain/manifest.json ]; then
  python fetch_gwosc_strain.py || echo "Warning: GWOSC strain download skipped; you can retry later."
fi

echo "[4/4] Checking .env configuration..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Edit .env now with your Groq API key: nano .env"
fi

chmod +x start_phone_bot.sh
echo "Setup complete! Run: ./start_phone_bot.sh"
