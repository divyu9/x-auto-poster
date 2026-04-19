import os
import json
import base64
import feedparser
import requests
import time
import anthropic
from datetime import datetime

SLOTS = [
    {"label": "11 AM IST", "utc_hour": 5,  "utc_min": 30},
    {"label": "1 PM IST",  "utc_hour": 7,  "utc_min": 30},
    {"label": "5 PM IST",  "utc_hour": 11, "utc_min": 30},
    {"label": "9 PM IST",  "utc_hour": 15, "utc_min": 30},
]

def gh_headers():
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def gh_get(filename):
    repo = os.environ["GITHUB_REPOSITORY"]
    res = requests.get(
        f"https://api.github.com/repos/{repo}/contents/{filename}",
        headers=gh_headers()
    )
    if not res.ok:
        return None, None
    data = res.json()
    return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]

def gh_put(filename, payload, sha, message):
    repo = os.environ["GITHUB_REPOSITORY"]
    encoded = base64.b64encode(
        json.dumps(payload, indent=2, ensure_ascii=False).encode()
    ).decode()
    body = {"message": message, "content": encoded, "branch": "main"}
    if sha:
        body["sha"] = sha
    res = requests.put(
        f"https://api.github.com/repos/{repo}/contents/{filename}",
        json=body, headers=gh_headers()
    )
    return res.ok

# ── Gemini — only for topic selection (free) ──────────────────────────────────
def ask_gemini(system_prompt, user_prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={os.environ['GEMINI_API_KEY']}"
    payload = {
        "contents": [{"parts": [{"text": f"SYSTEM: {system_prompt}\nUSER: {user_prompt}"}]}],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 600}
    }
    res = requests.post(url, json=payload)
    if not res.ok:
        print(f"Gemini Error: {res.status_code} {res.text}")
        return ""
    try:
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Gemini parse error: {e}")
        return ""

# ── Claude Haiku — for tweet writing (quality) ────────────────────────────────
def write_tweet(topic):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="""You are Sarcastic Sindhi (Chandan Bulani) — a friendly Indian tech creator sharing news like a well-informed friend, not a critic.

Write ONE tweet with exactly 2 complete sentences:
SENTENCE 1: The news fact — what happened, with specific number/price/company. Clear and informative.
SENTENCE 2: One casual, friendly take on what this means for Indian consumers. Slightly witty is fine but NOT a taunt or criticism.

TONE: Like a friend texting you about tech news. Helpful and curious, not cynical.
AVOID: words like "scam", "trap", "fooling", "joke", "pathetic", rhetorical angry questions.

RULES:
- Both sentences complete — never cut off mid-sentence
- 200-260 characters total including hashtags
- Pure English
- Use ₹ for prices
- 2 relevant hashtags at end
- Output ONLY tweet text, no quotes

GOOD EXAMPLE:
OnePlus 15T launches in India at ₹49,999 with a 7500mAh battery and 100W charging. If battery anxiety was your issue, this one actually looks worth considering. #OnePlus #IndianTech

BAD EXAMPLE (too cynical):
OnePlus 15T at ₹49,999 — another overpriced phone Indians will blindly buy for marketing hype. #OnePlus #IndianTech""",
        messages=[{
            "role": "user",
            "content": f"Write a 2-sentence informative tweet about this India tech news: {topic}"
        }]
    )

    tweet = res.content[0].text.strip().strip('"').strip("'")

    # Smart trim — cut at last complete sentence if over 280
    if len(tweet) > 280:
        last_period = tweet[:277].rfind('.')
        tweet = tweet[:last_period + 1] if last_period > 150 else tweet[:277] + "..."

    return tweet

def load_library():
    data, _ = gh_get("topics_library.json")
    return data.get("topics", []) if data else []

def fetch_news():
    import time as time_module
    from datetime import datetime, timedelta

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Hard blocklist — filtered BEFORE sending to Gemini
    BLOCK_KEYWORDS = [
        "share price", "stock price", "nse", "bse", "sensex", "nifty",
        "ipo", "mutual fund", "equity", "market cap", "shares rise",
        "shares fall", "shares up", "shares down", "stock market",
        "quarterly results", "q1 results", "q2 results", "q3 results", "q4 results",
        "revenue", "profit", "earnings", "dividend", "investor",
        "target price", "buy rating", "sell rating", "analyst",
    ]

    feeds = [
        f"https://news.google.com/rss/search?q=Jio+telecom+plan+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=Airtel+plan+network+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=TRAI+regulation+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=smartphone+launch+price+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=Samsung+Apple+OnePlus+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=cyber+fraud+scam+India+consumer+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=Amazon+Flipkart+consumer+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=UPI+payment+app+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=broadband+internet+speed+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=AI+app+gadget+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
    ]

    cutoff_ts = time_module.time() - (72 * 3600)
    headlines = []
    seen = set()
    blocked = 0

    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                pub = entry.get("published_parsed")
                if pub:
                    if time_module.mktime(pub) < cutoff_ts:
                        continue

                title = entry.title.split(" - ")[0].strip()
                title_lower = title.lower()

                # Hard filter — skip stock market headlines
                if any(kw in title_lower for kw in BLOCK_KEYWORDS):
                    blocked += 1
                    print(f"  BLOCKED: {title[:60]}")
                    continue

                if len(title) > 25 and title not in seen:
                    seen.add(title)
                    headlines.append(title)
        except Exception as e:
            print(f"Feed error: {e}")

    print(f"Fetched {len(headlines)} fresh headlines, blocked {blocked} stock/finance topics")
    return headlines[:50]

