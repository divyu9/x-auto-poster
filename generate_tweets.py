import os
import re
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
    body = {"message": message, "content": encoded}
    if sha:
        body["sha"] = sha
    res = requests.put(
        f"https://api.github.com/repos/{repo}/contents/{filename}",
        json=body, headers=gh_headers()
    )
    return res.ok

def load_library():
    data, _ = gh_get("topics_library.json")
    if not data:
        return []
    return data.get("topics", [])

def fetch_news():
    feeds = [
        "https://news.google.com/rss/search?q=Jio+Airtel+BSNL+telecom+India&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=tech+scam+fraud+India+consumer&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=smartphone+laptop+gadget+India+price&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=TRAI+internet+policy+India&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Amazon+Flipkart+India+consumer+scam&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Apple+Samsung+India+price+launch&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=India+startup+fintech+app+consumer&hl=en-IN&gl=IN&ceid=IN:en",
    ]
    headlines = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.title.split(" - ")[0].strip()
                if len(title) > 20:
                    headlines.append(title)
        except Exception as e:
            print(f"Feed error: {e}")
    seen = set()
    unique = []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return unique[:30]

def pick_10_topics(headlines, library_topics):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    headlines_text = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])
    lib_section = ""
    if library_topics:
        lib_text = "\n".join([f"- {t['text']}" for t in library_topics])
        lib_section = f"\n\nCustom topics from my library (include if relevant):\n{lib_text}"

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": f"""Pick 10 best topics for Sarcastic Sindhi — Indian consumer-advocate tech creator (391K YouTube subs). Audience: Indian males 18-35. Focus on: scams, telecom, gadgets, consumer rights, India pricing.

News headlines:
{headlines_text}{lib_section}

Return ONLY a JSON array of exactly 10 topic strings, no markdown:
["topic1", "topic2", ..., "topic10"]"""}]
    )
    raw = res.content[0].text.strip().replace("```json","").replace("```","").strip()
    return json.loads(raw)

def write_tweet(topic):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    res = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=350,
        system="""Tu Sarcastic Sindhi ka X account hai — Chandan Bulani, consumer-advocate tech creator, 391K YouTube subscribers.

VOICE RULES — ye follow karna ZAROOR hai:
- 50% Hindi + 50% English — natural Hinglish jaise Chandan bolta hai
- Sarcastic aur brutally honest — "yaar ye toh scam hai" energy
- Consumer ka POV — "company tujhe bewakoof bana rahi hai" angle
- Pehle 5 words mein punch honi chahiye — seedha point pe aao
- ₹ use karo prices ke liye — dollar nahi
- Jio, Airtel, Flipkart, Amazon India, TRAI reference karo jahan fit ho
- End mein sharp verdict YA rhetorical question jo reader ko angry/aware kare
- Aam aadmi ki jeb pe kya asar padega — yeh ZAROOR batao
- Natural phrases: "yaar sun", "bhai seriously", "samajh lo", "bewakoof mat bano", "likh ke de sakta hu"

OUTPUT: SIRF tweet text. 280 chars se kam. 2-3 hashtags end mein. Quotes mat lagao.""",
        messages=[{"role": "user", "content": f"Is India tech news pe ek sarcastic consumer-POV Hinglish tweet likho: {topic}"}]
    )
    tweet = res.content[0].text.strip().strip('"').strip("'")
    return tweet[:280] if len(tweet) > 280 else tweet

def send_to_telegram(all_tweets):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # Intro message
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
        "chat_id": chat_id,
        "text": (
            f"🔴 *Sarcastic Sindhi — {datetime.now().strftime('%d %b %Y')}*\n\n"
            f"*10 tweets ready hain!*\n\n"
            f"4 approve karo — slots:\n"
            f"• 1st approved → 11 AM\n"
            f"• 2nd approved → 1 PM\n"
            f"• 3rd approved → 5 PM\n"
            f"• 4th approved → 9 PM\n\n"
            f"_5th onwards approve kiye toh skip ho jayenge_"
        ),
        "parse_mode": "Markdown"
    })

    for i, t in enumerate(all_tweets):
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id,
            "text": (
                f"📱 *Option {i+1}/10*\n\n"
                f"{t['tweet']}\n\n"
                f"`{len(t['tweet'])}/280 chars`"
            ),
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve_{i}"},
                {"text": "❌ Skip",    "callback_data": f"skip_{i}"}
            ]]}
        })
        if res.ok:
            all_tweets[i]["message_id"] = res.json()["result"]["message_id"]
            print(f"Sent option {i+1}/10")
    return all_tweets

def save_to_repo(all_tweets):
    payload = {
        "tweets": all_tweets,
        "slots": SLOTS,
        "generated_at": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "approved_count": 0
    }
    _, sha = gh_get("pending_tweets.json")
    ok = gh_put("pending_tweets.json", payload, sha, f"Daily tweets {datetime.now().strftime('%Y-%m-%d')}")
    print("Saved to repo" if ok else "Save FAILED")

def main():
    print(f"[{datetime.now().isoformat()}] Generating 10 tweets...")
    headlines = fetch_news()
    print(f"Fetched {len(headlines)} headlines (free RSS)")
    library = load_library()
    print(f"Library: {len(library)} custom topics")
    topics = pick_10_topics(headlines, library)
    print(f"10 topics selected")

    all_tweets = []
    for i, topic in enumerate(topics):
        tweet_text = write_tweet(topic)
        all_tweets.append({
            "topic": topic,
            "tweet": tweet_text,
            "status": "pending",
            "slot_index": None,
            "slot_label": None,
            "utc_hour": None,
            "utc_min": None,
            "message_id": None
        })
        print(f"[{i+1}/10] {tweet_text[:60]}...")

    all_tweets = send_to_telegram(all_tweets)
    save_to_repo(all_tweets)
    print("Done! Check Telegram — approve 4 topics.")

if __name__ == "__main__":
    main()
