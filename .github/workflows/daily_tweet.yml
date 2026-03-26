name: Daily X Post — Sarcastic Sindhi

on:
  schedule:
    # 8:00 AM IST = 2:30 UTC — generate + send to Telegram
    - cron: '30 2 * * *'
    # Check every 15 min from 8 AM to 10 PM IST (2:30 UTC to 16:30 UTC)
    - cron: '*/15 3-16 * * *'
  workflow_dispatch:
    inputs:
      mode:
        description: 'generate or check'
        required: false
        default: 'generate'
        type: choice
        options:
          - generate
          - check

permissions:
  contents: write

jobs:
  run:
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
        run: pip install anthropic tweepy feedparser requests

      - name: Determine mode
        id: mode
        run: |
          HOUR=$(date -u +%H)
          MIN=$(date -u +%M)
          MANUAL="${{ inputs.mode }}"
          if [ -n "$MANUAL" ]; then
            echo "mode=$MANUAL" >> $GITHUB_OUTPUT
          elif [ "$HOUR" = "02" ] && [ "$MIN" -ge "25" ] && [ "$MIN" -le "45" ]; then
            echo "mode=generate" >> $GITHUB_OUTPUT
          else
            echo "mode=check" >> $GITHUB_OUTPUT
          fi

      - name: Generate tweets (8 AM IST)
        if: steps.mode.outputs.mode == 'generate'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python generate_tweets.py

      - name: Check approvals + post scheduled tweets
        if: steps.mode.outputs.mode == 'check'
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          X_CONSUMER_KEY: ${{ secrets.X_CONSUMER_KEY }}
          X_CONSUMER_SECRET: ${{ secrets.X_CONSUMER_SECRET }}
          X_ACCESS_TOKEN: ${{ secrets.X_ACCESS_TOKEN }}
          X_ACCESS_TOKEN_SECRET: ${{ secrets.X_ACCESS_TOKEN_SECRET }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python check_approvals.py
