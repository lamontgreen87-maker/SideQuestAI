#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

echo "[1/4] Updating Termux packages..."
pkg update -y && pkg upgrade -y
pkg install -y python python-numpy python-scipy git nodejs

echo "[2/4] Installing Python dependencies..."
pip install --upgrade pip
pip install fastapi uvicorn requests pydantic h5py emcee gwosc

echo "[3/4] Downloading public GWOSC .hdf5 strain snippets..."
if [ ! -f memory/gwosc_strain/manifest.json ]; then
  python fetch_gwosc_strain.py || echo "Warning: GWOSC strain download failed; you can retry later with: python fetch_gwosc_strain.py"
fi

echo "[4/4] Checking .env configuration..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Edit .env now with your Groq API key: nano .env"
fi

chmod +x start_phone_bot.sh
echo "Setup complete! Run: ./start_phone_bot.sh"
