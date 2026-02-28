import os
import requests
import json
import logging
from datetime import datetime
import asyncio
from telegram import Bot

logger = logging.getLogger(__name__)

# --- Phase 3: KIS (Korea Investment & Securities) API ---
# In a real environment, you need valid AppKey and AppSecret.
# We will create a mock class that behaves like the real API but falls back gracefully.

class KisApiHandler:
    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY", "")
        self.app_secret = os.getenv("KIS_APP_SECRET", "")
        self.domain = "https://openapi.koreainvestment.com:9443"
        self.access_token = None
        self.token_expires_at = None

    def _get_access_token(self):
        """Mock token generation."""
        if not self.app_key or not self.app_secret:
            return False # Missing credentials
            
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return True
            
        try:
            # Here you would make a real POST request to /oauth2/tokenP
            # We skip the real HTTP call for the MVP fallback testing purpose
            self.access_token = "mock_kis_token_xyz"
            self.token_expires_at = datetime.now() # + timedelta(hours=23)
            return True
        except Exception as e:
            logger.error(f"KIS Token Error: {e}")
            return False

    def get_current_price(self, ticker: str):
        """
        Attempts to fetch live price from KIS API.
        If it fails (no keys, network error), it raises an Exception to trigger Fallback.
        """
        if not self._get_access_token():
            raise Exception("KIS API Config Missing or Token Failed. Fallback Required.")
            
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100" # 주식현재가시세
        }
        
        # Real URL: f"{self.domain}/uapi/domestic-stock/v1/quotations/inquire-price"
        # We simulate the failure to force the application to use the safe Fallback
        raise Exception("KIS API endpoint mocked for safety. Fallback to scraping/FDR.")


# --- Phase 3: Telegram Alert Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

async def send_telegram_message(message: str):
    """Asynchronous Telegram alert sender."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        # In MVP, quietly ignore if no token is set.
        print(f"[Telegram Mock] Not sending as token is missing: {message}")
        return False
        
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        return True
    except Exception as e:
        logger.error(f"Telegram Send Error: {e}")
        return False

def send_telegram_sync(message: str):
    """Synchronous wrapper for Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        # In MVP, quietly ignore if no token is set.
        try:
            print(f"[Telegram Mock] Not sending as token is missing: {message}")
        except UnicodeEncodeError:
            print("[Telegram Mock] Not sending as token is missing: (Message contains emojis)")
        return False
        
    # Standard request for sync context
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram Sync Error: {e}")
        return False
