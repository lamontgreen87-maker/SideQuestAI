# Running Hive Science Bot on Android (Termux)

## 1. Install Termux
Install **Termux** from **F-Droid** or GitHub (avoid the outdated Play Store version).

## 2. Install Python & Dependencies
```bash
pkg update && pkg upgrade -y
pkg install -y python git
pip install fastapi uvicorn requests pydantic
```

## 3. Configure Your Free Groq API Key
1. Create a free API key at <https://console.groq.com/keys>.
2. In `hive_mind/`, copy `.env.example` to `.env` and paste your key:
```bash
cp .env.example .env
nano .env
```
Set:
```env
BRAIN_PROVIDER=groq
BRAIN_API_KEY=gsk_...
BRAIN_MODEL=llama-3.3-70b-versatile
SCIENCE_INTERVAL_MINUTES=30
```

## 4. Start the Bot
```bash
chmod +x start_phone_bot.sh
./start_phone_bot.sh
```
Open your phone's web browser (Chrome/Firefox) to:
**`http://127.0.0.1:8000/science`**

> **Tip:** In Android Settings -> Apps -> Termux -> Battery, set battery usage to **Unrestricted** so Android doesn't pause the bot in the background.

