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
        # 바탕화면의 한투 key.txt 파일 읽기
        key_file_path = r"c:\Users\vdpck\OneDrive\Desktop\한투 key.txt"
        self.app_key = os.getenv("KIS_APP_KEY", "")
        self.app_secret = os.getenv("KIS_APP_SECRET", "")
        
        if os.path.exists(key_file_path):
            try:
                with open(key_file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines:
                        if "APP KEY :" in line:
                            self.app_key = line.split("APP KEY :")[1].strip()
                        elif "APP Secret :" in line:
                            self.app_secret = line.split("APP Secret :")[1].strip()
            except Exception as e:
                logger.error(f"Failed to read KIS key file: {e}")

        self.domain = "https://openapi.koreainvestment.com:9443"
        self.access_token = None
        self.token_expires_at = None
        self.last_api_call_time = 0.0

    async def _rate_limit(self):
        """초당 20건 제한을 피하기 위해 호출 간 지연을 보장합니다."""
        import time
        now = time.time()
        time_since_last_call = now - self.last_api_call_time
        if time_since_last_call < 0.1:  # 최소 0.1초 간격 (초당 최대 10건)
            await asyncio.sleep(0.1 - time_since_last_call)
        self.last_api_call_time = time.time()

    def _get_access_token(self):
        """실제 KIS OAuth 토큰 발급 및 캐싱"""
        if not self.app_key or not self.app_secret:
            logger.error("KIS API keys are missing.")
            return False
            
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return True
            
        try:
            url = f"{self.domain}/oauth2/tokenP"
            headers = {"content-type": "application/json"}
            body = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }
            res = requests.post(url, headers=headers, json=body, timeout=5)
            res.raise_for_status()
            data = res.json()
            
            self.access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 86400))
            from datetime import timedelta
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300) # 만료 5분 전까지
            return True
        except Exception as e:
            logger.error(f"KIS Token Error: {e}")
            return False

    async def get_current_price(self, ticker: str):
        """
        초당 제한을 지키며 비동기 방식으로 실제 KIS API에서 현재가를 가져옵니다.
        """
        if not self._get_access_token():
            raise Exception("KIS API Config Missing or Token Failed.")
            
        await self._rate_limit()
            
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100" # 주식현재가시세
        }
        
        url = f"{self.domain}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker
        }
        
        try:
            # 비동기 내에서 동기 requests 호출하므로 to_thread 권장
            def fetch():
                res = requests.get(url, headers=headers, params=params, timeout=5)
                res.raise_for_status()
                return res.json()
                
            data = await asyncio.to_thread(fetch)
            if data["rt_cd"] == "0":
                return float(data["output"]["stck_prpr"])
            else:
                raise Exception(f"KIS API Error: {data['msg1']}")
        except Exception as e:
            logger.error(f"Failed to fetch price for {ticker}: {e}")
            raise

    async def get_orderbook(self, ticker: str):
        """
        KIS API 실시간 호가잔량 (5단계) 통신 함수
        """
        if not self._get_access_token():
            raise Exception("KIS API Config Missing or Token Failed.")
            
        await self._rate_limit()
            
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200" # 주식호가예상체결
        }
        
        url = f"{self.domain}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker
        }
        
        try:
            def fetch():
                res = requests.get(url, headers=headers, params=params, timeout=5)
                res.raise_for_status()
                return res.json()
                
            data = await asyncio.to_thread(fetch)
            if data["rt_cd"] == "0":
                output1 = data["output1"] # 호가 data
                
                # Parse 5 levels of Ask/Bid
                asks = []
                bids = []
                for i in range(1, 6):
                    ask_price = output1.get(f"askp{i}", "0")
                    ask_qty = output1.get(f"askp_rsqn{i}", "0")
                    bid_price = output1.get(f"bidp{i}", "0")
                    bid_qty = output1.get(f"bidp_rsqn{i}", "0")
                    
                    if ask_price != "0":
                        asks.append({"price": float(ask_price), "qty": int(ask_qty)})
                    if bid_price != "0":
                        bids.append({"price": float(bid_price), "qty": int(bid_qty)})
                
                return {
                    "asks": asks,
                    "bids": bids,
                    "total_ask_qty": int(output1.get("total_askp_rsqn", "0")),
                    "total_bid_qty": int(output1.get("total_bidp_rsqn", "0"))
                }
            else:
                raise Exception(f"KIS API Error: {data['msg1']}")
        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {ticker}: {e}")
            raise


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
