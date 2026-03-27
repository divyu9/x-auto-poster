import os
import json
import base64
import feedparser
import requests
import time
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
    res = requests.get(f"https://api.github.com/repos/{repo}/contents/{filename}", headers=gh_headers())
    if not res.ok:
        return None, None
    data = res.json()
    return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]

def gh_put(filename, payload, sha, message):
    repo = os.environ["GITHUB_REPOSITORY"]
    encoded = base64.b64encode(json.dumps(payload, indent=2, ensure_ascii=False).encode()).decode()
    body = {"message": message, "content": encoded, "branch": "main"}
    if sha:
        body["sha"] = sha
    res = requests.put(f"https://api.github.com/repos/{repo}/contents/{filename}", json=body, headers=gh_headers())
    return res.ok

def ask_gemini(system_prompt, user_prompt, model="gemini-2.5-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={os.environ['GEMINI_API_KEY']}"
    payload = {
        "contents": [{"parts": [{"text": f"SYSTEM: {system_prompt}\nUSER: {user_prompt}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
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

    sys_msg = "You are a content strategist for Sarcastic Sindhi, a top Indian consumer-advocate tech creator. Select the most viral and consumer-relevant topics."
    user_msg = (
        f"Pick the 10 best topics from these news headlines and library topics.\n\n"
        f"NEWS:\n{h_text}\n\nLIBRARY TOPICS:\n{l_text}\n\n"
        f"Return ONLY a valid JSON array of 10 strings, no markdown, no explanation:\n"
        f'["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7", "topic8", "topic9", "topic10"]'
    )

    raw = ask_gemini(sys_msg, user_msg, model="gemini-2.5-flash")
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        start = clean.index("[")
        end = clean.rindex("]") + 1
        return json.loads(clean[start:end])
    except:
        print(f"Topic parse failed, using headlines directly")
        return headlines[:10]

def write_tweet(topic):
    sys_msg = """Tu Sarcastic Sindhi hai — Chandan Bulani, consumer-advocate tech creator, 391K YouTube subscribers.

TWEET FORMAT — exactly yeh structure follow karo:
Line 1: News ka seedha fact — kya hua, exact number ya detail ke saath (real info)
Line 2: Teri ek genuine consumer POV line — aam aadmi ko isse kya fark padega

RULES:
- 220-270 characters USE KARO — short mat rehna
- Complete sentences — koi bhi line incomplete nahi
- Fact-first — pehle actual news, phir opinion
- Tone: curious + sarcastic, NOT angry or blaming
- 50% Hindi + 50% English — natural Hinglish
- Rupee symbol use karo
- 2 relevant hashtags end mein

EXAMPLE FORMAT:
"Jio ne 5G users ke liye ₹299 wala plan band kar diya, ab sirf ₹399+ wale plans available hain. Matlab speed toh dete hain, lekin saste mein nahi — upgrade karo ya suffer karo. #Jio #Telecom"

OUTPUT: SIRF tweet text. No quotes."""

    user_msg = f"Is India tech news pe ek sarcastic consumer-POV Hinglish tweet likho: {topic}"
    tweet = ask_gemini(sys_msg, user_msg, model="gemini-2.5-flash")
    tweet = tweet.strip().strip('"').strip("'")
    return tweet[:280] if len(tweet) > 280 else tweet

def send_to_telegram(all_tweets):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    intro = (
        f"Sarcastic Sindhi — {datetime.now().strftime('%d %b %Y')}\n\n"
        f"10 tweets ready! 4 approve karo:\n"
        f"1st approved → 11 AM\n"
        f"2nd approved → 1 PM\n"
        f"3rd approved → 5 PM\n"
        f"4th approved → 9 PM"
    )
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  json={"chat_id": chat_id, "text": intro})

    for i, t in enumerate(all_tweets):
        tweet_text = t["tweet"]
        if not tweet_text:
            tweet_text = "[Tweet generation failed for this topic]"

        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Option {i+1}/10\n\n{tweet_text}\n\n{len(tweet_text)}/280 chars",
            "reply_markup": {"inline_keyboard": [[
                {"text": "Approve", "callback_data": f"approve_{i}"},
                {"text": "Skip",    "callback_data": f"skip_{i}"}
            ]]}
        })
        if res.ok:
            all_tweets[i]["message_id"] = res.json()["result"]["message_id"]
        else:
            print(f"Telegram send error for tweet {i}: {res.text}")

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
        print(f"Writing tweet {i+1}/10: {topic[:50]}...")
        tweet = write_tweet(topic)
        print(f"  → {tweet[:60]}...")
        time.sleep(10)
        all_tweets.append({
            "topic": topic,
            "tweet": tweet,
            "status": "pending",
            "slot_index": None,
            "slot_label": None,
            "utc_hour": None,
            "utc_min": None,
            "message_id": None
        })

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
