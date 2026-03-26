import os
import json
import base64
import feedparser
import anthropic
import requests
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

def load_library():
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}/contents/topics_library.json"
    res = requests.get(url, headers=gh_headers())
    if not res.ok:
        return []
    data = res.json()
    content = json.loads(base64.b64decode(data["content"]).decode())
    return content.get("topics", [])

def fetch_news():
    feeds = [
        "https://news.google.com/rss/search?q=Jio+Airtel+BSNL+telecom+India&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=tech+scam+fraud+India+consumer&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=smartphone+laptop+launch+India+price&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=TRAI+internet+policy+India&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Amazon+Flipkart+India+consumer&hl=en-IN&gl=IN&ceid=IN:en",
    ]
    headlines = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                title = entry.title.split(" - ")[0].strip()
                headlines.append(title)
        except Exception as e:
            print(f"Feed error: {e}")
    seen = set()
    unique = []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return unique[:20]

def pick_topics(headlines, library_topics):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    headlines_text = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])

    lib_section = ""
    if library_topics:
        lib_text = "\n".join([f"- {t['text']}" for t in library_topics])
        lib_section = f"\n\nAlso consider these custom topics from my library (include if relevant news found):\n{lib_text}"

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": f"""Pick 4 best topics for Sarcastic Sindhi — Indian consumer-advocate tech creator (391K YouTube subs). Audience: Indian males 18-35, want to avoid scams and spend smartly.

News headlines today:
{headlines_text}{lib_section}

Return ONLY a JSON array of 4 topic strings (mix news headlines + library topics if relevant), no markdown:
["topic1", "topic2", "topic3", "topic4"]"""}]
    )
    raw = res.content[0].text.strip().replace("```json","").replace("```","").strip()
    return json.loads(raw)

def write_tweet(topic):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    res = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system="""You are Sarcastic Sindhi's X voice — Chandan Bulani, consumer-advocate tech creator.

Rules:
- Hinglish (natural Hindi-English mix, how Chandan actually speaks)
- Sarcastic, brutally honest, consumer POV — "they're doing this TO you" energy
- First 5 words must grab. No warm-up.
- Use rupee symbol for prices. Reference Jio/Airtel/Flipkart/Amazon India/TRAI when relevant.
- End with sharp verdict OR rhetorical question
- What does this mean for aam aadmi's wallet?
- Under 280 characters including 2-3 hashtags
- Output ONLY the tweet. No quotes around it.""",
        messages=[{"role": "user", "content": f"Write one consumer-POV sarcastic Hinglish tweet about: {topic}"}]
    )
    tweet = res.content[0].text.strip().replace('"', '')
    return tweet[:280] if len(tweet) > 280 else tweet

def send_telegram(tweets):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
        "chat_id": chat_id,
        "text": (
            f"🔴 *Sarcastic Sindhi — {datetime.now().strftime('%d %b %Y')}*\n\n"
            f"4 tweets ready! Approve karo — auto-post honge:\n"
            f"• Tweet 1 → 11 AM\n• Tweet 2 → 1 PM\n• Tweet 3 → 5 PM\n• Tweet 4 → 9 PM\n\n"
            f"_Har tweet ke neeche Approve ya Skip karo_\n\n"
            f"💡 `/help` for all commands"
        ),
        "parse_mode": "Markdown"
    })

    for i, t in enumerate(tweets):
        slot = SLOTS[i]
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"📱 *Tweet {i+1}/4 — {slot['label']}*\n\n{t['tweet']}\n\n`{len(t['tweet'])}/280 chars`",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [[
                {"text": f"✅ Approve", "callback_data": f"approve_{i}"},
                {"text": "❌ Skip", "callback_data": f"skip_{i}"}
            ]]}
        })
        if res.ok:
            tweets[i]["message_id"] = res.json()["result"]["message_id"]
            print(f"Sent tweet {i+1} — {slot['label']}")
    return tweets

def save_to_repo(tweets):
    repo = os.environ["GITHUB_REPOSITORY"]
    payload = {
        "tweets": tweets,
        "generated_at": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "slots": SLOTS
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    encoded = base64.b64encode(content.encode()).decode()
    url = f"https://api.github.com/repos/{repo}/contents/pending_tweets.json"
    get_res = requests.get(url, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    })
    sha = get_res.json().get("sha") if get_res.ok else None
    body = {"message": f"Daily tweets {datetime.now().strftime('%Y-%m-%d')}", "content": encoded}
    if sha:
        body["sha"] = sha
    res = requests.put(url, json=body, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    })
    print("Saved to repo" if res.ok else f"Save error: {res.text}")

def main():
    print(f"[{datetime.now().isoformat()}] Generating tweets...")
    headlines = fetch_news()
    print(f"Fetched {len(headlines)} headlines (free RSS)")
    library_topics = load_library()
    print(f"Loaded {len(library_topics)} custom topics from library")
    topics = pick_topics(headlines, library_topics)
    print(f"Selected: {topics}")
    tweets = []
    for i, topic in enumerate(topics):
        tweet_text = write_tweet(topic)
        tweets.append({
            "topic": topic,
            "tweet": tweet_text,
            "status": "pending",
            "slot_index": i,
            "slot_label": SLOTS[i]["label"],
            "utc_hour": SLOTS[i]["utc_hour"],
            "utc_min": SLOTS[i]["utc_min"],
            "message_id": None
        })
        print(f"Tweet {i+1}: {tweet_text[:70]}...")
    tweets = send_telegram(tweets)
    save_to_repo(tweets)
    print("Done! Check Telegram.")

if __name__ == "__main__":
    main()
