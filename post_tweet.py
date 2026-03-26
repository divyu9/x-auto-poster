import os
import anthropic
import tweepy
from datetime import datetime

TOPIC_BUCKETS = [
    "Jio or Airtel latest tariff change, data plan update, 5G rollout, or network policy in India",
    "BSNL revival, government telecom policy, TRAI ruling, or spectrum auction news in India",
    "Samsung Galaxy latest launch, price reveal, or a consumer gotcha hidden in their India pricing",
    "Apple India pricing, iPhone or MacBook value trap, ecosystem lock-in, or repair cost expose",
    "Indian e-commerce scam, fake reviews, dark pattern, misleading deal on Flipkart or Amazon India",
    "Budget smartphone or laptop launch in India — real value vs marketing claims",
    "Internet company move that hurts Indian consumers — Google, Meta, YouTube, WhatsApp policy change",
    "AI tool or tech trend relevant to Indian consumers — what it means for your money or privacy",
    "WiFi router, broadband plan, or home internet tip that most Indians don't know about",
    "Indian startup, fintech, or app doing something sketchy or genuinely impressive",
]

today_index = datetime.now().timetuple().tm_yday % len(TOPIC_BUCKETS)
todays_topic_focus = TOPIC_BUCKETS[today_index]

SYSTEM_PROMPT = """You are the social media voice of Sarcastic Sindhi — Chandan Bulani's X (Twitter) account.

Chandan is a consumer-advocate tech creator with 391K YouTube subscribers. His audience is Indian males 18-35 who want to know: "Save me from getting scammed" and "Help me spend smartly."

## Your job
Write ONE punchy X post (tweet) in Chandan's voice. Under 280 characters including hashtags.

## Voice rules (non-negotiable)
- Tone: Sarcastic, brutally honest, consumer advocate. Friend talking to friend.
- Language: Hinglish — natural Hindi-English mix.
- Angle: ALWAYS consumer POV. "They're doing this TO you" energy. Expose the business tactic.
- Hook: Start with the punch. First 5 words must grab.
- India-first: Use ₹ not $. Reference Jio, Airtel, Flipkart, Amazon India, TRAI.
- End with a sharp verdict or rhetorical question that makes them think.
- Every tweet must have a CONSUMER INSIGHT — not just news, but what it means for the aam aadmi's wallet.

## Output
Return ONLY the tweet text. Under 280 characters. 2-3 hashtags at end."""


def get_auto_tweet():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": f"Today's focus: {todays_topic_focus}\n\nSearch for the latest news (last 24-48 hours) on this. Find the most consumer-relevant development. Write one tweet in Chandan's Sarcastic Sindhi voice with a strong consumer POV — what does this mean for the aam Indian's pocket?"}],
    )
    tweet_text = ""
    for block in response.content:
        if block.type == "text":
            tweet_text = block.text.strip()
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."
    return tweet_text


def post_to_x(tweet_text):
    client = tweepy.Client(
        consumer_key=os.environ["X_CONSUMER_KEY"],
        consumer_secret=os.environ["X_CONSUMER_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    response = client.create_tweet(text=tweet_text)
    return response.data["id"]


def main():
    print(f"[{datetime.now().isoformat()}] Starting X auto-poster...")

    # Check if manual tweet was provided via workflow_dispatch input
    manual_tweet = os.environ.get("MANUAL_TWEET", "").strip()

    if manual_tweet:
        print(f"Manual tweet mode — using provided text:")
        tweet = manual_tweet
    else:
        print(f"Auto-generate mode — topic: {todays_topic_focus}")
        tweet = get_auto_tweet()

    print(f"\nTweet ({len(tweet)} chars):\n{tweet}\n")

    tweet_id = post_to_x(tweet)
    print(f"Posted! Tweet ID: {tweet_id}")
    print(f"View: https://x.com/thesarcasticsindhi/status/{tweet_id}")


if __name__ == "__main__":
    main()
