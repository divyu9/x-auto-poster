import os
import json
import base64
import requests
import tweepy
from datetime import datetime

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

def send_tg(text):
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
              "disable_web_page_preview": True}
    )

def main():
    print(f"[{datetime.now().isoformat()}] Posting instant tweet...")
    data, sha = gh_get("instant_tweet.json")
    
    if not data or "tweet" not in data:
        print("Error: No tweet data found in JSON")
        return

    tweet_text = data["tweet"].strip() # Khali spaces hatao
    
    if not tweet_text:
        print("Error: Tweet text is empty. Skipping post.")
        send_tg("❌ Post cancelled: Tweet text was empty.")
        return

    print(f"Attempting to post: {tweet_text[:80]}...")

    client = tweepy.Client(
        consumer_key=os.environ["X_CONSUMER_KEY"],
        consumer_secret=os.environ["X_CONSUMER_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    try:
        # Twitter API v2 call
        response = client.create_tweet(text=tweet_text)
        tweet_id = response.data["id"]
        
        # Update GitHub status
        data["status"] = "posted"
        data["tweet_id"] = str(tweet_id)
        gh_put("instant_tweet.json", data, sha, "Instant tweet posted")
        
        send_tg(f"🟢 *Posted Successfully!*\n\n{tweet_text}\n\n[View on X](https://x.com/user/status/{tweet_id})")
        print(f"Posted! ID: {tweet_id}")

    except Exception as e:
        print(f"Twitter API Error: {e}")
        data["status"] = "failed"
        gh_put("instant_tweet.json", data, sha, "Instant tweet failed")
        send_tg(f"❌ X Post failed: {str(e)}")

if __name__ == "__main__":
    main()
