# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import traceback as tb

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from database import engine
import models
import ai_module
import infra_module
from internal.cache import cache_data

# Import routers
from routers import auth, dashboard, analysis, portfolio, community, alerts, payment, system

# Helper imports for schedulers
from routers.dashboard import get_money_flow_data, get_theme_list
from routers.analysis import resolve_ticker
import FinanceDataReader as fdr
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("alphafinder")

models.Base.metadata.create_all(bind=engine)

def fetch_and_cache_data():
    try:
        logger.info("Fetching background data...")
        flow_data = get_money_flow_data()
        theme_data = get_theme_list()
        
        # Prefetch top stocks for each theme to prevent on-demand scraping
        theme_stocks = {}
        if not theme_data.empty:
            import time
            from routers.dashboard import get_theme_top_stocks
            for index, row in theme_data.iterrows():
                try:
                    theme_name = row['테마명']
                    theme_link = row['링크']
                    stocks_df = get_theme_top_stocks(theme_link)
                    if not stocks_df.empty:
                        theme_stocks[theme_name] = stocks_df.to_dict('records')
                    time.sleep(0.5) # Prevent aggressive scraping
                except Exception as loop_e:
                    logger.error(f"Error fetching top stocks for theme {theme_name}: {loop_e}")

        cache_data["money_flow"] = flow_data
        cache_data["theme_list"] = theme_data
        cache_data["theme_stocks"] = theme_stocks
        logger.info("Background data updated successfully.")
    except Exception as e:
        logger.error(f"Background fetch error: {e}")

def train_major_models():
    try:
        logger.info("Starting weekly Prophet model training...")
        major_tickers = ["005930", "006400", "068270", "105560", "005380"]
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(years=3)
        for ticker in major_tickers:
            df = fdr.DataReader(ticker, start_date, end_date)
            forecast = ai_module.train_prophet_model(ticker, df)
            if forecast:
                cache_data["prophet_models"][ticker] = forecast
        logger.info("Weekly model training completed.")
    except Exception as e:
        logger.error(f"Model training error: {e}")

def calculate_mock_returns():
    try:
        logger.info("Calculating daily mock investment returns...")
        from database import SessionLocal
        db = SessionLocal()
        users = db.query(models.User).all()
        for u in users:
            portfolios = db.query(models.Portfolio).filter(models.Portfolio.user_id == u.id).all()
            total_invested = 0
            total_current = 0
            for p in portfolios:
                buy_price = p.target_price or 0
                qty = p.qty or 1
                try:
                    df = fdr.DataReader(p.ticker, (datetime.now() - pd.DateOffset(days=7)).strftime('%Y-%m-%d'))
                    if not df.empty:
                        current = float(df['Close'].iloc[-1])
                        total_invested += buy_price * qty
                        total_current += current * qty
                except: pass
            if total_invested > 0:
                u.total_return = round(((total_current - total_invested) / total_invested) * 100, 2)
            else:
                u.total_return = 0.0
        db.commit()
        db.close()
        logger.info("Mock returns updated.")
    except Exception as e:
        logger.error(f"Mock return calculation error: {e}")

def process_alerts():
    try:
        from database import SessionLocal
        db = SessionLocal()
        alerts_list = db.query(models.Alert).filter(models.Alert.is_active == 1).all()
        for alert in alerts_list:
            try:
                df = fdr.DataReader(alert.ticker, (datetime.now() - pd.DateOffset(days=5)).strftime('%Y-%m-%d'))
                if not df.empty:
                    current_price = float(df['Close'].iloc[-1])
                    triggered = False
                    if alert.condition_type == 'ABOVE' and current_price >= alert.target_price:
                        triggered = True
                    elif alert.condition_type == 'BELOW' and current_price <= alert.target_price:
                        triggered = True
                    if triggered:
                        user = db.query(models.User).filter(models.User.id == alert.user_id).first()
                        if infra_module.send_telegram_alert(alert.ticker, current_price, alert.condition_type, alert.target_price):
                            alert.is_active = 0
                            alert.triggered_at = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error processing alert {alert.id}: {e}")
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Alert processing engine error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    FastAPICache.init(InMemoryBackend())
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_and_cache_data, 'interval', minutes=10)
    scheduler.add_job(train_major_models, 'cron', day_of_week='sun', hour=2)
    scheduler.add_job(calculate_mock_returns, 'cron', day_of_week='1-5', hour=16)
    scheduler.add_job(process_alerts, 'interval', minutes=5)
    scheduler.start()
    
    fetch_and_cache_data()
    
    yield
    scheduler.shutdown()

app = FastAPI(title="AlphaFinder", version="1.0.0", description="10x AI Trading Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}")
    logger.error(tb.format_exc())
    return HTMLResponse(
        content="<h1>500 Internal Server Error</h1><p>서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.</p>",
        status_code=500
    )

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start).total_seconds()
    if duration > 2.0:
        logger.warning(f"SLOW: {request.method} {request.url.path} took {duration:.2f}s")
    return response

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include all the domain routers
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(portfolio.router)
app.include_router(community.router)
app.include_router(alerts.router)
app.include_router(payment.router)
app.include_router(system.router)

if __name__ == "__main__":
    import uvicorn
    # Make sure to run the app with 'uvicorn main:app --reload' in production
    uvicorn.run(app, host="127.0.0.1", port=8000)
