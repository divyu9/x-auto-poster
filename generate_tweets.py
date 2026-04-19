import os
import json
import base64
import feedparser
import requests
import time
import anthropic
from datetime import datetime, timedelta

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

def load_library():
    data, _ = gh_get("topics_library.json")
    return data.get("topics", []) if data else []

def fetch_news():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    BLOCK = [
        "share price", "stock price", "nse", "bse", "sensex", "nifty", "ipo",
        "mutual fund", "equity", "market cap", "quarterly result", "revenue",
        "profit", "earnings", "dividend", "investor", "target price", "analyst",
        "large cap", "mid cap", "fund", "blackrock", "asset management",
        "ipl", "cricket", "kkr", "csk", "rcb", "srh", "pbks", "dc match",
        "broadcast right", "streaming right", "ott right",
        "bollywood", "box office", "film", "web series",
        "election", "parliament", "minister", "scheme",
    ]

    feeds = [
        f"https://news.google.com/rss/search?q=Jio+new+plan+launch+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=Airtel+new+launch+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=TRAI+consumer+ruling+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=smartphone+launch+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=Samsung+Apple+OnePlus+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=cyber+fraud+scam+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=Amazon+Flipkart+consumer+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=UPI+digital+payment+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=5G+broadband+internet+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q=new+app+gadget+India+after:{yesterday}&hl=en-IN&gl=IN&ceid=IN:en",
    ]

    cutoff_ts = time.time() - (72 * 3600)
    headlines = []
    seen = set()
    blocked = 0

    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                pub = entry.get("published_parsed")
                if pub and time.mktime(pub) < cutoff_ts:
                    continue
                title = entry.title.split(" - ")[0].strip()
                tl = title.lower()
                if any(kw in tl for kw in BLOCK):
                    blocked += 1
                    print(f"  BLOCKED: {title[:70]}")
                    continue
                if len(title) > 20 and title not in seen:
                    seen.add(title)
                    headlines.append(title)
        except Exception as e:
            print(f"Feed error: {e}")

    print(f"Fetched {len(headlines)} headlines, blocked {blocked}")
    return headlines[:50]

def pick_10_topics(headlines, library_topics):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    h_text = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])
    l_text = "\n".join([f"- {t['text']}" for t in library_topics]) if library_topics else ""

    prompt = f"Select best unique consumer tech topics from these headlines.\n\nHEADLINES:\n{h_text}"
    if l_text:
        prompt += f"\n\nLIBRARY TOPICS (also include if relevant):\n{l_text}"
    prompt += "\n\nReturn a JSON array of topic strings only."

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system="""You select topics for Sarcastic Sindhi — Indian consumer tech channel (391K subs).
Niche: new smartphone launches, new telecom plans, consumer scams, internet/broadband, gadgets, apps, digital payments.

RULES:
- Only NEW announcements — not commentary on existing old plans/products
- Skip: stock prices, IPO, funds, cricket/IPL, movies, OTT rights, politics
- Each topic must be a DIFFERENT event
- If fewer than 10 good topics exist, return fewer — never pad with irrelevant ones
- Return ONLY valid JSON array of strings. No markdown, no explanation.""",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = res.content[0].text.strip()
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        topics = json.loads(clean[clean.index("["):clean.rindex("]")+1])
        print(f"Selected {len(topics)} topics")
        return topics[:10]
    except Exception as e:
        print(f"Topic parse failed: {e}")
        return headlines[:10]

def write_tweet(topic):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="""You are Sarcastic Sindhi (Chandan Bulani) — friendly Indian tech creator sharing news like a well-informed friend.

Write ONE tweet — exactly 2 complete sentences:
SENTENCE 1: News fact with specific number/price/company. Clear and informative.
SENTENCE 2: One casual friendly take on what this means for Indian consumers. Slightly witty OK, NOT a taunt.

TONE: Like a friend texting tech news. Helpful, not cynical.
AVOID: scam, trap, fooling, pathetic, angry questions.
RULES: Both complete. 200-260 chars total. Pure English. Rupee symbol. 2 hashtags at end. Output ONLY tweet text.""",
        messages=[{"role": "user", "content": f"Write a 2-sentence informative tweet about: {topic}"}]
    )
    tweet = res.content[0].text.strip().strip('"').strip("'")
    if len(tweet) > 280:
        lp = tweet[:277].rfind('.')
        tweet = tweet[:lp+1] if lp > 150 else tweet[:277] + "..."
    return tweet

def send_to_telegram(all_tweets):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
        "chat_id": chat_id,
        "text": (
            f"Sarcastic Sindhi — {datetime.now().strftime('%d %b %Y')}\n\n"
            f"{len(all_tweets)} tweets ready!\n"
            f"Post Now = instant\nSchedule = pick time slot"
        )
    })

    for i, t in enumerate(all_tweets):
        tweet_text = t["tweet"] or "[Tweet generation failed]"
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Option {i+1}/{len(all_tweets)}\n\n{tweet_text}\n\n{len(tweet_text)}/280 chars",
            "reply_markup": {"inline_keyboard": [[
                {"text": "🚀 Post Now",  "callback_data": f"postnow_{i}"},
                {"text": "🕐 Schedule", "callback_data": f"sched_{i}"},
                {"text": "✏️ Edit",     "callback_data": f"edit_{i}"},
            ], [
                {"text": "❌ Skip", "callback_data": f"skip_{i}"},
            ]]}
        })
        if res.ok:
            all_tweets[i]["message_id"] = res.json()["result"]["message_id"]
    return all_tweets

def main():
    print(f"[{datetime.now().isoformat()}] Starting generation...")
    headlines = fetch_news()
    library = load_library()
    print(f"Library: {len(library)} custom topics")
    topics = pick_10_topics(headlines, library)

    all_tweets = []
    for i, topic in enumerate(topics):
        print(f"[{i+1}/{len(topics)}] {topic[:60]}...")
        tweet = write_tweet(topic)
        print(f"  -> ({len(tweet)} chars) {tweet[:70]}...")
        all_tweets.append({
            "topic": topic, "tweet": tweet, "status": "pending",
            "slot_label": None, "utc_hour": None, "utc_min": None,
            "message_id": None, "instant": False
        })
        time.sleep(3)

    all_tweets = send_to_telegram(all_tweets)

    payload = {
        "tweets": all_tweets,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
    }
    _, sha = gh_get("pending_tweets.json")
    ok = gh_put("pending_tweets.json", payload, sha, f"Daily tweets {payload['date']}")
    print("Saved!" if ok else "SAVE FAILED")
    print("Done! Check Telegram.")

if __name__ == "__main__":
    main()
