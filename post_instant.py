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
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    )

def download_telegram_image(file_id):
    """Download image from Telegram using file_id"""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    # Get file path
    res = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}")
    if not res.ok:
        return None
    file_path = res.json()["result"]["file_path"]
    # Download file
    img_res = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
    if img_res.ok:
        return img_res.content
    return None

def post_to_x(tweet_text, image_data=None):
    # OAuth1 client for media upload
    auth = tweepy.OAuth1UserHandler(
        os.environ["X_CONSUMER_KEY"],
        os.environ["X_CONSUMER_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    api_v1 = tweepy.API(auth)

    media_ids = []
    if image_data:
        # Upload image to X
        import io
        media = api_v1.media_upload(filename="image.jpg", file=io.BytesIO(image_data))
        media_ids.append(str(media.media_id))
        print(f"Image uploaded to X, media_id: {media.media_id}")

    # Post tweet
    client = tweepy.Client(
        consumer_key=os.environ["X_CONSUMER_KEY"],
        consumer_secret=os.environ["X_CONSUMER_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    if media_ids:
        response = client.create_tweet(text=tweet_text, media_ids=media_ids)
    else:
        response = client.create_tweet(text=tweet_text)

    return response.data["id"]

def main():
    print(f"[{datetime.now().isoformat()}] Posting instant tweet...")
    data, sha = gh_get("instant_tweet.json")
    if not data:
        print("No instant_tweet.json found")
        return
    if data.get("status") not in ["pending", "posting"]:
        print(f"Status is {data.get('status')} — skipping")
        return

    tweet_text = data["tweet"]
    file_id    = data.get("telegram_file_id")
    print(f"Posting: {tweet_text[:80]}...")
    if file_id:
        print("Image attached — downloading from Telegram...")

    try:
        image_data = None
        if file_id:
            image_data = download_telegram_image(file_id)
            if image_data:
                print(f"Image downloaded: {len(image_data)} bytes")
            else:
                print("Image download failed — posting without image")

        tweet_id = post_to_x(tweet_text, image_data)
        data["status"]   = "posted"
        data["tweet_id"] = str(tweet_id)
        gh_put("instant_tweet.json", data, sha, "Instant tweet posted")

        img_note = " (with image)" if image_data else ""
        send_tg(
            f"🟢 Posted{img_note}!\n\n{tweet_text}\n\n"
            f"View: https://x.com/sarcasticsindhi/status/{tweet_id}"
        )
        print(f"Posted{img_note}! ID: {tweet_id}")
    except Exception as e:
        data["status"] = "failed"
        gh_put("instant_tweet.json", data, sha, "Instant tweet failed")
        send_tg(f"❌ Post failed: {str(e)[:150]}")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
