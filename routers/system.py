from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import FinanceDataReader as fdr

from dependencies import get_db, templates
import models
import auth
from routers.analysis import resolve_ticker

router = APIRouter(tags=["System & SEO"])

@router.get("/policies", response_class=HTMLResponse)
async def read_policies(request: Request):
    return templates.TemplateResponse(request=request, name="policies.html", context={})

@router.get("/ads.txt", response_class=PlainTextResponse)
async def get_ads_txt():
    return "google.com, pub-9065075656013134, DIRECT, f08c47fec0942fa0"

@router.get("/sitemap.xml")
async def sitemap():
    base_url = "https://alphafinder.kr"
    today = datetime.now().strftime("%Y-%m-%d")
    
    pages = [
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        {"loc": "/seasonality", "priority": "0.8", "changefreq": "weekly"},
        {"loc": "/themes", "priority": "0.8", "changefreq": "daily"},
        {"loc": "/leaderboard", "priority": "0.7", "changefreq": "daily"},
        {"loc": "/review", "priority": "0.9", "changefreq": "daily"},
        {"loc": "/policies", "priority": "0.3", "changefreq": "monthly"},
    ]
    
    xml_items = ""
    for p in pages:
        xml_items += f"""  <url>
    <loc>{base_url}{p['loc']}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{p['changefreq']}</changefreq>
    <priority>{p['priority']}</priority>
  </url>\n"""
    
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_items}</urlset>"""
    return Response(content=sitemap_xml, media_type="application/xml")

@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return """User-agent: *
Allow: /
Disallow: /api/
Disallow: /portfolio
Sitemap: https://alphafinder.kr/sitemap.xml
"""

@router.get("/api/og-image/{ticker}")
async def generate_og_image(ticker: str, db: Session = Depends(get_db)):
    resolved_ticker = resolve_ticker(ticker)
    try:
        df = fdr.DataReader(resolved_ticker, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        if not df.empty:
            current_price = float(df['Close'].iloc[-1])
            price_30d_ago = float(df['Close'].iloc[0])
            change_pct = round((current_price - price_30d_ago) / price_30d_ago * 100, 2)
            if change_pct > 0: trend = "상승"
            elif change_pct < 0: trend = "하락"
            else: trend = "보합"
        else:
            current_price = 0
            change_pct = 0
            trend = "N/A"
    except:
        current_price = 0
        change_pct = 0
        trend = "N/A"
    
    bull = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BULL').count()
    bear = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BEAR').count()
    total = bull + bear
    sentiment = f"BULL {round(bull/total*100)}%" if total > 0 else "투표 없음"
    
    return {
        "title": f"AlphaFinder | {resolved_ticker} 종목 AI 분석",
        "description": f"{trend} {change_pct:+.2f}% (30일) | 현재가 {current_price:,.0f}원 | 투자자 심리: {sentiment}",
        "image_text": f"{resolved_ticker} | {current_price:,.0f}원 | {change_pct:+.2f}%",
        "ticker": resolved_ticker,
        "current_price": current_price,
        "change_pct": change_pct,
        "sentiment": sentiment
    }

@router.get("/api/pnl-card")
def generate_pnl_card(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    portfolios = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    holdings = []
    total_pnl = 0.0
    for p in portfolios:
        try:
            df = fdr.DataReader(p.ticker, (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
            if not df.empty and p.target_price and p.target_price > 0:
                current = float(df['Close'].iloc[-1])
                pnl_pct = round((current - p.target_price) / p.target_price * 100, 2)
                pnl_value = round((current - p.target_price) * p.qty, 0)
                total_pnl += pnl_value
                holdings.append({
                    "ticker": p.ticker, "buy_price": p.target_price, "current_price": current,
                    "qty": p.qty, "pnl_pct": pnl_pct, "pnl_value": pnl_value
                })
        except:
            pass
    rank_data = db.query(models.User.username, models.User.total_return).filter(models.User.total_return.isnot(None)).order_by(models.User.total_return.desc()).all()
    user_rank = "N/A"
    for i, r in enumerate(rank_data):
        if r.username == current_user.username:
            user_rank = f"{i + 1}/{len(rank_data)}"
            break
            
    return {
        "username": current_user.username,
        "total_return": current_user.total_return or 0.0,
        "rank": user_rank,
        "holdings": holdings,
        "total_pnl_value": total_pnl,
        "generated_at": datetime.now().isoformat(),
        "watermark": "AlphaFinder | alphafinder.kr"
    }
