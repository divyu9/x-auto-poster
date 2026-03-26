import os
import re
import json
import base64
import requests
import tweepy
from datetime import datetime, timezone

# ── GITHUB HELPERS ────────────────────────────────────────────────────────────
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
    body = {"message": message, "content": encoded}
    if sha:
        body["sha"] = sha
    res = requests.put(f"https://api.github.com/repos/{repo}/contents/{filename}", json=body, headers=gh_headers())
    return res.ok

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def tg(method, **kwargs):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    return requests.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)

def send_msg(text, chat_id=None, buttons=None):
    if not chat_id:
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    tg("sendMessage", **payload)

def edit_msg(chat_id, msg_id, text):
    tg("editMessageText", chat_id=chat_id, message_id=msg_id, text=text, parse_mode="Markdown")

def answer_cb(cb_id, text):
    tg("answerCallbackQuery", callback_query_id=cb_id, text=text)

def get_updates(offset=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    params = {"timeout": 3, "allowed_updates": ["callback_query", "message"]}
    if offset:
        params["offset"] = offset
    res = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params=params)
    return res.json().get("result", [])

# ── X POSTING ────────────────────────────────────────────────────────────────
def post_to_x(tweet_text):
    client = tweepy.Client(
        consumer_key=os.environ["X_CONSUMER_KEY"],
        consumer_secret=os.environ["X_CONSUMER_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return client.create_tweet(text=tweet_text).data["id"]

# ── SLOT TIMING ───────────────────────────────────────────────────────────────
def is_slot_time(tweet):
    now = datetime.now(timezone.utc)
    slot_hour = tweet.get("utc_hour")
    slot_min  = tweet.get("utc_min", 30)
    if slot_hour is None:
        return False
    now_mins  = now.hour * 60 + now.minute
    slot_mins = slot_hour * 60 + slot_min
    return slot_mins <= now_mins <= slot_mins + 20

# ── URL → TWEET PIPELINE ──────────────────────────────────────────────────────
def is_url(text):
    return text.startswith("http://") or text.startswith("https://")

def fetch_article(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SarcasticSindhiBot/1.0)"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        html = res.text
        og_title  = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html, re.I)
        og_desc   = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', html, re.I)
        meta_desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.I)
        title = og_title.group(1) if og_title else ""
        desc  = (og_desc or meta_desc)
        desc  = desc.group(1) if desc else ""
        clean = re.sub(r'<[^>]+>', ' ', html)
        clean = re.sub(r'\s+', ' ', clean).strip()[:3000]
        return f"Title: {title}\nDescription: {desc}\nContent: {clean}"
    except Exception as e:
        print(f"Fetch error: {e}")
        return None

def url_to_tweet(article_text):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    res = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=350,
        system="""You are Sarcastic Sindhi's X voice — Chandan Bulani, consumer-advocate tech creator, 391K YouTube subs.

Rules:
- Hinglish (natural Hindi-English mix, how Chandan actually speaks)
- Sarcastic, brutally honest, consumer POV — "they're doing this TO you" energy
- First 5 words must grab. No warm-up.
- Use rupee symbol for prices. Reference Jio/Airtel/Flipkart/Amazon India/TRAI when relevant.
- End with sharp verdict OR rhetorical question
- MUST include what this means for aam aadmi wallet or life
- Under 280 characters including 2-3 hashtags
- Output ONLY the tweet. No quotes around it.""",
        messages=[{"role": "user", "content": f"Write a consumer-POV sarcastic Hinglish tweet from this news:\n\n{article_text[:2000]}\n\nFocus on consumer impact for Indians."}]
    )
    tweet = res.content[0].text.strip().replace('"', '')
    return tweet[:280] if len(tweet) > 280 else tweet