def pick_10_topics(headlines, library_topics):
    h_text = "\n".join([f"- {h}" for h in headlines])
    l_text = "\n".join([f"- {t['text']}" for t in library_topics]) if library_topics else "None"

    sys_msg = "You are a content strategist for Sarcastic Sindhi, India's top consumer-advocate tech creator (391K YouTube subscribers). His niche: consumer tech, telecom, gadgets, scams, digital life for Indians."
    user_msg = (
        f"Pick 10 UNIQUE and DIVERSE topics for Indian tech tweets. Each topic must be about a DIFFERENT news story.\n\n"
        f"STRICT RULES:\n"
        f"- NO stock market, share prices, NSE, BSE, Sensex, Nifty, IPO, mutual funds\n"
        f"- NO duplicate stories — if multiple headlines are about the same event, pick only 1\n"
        f"- NO politics unrelated to consumer tech\n"
        f"- ONLY: telecom plans, smartphones, gadgets, apps, internet, consumer scams, digital payments, AI tools, tech company news\n"
        f"- Each topic must be genuinely different\n\n"
        f"NEWS:\n{h_text}\n\nLIBRARY TOPICS:\n{l_text}\n\n"
        f'Return ONLY a JSON array of 10 unique strings, no markdown:\n'
        f'["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7", "topic8", "topic9", "topic10"]'
    )

    raw = ask_gemini(sys_msg, user_msg)
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        start_idx = clean.index("[")
        end_idx = clean.rindex("]") + 1
        return json.loads(clean[start_idx:end_idx])
    except:
        print("Topic parse failed, using headlines directly")
        return headlines[:10]

def send_to_telegram(all_tweets):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
        "chat_id": chat_id,
        "text": (
            f"Sarcastic Sindhi — {datetime.now().strftime('%d %b %Y')}\n\n"
            f"10 tweets ready! 4 approve karo:\n"
            f"1st approved → Instant post\n"
            f"2nd approved → 1 PM\n"
            f"3rd approved → 5 PM\n"
            f"4th approved → 9 PM"
        )
    })

    for i, t in enumerate(all_tweets):
        tweet_text = t["tweet"] or "[Tweet generation failed]"
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Option {i+1}/10\n\n{tweet_text}\n\n{len(tweet_text)}/280 chars",
            "reply_markup": {"inline_keyboard": [[
                {"text": "🚀 Post Now",  "callback_data": f"postnow_{i}"},
                {"text": "🕐 Schedule", "callback_data": f"sched_{i}"},
                {"text": "✏️ Edit",     "callback_data": f"edit_{i}"},
            ], [
                {"text": "❌ Skip",     "callback_data": f"skip_{i}"},
            ]]}
        })
        if res.ok:
            all_tweets[i]["message_id"] = res.json()["result"]["message_id"]
    return all_tweets

def main():
    print(f"[{datetime.now().isoformat()}] Starting generation...")

    headlines = fetch_news()
    print(f"Fetched {len(headlines)} headlines")

    library = load_library()
    print(f"Library: {len(library)} custom topics")

    topics = pick_10_topics(headlines, library)
    print(f"Selected {len(topics)} topics")

    all_tweets = []
    for i, topic in enumerate(topics):
        print(f"[{i+1}/10] Writing: {topic[:60]}...")
        tweet = write_tweet(topic)
        print(f"  → ({len(tweet)} chars) {tweet[:80]}...")
        all_tweets.append({
            "topic": topic,
            "tweet": tweet,
            "status": "pending",
            "slot_index": None,
            "slot_label": None,
            "utc_hour": None,
            "utc_min": None,
            "message_id": None,
            "instant": False
        })
        time.sleep(3)

    all_tweets = send_to_telegram(all_tweets)

    payload = {
        "tweets": all_tweets,
        "slots": SLOTS,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "approved_count": 0
    }
    _, sha = gh_get("pending_tweets.json")
    ok = gh_put("pending_tweets.json", payload, sha, f"Daily tweets {payload['date']}")
    print("Saved to repo" if ok else "SAVE FAILED")
    print("Done! Check Telegram.")

if __name__ == "__main__":
    main()
