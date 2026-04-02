import os
import json
import base64
import requests
import tweepy
from datetime import datetime, timezone

def gh_headers():
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SarcasticSindhiBot/1.0"
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

def post_to_x(tweet_text):
    client = tweepy.Client(
        consumer_key=os.environ["X_CONSUMER_KEY"],
        consumer_secret=os.environ["X_CONSUMER_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return client.create_tweet(text=tweet_text).data["id"]

def is_time_to_post(tweet):
    """Check if current UTC time has passed the scheduled time"""
    utc_hour = tweet.get("utc_hour")
    utc_min  = tweet.get("utc_min", 0)
    if utc_hour is None:
        return False
    now = datetime.now(timezone.utc)
    now_mins  = now.hour * 60 + now.minute
    slot_mins = utc_hour * 60 + utc_min
    # Post if within 20-min window past scheduled time
    return slot_mins <= now_mins <= slot_mins + 20

def main():
    print(f"[{datetime.now().isoformat()}] Checking scheduled tweets...")

    payload, sha = gh_get("pending_tweets.json")
    if not payload:
        print("No pending_tweets.json found")
        return

    tweets  = payload.get("tweets", [])
    changed = False

    for i, tweet in enumerate(tweets):
        if tweet["status"] == "approved" and is_time_to_post(tweet):
            print(f"Time to post tweet {i} — scheduled at {tweet.get('slot_label')}")
            try:
                tweet_id = post_to_x(tweet["tweet"])
                tweets[i]["status"]   = "posted"
                tweets[i]["tweet_id"] = str(tweet_id)
                changed = True
                send_tg(
                    f"🟢 *Posted — {tweet.get('slot_label')}*\n\n"
                    f"{tweet['tweet']}\n\n"
                    f"[View on X](https://x.com/sarcasticsindhi/status/{tweet_id})"
                )
                print(f"Posted! ID: {tweet_id}")
            except Exception as e:
                print(f"Post error: {e}")
                send_tg(f"❌ Post failed ({tweet.get('slot_label')}): {str(e)[:100]}")

    if changed:
        payload["tweets"] = tweets
        gh_put("pending_tweets.json", payload, sha, "Update scheduled posts")

    print("Done.")

if __name__ == "__main__":
    main()
