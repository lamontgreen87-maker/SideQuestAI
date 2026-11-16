# Running SideQuestAI ScienceBot on Android (Termux — No APK Needed)

## 1. Install Termux
Install **Termux** from **F-Droid** or GitHub (avoid the outdated Play Store version).

## 2. Clone & Run One-Step Phone Setup
```bash
pkg install -y git
git clone https://github.com/lamontgreen87-maker/SideQuestAI.git
cd SideQuestAI/hive_mind
chmod +x phone_setup.sh
./phone_setup.sh
```

## 3. Add Your Free Groq API Key
Edit `.env`:
```bash
nano .env
```
Set:
```env
BRAIN_PROVIDER=groq
BRAIN_API_KEY=gsk_...
BRAIN_MODEL=llama-3.3-70b-versatile
SCIENCE_RESEARCH_PHASE=frontier
SCIENCE_INTERVAL_MINUTES=30
SCIENCE_SCHEDULE_ENABLED=1
SCIENCE_SCHEDULE_START=22:00
SCIENCE_SCHEDULE_END=07:00
```

*(Optional — auto-publish to `sidequestai.org` from your phone: run `npx wrangler login` once in Termux.)*

## 4. Start the Phone Bot
```bash
./start_phone_bot.sh
```
Open your phone's browser to: **`http://127.0.0.1:8000/science`**

You can also toggle and adjust the **Alarm Window** (`22:00 – 07:00`, or any hours you want) live in the `/science` dashboard so it only runs during your set hours and sleeps the rest of the day.

> **Tip:** In Android **Settings → Apps → Termux → Battery**, set battery usage to **Unrestricted** so Android doesn't pause it in the background.
