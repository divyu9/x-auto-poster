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

def tg(method, **kwargs):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    return requests.post(
        f"https://api.telegram.org/bot{token}/{method}", json=kwargs
    )

def send_msg(text, chat_id=None):
    if not chat_id:
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
    tg("sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown",
       disable_web_page_preview=True)

def edit_msg(chat_id, msg_id, text):
    tg("editMessageText", chat_id=chat_id, message_id=msg_id,
       text=text, parse_mode="Markdown")

def answer_cb(cb_id, text):
    tg("answerCallbackQuery", callback_query_id=cb_id, text=text)

def get_updates(offset=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    params = {"timeout": 3, "allowed_updates": ["callback_query"]}
    if offset:
        params["offset"] = offset
    res = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates", params=params
    )
    return res.json().get("result", [])

def post_to_x(tweet_text):
    client = tweepy.Client(
        consumer_key=os.environ["X_CONSUMER_KEY"],
        consumer_secret=os.environ["X_CONSUMER_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return client.create_tweet(text=tweet_text).data["id"]

def is_slot_time(tweet):
    now = datetime.now(timezone.utc)
    slot_hour = tweet.get("utc_hour")
    slot_min  = tweet.get("utc_min", 30)
    if slot_hour is None:
        return False
    now_mins  = now.hour * 60 + now.minute
    slot_mins = slot_hour * 60 + slot_min
    return slot_mins <= now_mins <= slot_mins + 20

SLOTS = [
    {"label": "11 AM IST", "utc_hour": 5,  "utc_min": 30},
    {"label": "1 PM IST",  "utc_hour": 7,  "utc_min": 30},
    {"label": "5 PM IST",  "utc_hour": 11, "utc_min": 30},
    {"label": "9 PM IST",  "utc_hour": 15, "utc_min": 30},
]

def assign_slot(tweets, idx):
    """Assign next available slot to approved tweet"""
    approved_count = sum(
        1 for t in tweets
        if t["status"] in ["approved", "posted"] and t.get("slot_index") is not None
    )
    if approved_count >= len(SLOTS):
        return None  # No more slots
    slot = SLOTS[approved_count]
    tweets[idx]["slot_index"]  = approved_count
    tweets[idx]["slot_label"]  = slot["label"]
    tweets[idx]["utc_hour"]    = slot["utc_hour"]
    tweets[idx]["utc_min"]     = slot["utc_min"]
    return slot

def main():
    print(f"[{datetime.now().isoformat()}] Checking approvals...")

    payload, sha = gh_get("pending_tweets.json")
    if not payload:
        print("No pending_tweets.json")
        return

    tweets  = payload.get("tweets", [])
    changed = False
    last_id = None

    updates = get_updates()

    for update in updates:
        last_id = update["update_id"]

        if "callback_query" not in update:
            continue

        cb      = update["callback_query"]
        cb_data = cb.get("data", "")
        cb_id   = cb["id"]
        chat_id = cb["message"]["chat"]["id"]
        msg_id  = cb["message"]["message_id"]

        if "_" not in cb_data:
            continue

        action, idx_str = cb_data.split("_", 1)
        try:
            idx = int(idx_str)
        except ValueError:
            continue

        if idx >= len(tweets):
            answer_cb(cb_id, "Tweet not found!")
            continue

        tweet = tweets[idx]

        if tweet["status"] != "pending":
            answer_cb(cb_id, f"Already {tweet['status']}!")
            continue

        if action == "approve":
            slot = assign_slot(tweets, idx)
            if slot is None:
                answer_cb(cb_id, "4 tweets already approved! Pehle wale enough hain.")
                continue
            tweets[idx]["status"] = "approved"
            answer_cb(cb_id, f"✅ Approved! Posts at {slot['label']}")
            edit_msg(chat_id, msg_id,
                f"✅ *APPROVED — {slot['label']}*\n\n{tweet['tweet']}\n\n"
                f"_Auto-posts at {slot['label']}_")
            print(f"Tweet {idx} approved → {slot['label']}")
            changed = True

        elif action == "skip":
            tweets[idx]["status"] = "skipped"
            answer_cb(cb_id, "❌ Skipped")
            edit_msg(chat_id, msg_id,
                f"❌ *SKIPPED*\n\n_{tweet['tweet'][:120]}_")
            print(f"Tweet {idx} skipped")
            changed = True

    if last_id:
        get_updates(offset=last_id + 1)

    # ── POST APPROVED TWEETS AT SLOT TIME ─────────────────────────────────
    for i, tweet in enumerate(tweets):
        if tweet["status"] == "approved" and is_slot_time(tweet):
            print(f"Slot time! Posting tweet {i} → {tweet.get('slot_label')}")
            try:
                tweet_id = post_to_x(tweet["tweet"])
                tweets[i]["status"]   = "posted"
                tweets[i]["tweet_id"] = str(tweet_id)
                changed = True
                send_msg(
                    f"🟢 *Posted — {tweet.get('slot_label')}*\n\n"
                    f"{tweet['tweet']}\n\n"
                    f"[View on X](https://x.com/sarcasticsindhi/status/{tweet_id})"
                )
                print(f"Posted! ID: {tweet_id}")
            except Exception as e:
                print(f"Post error: {e}")
                send_msg(f"❌ Post failed ({tweet.get('slot_label')}): {str(e)[:100]}")

    if changed:
        payload["tweets"] = tweets
        gh_put("pending_tweets.json", payload, sha, "Update approvals")

        still  = sum(1 for t in tweets if t["status"] in ["pending", "approved"])
        posted = sum(1 for t in tweets if t["status"] == "posted")
        skip   = sum(1 for t in tweets if t["status"] == "skipped")

        if still == 0 and (posted + skip) == len(tweets):
            send_msg(
                f"📊 *Aaj ka batch complete!*\n\n"
                f"🟢 Posted: {posted}\n❌ Skipped: {skip}\n\n"
                f"_Kal subah 8 AM pe next batch!_ 🔁"
            )

if __name__ == "__main__":
    main()
