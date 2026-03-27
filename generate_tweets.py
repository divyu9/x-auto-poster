import os
import json
import base64
import feedparser
import requests
from datetime import datetime

# Slots for scheduling
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
    if not res.ok: return None, None
    data = res.json()
    return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]

def gh_put(filename, payload, sha, message):
    repo = os.environ["GITHUB_REPOSITORY"]
    encoded = base64.b64encode(json.dumps(payload, indent=2, ensure_ascii=False).encode()).decode()
    body = {"message": message, "content": encoded, "branch": "main"}
    if sha: body["sha"] = sha
    res = requests.put(f"https://api.github.com/repos/{repo}/contents/{filename}", json=body, headers=gh_headers())
    return res.ok

# --- Gemini API Helper ---
def ask_gemini(system_prompt, user_prompt, model="gemini-1.5-pro"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={os.environ['GEMINI_API_KEY']}"
    payload = {
        "contents": [{"parts": [{"text": f"SYSTEM: {system_prompt}\nUSER: {user_prompt}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
    }
    res = requests.post(url, json=payload)
    if not res.ok:
        print(f"Gemini Error: {res.text}")
        return ""
    return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()

def load_library():
    data, _ = gh_get("topics_library.json")
    return data.get("topics", []) if data else []

def fetch_news():
    feeds = [
        "https://news.google.com/rss/search?q=Jio+Airtel+telecom+India&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=tech+scam+India+consumer&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=smartphone+launch+India+price&hl=en-IN&gl=IN",
        "https://news.google.com/rss/search?q=Amazon+Flipkart+India+scam&hl=en-IN&gl=IN"
    ]
    headlines = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.title.split(" - ")[0].strip()
                if len(title) > 20: headlines.append(title)
        except: pass
    return list(set(headlines))[:40]

def pick_10_topics(headlines, library_topics):
    h_text = "\n".join([f"- {h}" for h in headlines])
    l_text = "\n".join([f"- {t['text']}" for t in library_topics])
    
    sys_msg = "You are a content strategist for Sarcastic Sindhi, a top Indian tech creator. Select the most viral/relevant topics."
    user_msg = f"Pick the 10 best topics from these news headlines and library topics:\n\nNEWS:\n{h_text}\n\nLIBRARY:\n{l_text}\n\nReturn ONLY a valid JSON array of strings: [\"topic1\", \"topic2\", ...]"
    
    raw = ask_gemini(sys_msg, user_msg, model="gemini-1.5-flash") # Flash is enough for selection
    try:
        # Clean JSON if Gemini adds markdown
        clean = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except:
        return headlines[:10]

def write_tweet(topic):
    sys_msg = """You are Sarcastic Sindhi (Chandan Bulani), a tech creator and consumer advocate.
    Write a brutally honest, sarcastic tweet in ENGLISH.
    - Style: Modern, sharp, pro-consumer.
    - Punchy hook, sharp verdict.
    - Use ₹ for money. 
    - 280 chars max. No hashtags."""
    
    user_msg = f"Write a sarcastic English tweet about this tech news: {topic}"
    tweet = ask_gemini(sys_msg, user_msg, model="gemini-1.5-pro")
    return tweet.strip('"').strip("'")[:280]

def send_to_telegram(all_tweets):
    token, chat_id = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    intro = f"🔴 *Sarcastic Sindhi — Daily Drafts*\n\n10 tweets ready in English. Approve 4 for the slots."
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": intro, "parse_mode": "Markdown"})

    for i, t in enumerate(all_tweets):
        res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"📱 *Option {i+1}*\n\n{t['tweet']}",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"approve_{i}"}, {"text": "❌ Skip", "callback_data": f"skip_{i}"}]]}
        })
        if res.ok: all_tweets[i]["message_id"] = res.json()["result"]["message_id"]
    return all_tweets

def main():
    headlines = fetch_news()
    library = load_library()
    topics = pick_10_topics(headlines, library)
    
    all_tweets = []
    for topic in topics:
        all_tweets.append({
            "topic": topic, "tweet": write_tweet(topic),
            "status": "pending", "slot_label": None, "message_id": None
        })

    all_tweets = send_to_telegram(all_tweets)
    
    payload = {"tweets": all_tweets, "slots": SLOTS, "date": datetime.now().strftime("%Y-%m-%d"), "approved_count": 0}
    _, sha = gh_get("pending_tweets.json")
    gh_put("pending_tweets.json", payload, sha, f"Daily tweets {payload['date']}")

if __name__ == "__main__":
    main()
