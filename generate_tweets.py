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
        system="""Tu Sarcastic Sindhi hai — Chandan Bulani, Indian tech consumer advocate, 391K YouTube subscribers.

Tweet likhne ka formula — 2 complete sentences:
1. NEWS FACT: Exact kya hua — company, number, price ke saath. Poora sentence.
2. CONSUMER POV: Aam aadmi ko isse kya fark padega. Sharp aur sarcastic. Poora sentence.

RULES:
- 200-260 characters total (hashtags samet)
- Pure English — no Hindi words at all
- Rupee symbol ₹ use karo
- 2 relevant hashtags end mein
- Dono sentences grammatically complete
- Output: SIRF tweet text, koi quotes nahi

EXAMPLE:
OnePlus 15T launched in India at ₹49,999 with a massive 7500mAh battery. Finally a phone that wont die before your workday ends — but will your wallet survive? #OnePlus #IndianTech""",
        messages=[{
            "role": "user",
            "content": f"Write a 2-sentence English tweet about this India tech news: {topic}"
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
    feeds = [
        "https://news.google.com/rss/search?q=Jio+Airtel+telecom+India&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=tech+scam+India+consumer&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=smartphone+launch+India+price&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=Amazon+Flipkart+India+scam&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=TRAI+internet+policy+India&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=Apple+Samsung+India+price&hl=en-IN&gl=IN",
    ]
    headlines = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.title.split(" - ")[0].strip()
                if len(title) > 20:
                    headlines.append(title)
        except:
            pass
    return list(set(headlines))[:40]

def pick_10_topics(headlines, library_topics):
    h_text = "\n".join([f"- {h}" for h in headlines])
    l_text = "\n".join([f"- {t['text']}" for t in library_topics]) if library_topics else "None"

    sys_msg = "You are a content strategist for Sarcastic Sindhi, India's top consumer-advocate tech creator."
    user_msg = (
        f"Pick the 10 best topics for viral Indian tech tweets from these headlines and library topics.\n\n"
        f"NEWS:\n{h_text}\n\nLIBRARY TOPICS:\n{l_text}\n\n"
        f"Prioritize: scams, consumer rights, price reveals, telecom updates, gadget launches.\n"
        f"Return ONLY a JSON array of 10 strings:\n"
        f'["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7", "topic8", "topic9", "topic10"]'
    )

    raw = ask_gemini(sys_msg, user_msg)
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        start = clean.index("[")
        end = clean.rindex("]") + 1
        return json.loads(clean[start:end])
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
                {"text": "Approve", "callback_data": f"approve_{i}"},
                {"text": "Edit",    "callback_data": f"edit_{i}"},
                {"text": "Skip",    "callback_data": f"skip_{i}"}
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