def handle_url(url, chat_id):
    send_msg("🔍 Article fetch ho raha hai...", chat_id)
    article = fetch_article(url)
    if not article:
        send_msg("❌ Article fetch nahi hua — check karo link sahi hai ya paywall toh nahi.", chat_id)
        return

    send_msg("✍️ Tweet likh raha hai...", chat_id)
    try:
        tweet = url_to_tweet(article)
    except Exception as e:
        send_msg(f"❌ Tweet generation failed: {str(e)[:100]}", chat_id)
        return

    # Save instant tweet to repo
    instant = {"url": url, "tweet": tweet, "status": "pending", "created": datetime.now().isoformat()}
    _, sha = gh_get("instant_tweet.json")
    gh_put("instant_tweet.json", instant, sha, "Instant tweet from URL")

    # Send to Telegram with approve button
    send_msg(
        f"📰 *URL se Tweet Ready!*\n\n"
        f"{tweet}\n\n"
        f"`{len(tweet)}/280 chars`\n\n"
        f"_Source: {url[:70]}_",
        chat_id,
        buttons=[[
            {"text": "✅ Post to X Now", "callback_data": "instant_approve"},
            {"text": "❌ Skip", "callback_data": "instant_skip"}
        ]]
    )

# ── LIBRARY COMMANDS ──────────────────────────────────────────────────────────
def handle_command(text, chat_id):
    parts = text.strip().split(None, 1)
    cmd   = parts[0].lower().lstrip("/")
    rest  = parts[1].strip() if len(parts) > 1 else ""

    topics, sha = gh_get("topics_library.json")
    if topics is None:
        topics = {"topics": []}
    topic_list = topics.get("topics", [])

    if cmd in ["topics", "library", "list"]:
        if not topic_list:
            send_msg("📚 *Topics Library khali hai!*\n\nAdd karo:\n`/add Jio 5G problems`", chat_id)
            return
        lines = [f"📚 *Topics Library ({len(topic_list)} topics)*\n"]
        for i, t in enumerate(topic_list, 1):
            lines.append(f"`{i}.` {t['text']}")
        lines.append("\n`/add <topic>` — nayi topic\n`/remove <n>` — topic hatao")
        send_msg("\n".join(lines), chat_id)

    elif cmd == "add":
        if not rest:
            send_msg("❌ Topic text daalo!\nExample: `/add TRAI OTT rules India`", chat_id)
            return
        topic_list.append({"text": rest, "added": datetime.now().strftime("%d %b %Y")})
        topics["topics"] = topic_list
        topics["updated"] = datetime.now().isoformat()
        if gh_put("topics_library.json", topics, sha, "Add topic"):
            send_msg(f"✅ *Added!*\n\n_{rest}_\n\nTotal: {len(topic_list)} topics", chat_id)
        else:
            send_msg("❌ Save failed — try again", chat_id)

    elif cmd in ["remove", "delete", "del"]:
        if not rest.isdigit():
            send_msg("❌ Number daalo!\nExample: `/remove 3`", chat_id)
            return
        idx = int(rest) - 1
        if idx < 0 or idx >= len(topic_list):
            send_msg(f"❌ Topic {rest} nahi mila. `/topics` se list dekho.", chat_id)
            return
        removed = topic_list.pop(idx)
        topics["topics"] = topic_list
        if gh_put("topics_library.json", topics, sha, "Remove topic"):
            send_msg(f"🗑 *Removed:* _{removed['text']}_\n\nTopics remaining: {len(topic_list)}", chat_id)
        else:
            send_msg("❌ Remove failed", chat_id)

    elif cmd == "status":
        payload, _ = gh_get("pending_tweets.json")
        if not payload:
            send_msg("📭 Aaj ke liye koi tweets pending nahi.", chat_id)
            return
        tweets = payload.get("tweets", [])
        icons = {"pending": "⏳", "approved": "✅", "posted": "🟢", "skipped": "❌"}
        lines = [f"📊 *Status — {payload.get('date', '')}*\n"]
        for i, t in enumerate(tweets, 1):
            icon = icons.get(t["status"], "❓")
            lines.append(f"{icon} Tweet {i} ({t.get('slot_label','')}) — {t['status'].upper()}")
        send_msg("\n".join(lines), chat_id)

    elif cmd == "help":
        send_msg(
            "🤖 *Sarcastic Sindhi Bot*\n\n"
            "📚 *Topics Library:*\n"
            "`/topics` — poori list dekho\n"
            "`/add <text>` — topic add karo\n"
            "`/remove <n>` — topic hatao\n\n"
            "📊 *Info:*\n"
            "`/status` — aaj ke tweets ka status\n"
            "`/help` — yeh message\n\n"
            "🔗 *URL se Tweet:*\n"
            "Koi bhi news link bhejo — bot tweet banake approval maangega!\n\n"
            "_Roz 8 AM pe 4 tweets Telegram pe aate hain_",
            chat_id
        )
    else:
        send_msg(f"❓ Command samajh nahi aaya. `/help` dekho.", chat_id)

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().isoformat()}] Checking updates...")

    payload, sha     = gh_get("pending_tweets.json")
    tweets           = payload.get("tweets", []) if payload else []
    changed          = False
    last_update_id   = None

    updates = get_updates()

    for update in updates:
        last_update_id = update["update_id"]

        # ── TEXT MESSAGES (commands + URLs) ───────────────────────────────
        if "message" in update:
            msg     = update["message"]
            text    = msg.get("text", "").strip()
            chat_id = str(msg["chat"]["id"])

            if not text:
                continue

            if is_url(text):
                handle_url(text, chat_id)
            elif text.startswith("/"):
                handle_command(text, chat_id)
            continue

        # ── CALLBACK BUTTONS ──────────────────────────────────────────────
        if "callback_query" not in update:
            continue

        cb      = update["callback_query"]
        cb_data = cb.get("data", "")
        cb_id   = cb["id"]
        chat_id = cb["message"]["chat"]["id"]
        msg_id  = cb["message"]["message_id"]

        # ── INSTANT TWEET (URL) APPROVAL ──────────────────────────────────
        if cb_data == "instant_approve":
            instant, inst_sha = gh_get("instant_tweet.json")
            if not instant:
                answer_cb(cb_id, "Tweet not found!")
                continue
            try:
                tweet_id = post_to_x(instant["tweet"])
                instant["status"] = "posted"
                gh_put("instant_tweet.json", instant, inst_sha, "Instant tweet posted")
                answer_cb(cb_id, "✅ Posted to X!")
                edit_msg(chat_id, msg_id,
                    f"✅ *POSTED!*\n\n{instant['tweet']}\n\n"
                    f"[View on X](https://x.com/sarcasticsindhi/status/{tweet_id})")
            except Exception as e:
                answer_cb(cb_id, f"Post failed: {str(e)[:60]}")
            continue

        if cb_data == "instant_skip":
            instant, inst_sha = gh_get("instant_tweet.json")
            if instant:
                instant["status"] = "skipped"
                gh_put("instant_tweet.json", instant, inst_sha, "Instant tweet skipped")
            answer_cb(cb_id, "❌ Skipped")
            edit_msg(chat_id, msg_id, f"❌ *SKIPPED*\n\n_{cb['message']['text'][:100]}_")
            continue

        # ── DAILY BATCH APPROVAL ──────────────────────────────────────────
        if "_" not in cb_data or not payload:
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
            tweets[idx]["status"] = "approved"
            answer_cb(cb_id, f"✅ Approved! Posts at {tweet.get('slot_label', 'scheduled time')}")
            edit_msg(chat_id, msg_id,
                f"✅ *APPROVED — {tweet.get('slot_label', '')}*\n\n{tweet['tweet']}\n\n_Auto-posts at scheduled time_")
            print(f"Approved tweet {idx} — {tweet.get('slot_label')}")
            changed = True

        elif action == "skip":
            tweets[idx]["status"] = "skipped"
            answer_cb(cb_id, "❌ Skipped")
            edit_msg(chat_id, msg_id, f"❌ *SKIPPED*\n\n_{tweet['tweet'][:120]}_")
            print(f"Skipped tweet {idx}")
            changed = True

    # Acknowledge all updates
    if last_update_id:
        get_updates(offset=last_update_id + 1)

    # ── POST APPROVED TWEETS AT SLOT TIME ─────────────────────────────────
    for i, tweet in enumerate(tweets):
        if tweet["status"] == "approved" and is_slot_time(tweet):
            print(f"Slot time! Posting tweet {i} — {tweet.get('slot_label')}")
            try:
                tweet_id = post_to_x(tweet["tweet"])
                tweets[i]["status"] = "posted"
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

    # ── SAVE + SUMMARY ────────────────────────────────────────────────────
    if changed and payload:
        payload["tweets"] = tweets
        gh_put("pending_tweets.json", payload, sha, "Update approval status")

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
