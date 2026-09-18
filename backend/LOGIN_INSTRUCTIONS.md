# Telegram Printer Account Login Guide

## Current Status
- ✅ Proxy running at 127.0.0.1:7890
- ✅ Dependencies installed (pysocks, python-socks)
- ⚠️ Session file created but not authenticated

## How to Login

### Step 1: Run Login Script
```bash
cd <project-root>/backend
source venv/bin/activate
python login_printer.py
```

### Step 2: Enter Your Credentials
When prompted:
1. **Phone number**: Enter your printer account phone (e.g., +84xxxxxxxxx)
2. **Verification code**: Check your Telegram app for the code
3. **Password**: Only if you have 2FA enabled

### Step 3: Verify Success
You should see:
```
✅ Login successful!
   User: [Your Name]
   Username: @[username]
   Phone: +84xxxxxxxxx
   ID: [numeric_id]
```

### Step 4: Start Live Chat Demo
```bash
python live_chat_demo.py
```

## What Happens Next

Once `live_chat_demo.py` is running:
1. Open your personal Telegram app
2. Search for the "printer" account by username or phone number
3. Send it a message like "Xin chào" (Hello in Vietnamese)
4. The bot will reply with an arithmetic verification question
5. Answer correctly (e.g., "15")
6. AI will start generating natural responses using DeepSeek

## Troubleshooting

**If connection times out:**
- Check proxy is running: `lsof -i :7890`
- Restart proxy if needed

**If session is locked:**
```bash
rm -f sessions/printer.session-journal
```

**If authentication fails:**
- Delete session and retry: `rm sessions/printer.session*`
- Run login script again

## Demo Features Demonstrated
- ✅ Arithmetic verification (filters bots)
- ✅ AI-powered Vietnamese conversation (DeepSeek-V3)
- ✅ Natural typing delay simulation
- ✅ Proactive information extraction
- ✅ Context-aware multi-turn dialogue
