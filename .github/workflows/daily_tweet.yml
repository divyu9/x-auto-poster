name: Daily X Post — Sarcastic Sindhi

on:
  schedule:
    - cron: '30 3 * * *'
  workflow_dispatch:
    inputs:
      tweet_text:
        description: 'Paste your chosen tweet here (leave empty for auto-generate)'
        required: false
        type: string

jobs:
  post-tweet:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install anthropic tweepy

      - name: Post tweet
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          X_CONSUMER_KEY: ${{ secrets.X_CONSUMER_KEY }}
          X_CONSUMER_SECRET: ${{ secrets.X_CONSUMER_SECRET }}
          X_ACCESS_TOKEN: ${{ secrets.X_ACCESS_TOKEN }}
          X_ACCESS_TOKEN_SECRET: ${{ secrets.X_ACCESS_TOKEN_SECRET }}
          MANUAL_TWEET: ${{ inputs.tweet_text }}
        run: python post_tweet.py
