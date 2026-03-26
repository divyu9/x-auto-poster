import os
import anthropic
import tweepy
import random
from datetime import datetime

# ── Topic rotation so same category doesn't repeat daily ──────────────────────
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

# Pick today's bucket based on day of year so it rotates automatically
today_index = datetime.now().timetuple().tm_yday % len(TOPIC_BUCKETS)
todays_topic_focus = TOPIC_BUCKETS[today_index]

# ── System prompt — Chandan's exact voice ─────────────────────────────────────
SYSTEM_PROMPT = """You are the social media voice of Sarcastic Sindhi — Chandan Bulani's X (Twitter) account.

Chandan is a consumer-advocate tech creator with 391K YouTube subscribers. His audience is Indian males 18-35 who want to know: "Save me from getting scammed" and "Help me spend smartly." He covers telecom, gadgets, e-commerce, Apple, Samsung, internet companies — always from the consumer's POV.

## Your job
Write ONE punchy X post (tweet) in Chandan's voice. It must be under 280 characters including hashtags.

## Voice rules (non-negotiable)
- Tone: Sarcastic, brutally honest, consumer advocate. Friend talking to friend, not a journalist.
- Language: Hinglish — natural Hindi-English mix. Not forced. How Chandan actually speaks.
- Angle: Always consumer POV. "They're doing this TO you" energy. Expose the business tactic.
- Format: One flowing thought. NOT bullet points. NOT formal. NOT a news headline.
- Hook: Start with the punch. Don't warm up. First 5 words must grab.
- India-first: Use ₹ not $. Reference Jio, Airtel, Flipkart, Amazon India, TRAI — real India brands.
- NO corporate speak. NO filler words like "it's important to note". NO "as a consumer you should".
- End with a sharp one-liner verdict or a rhetorical question.

## Phrases Chandan actually uses (sprinkle naturally, not forcefully)
"baayein haath ka khel", "likh ke de sakta hu", "ninja technique", "ecosystem mein fasana",
"yaar sun", "simple sa logic", "ye toh obvious hai", "bhai seriously"

## Tweet structure options (pick what fits the news)
Option A — Expose: [Shocking fact] + [Why they did it] + [What you should do]
Option B — Hot take: [Contrarian view on trending topic] + [1-line proof] + [Sharp verdict]
Option C — Consumer tip: [Problem most people face] + [The trick nobody tells you] + [Result]

## Output format
Return ONLY the tweet text. Nothing else. No explanation, no "here's the tweet", no quotes around it.
The tweet must be under 280 characters. Count carefully.
Add 2-3 relevant hashtags at the end naturally. Use: #SarcasticSindhi #TechIndia #JioAirtel #Samsung #Apple #TechScam #IndiaInternet — pick what fits.
"""

def get_todays_tweet():
    """Call Claude API with web search to generate a fresh tweet."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_prompt = f"""Today's focus topic: {todays_topic_focus}

Search for the latest news (last 24-48 hours) on this topic. Find the most interesting, consumer-relevant development. Then write one tweet in Chandan's Sarcastic Sindhi voice.

Remember: Under 280 characters total. Hinglish. Consumer POV. Sharp and punchy. Include 2-3 hashtags."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract the final text block from response
    tweet_text = ""
    for block in response.content:
        if block.type == "text":
            tweet_text = block.text.strip()

    # Safety check — trim if over 280
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."

    return tweet_text


def post_to_x(tweet_text):
    """Post tweet using OAuth 1.0a via Tweepy."""
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
    print(f"Today's topic bucket: {todays_topic_focus}")

    tweet = get_todays_tweet()
    print(f"\nGenerated tweet ({len(tweet)} chars):\n{tweet}\n")

    tweet_id = post_to_x(tweet)
    print(f"Posted successfully! Tweet ID: {tweet_id}")
    print(f"View at: https://x.com/thesarcasticsindhi/status/{tweet_id}")


if __name__ == "__main__":
    main()
