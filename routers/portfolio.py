from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import FinanceDataReader as fdr
from datetime import datetime, timedelta

from dependencies import get_db, templates
import models
import schemas
import auth
from routers.analysis import resolve_ticker # Helper for resolving ticker

router = APIRouter(tags=["Portfolio"])

@router.get("/portfolio", response_class=HTMLResponse)
async def read_portfolio(request: Request):
    context = {"error": None}
    return templates.TemplateResponse(request=request, name="portfolio.html", context=context)

from infra_module import KisApiHandler
import asyncio

kis_api = KisApiHandler()

async def get_current_price(stock_name: str) -> float:
    try:
        ticker = resolve_ticker(stock_name)
        # Try KIS API first
        try:
            price = await kis_api.get_current_price(ticker)
            return price
        except Exception as api_err:
            print(f"KIS API Fallback trigger for {stock_name}: {api_err}")
            # Fallback to FDR
            def fetch_fdr():
                start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                df = fdr.DataReader(ticker, start=start_date)
                if not df.empty:
                    return float(df.iloc[-1]['Close'])
                return 0.0
            price = await asyncio.to_thread(fetch_fdr)
            return price
    except Exception as e:
        print(f"Error fetching current price for {stock_name}: {e}")
    return 0.0

@router.post("/api/portfolio", response_model=schemas.Portfolio)
def add_portfolio_item(item: schemas.PortfolioCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    existing_item = db.query(models.Portfolio).filter(
        models.Portfolio.user_id == current_user.id,
        models.Portfolio.ticker == item.ticker
    ).first()

    if existing_item:
        old_qty = existing_item.qty or 1
        old_price = existing_item.target_price or 0.0
        new_qty = item.qty or 1
        new_price = item.target_price or 0.0
        total_old_value = old_qty * old_price
        total_new_value = new_qty * new_price
        combined_qty = old_qty + new_qty
        avg_price = (total_old_value + total_new_value) / combined_qty

        existing_item.qty = combined_qty
        existing_item.target_price = avg_price
        if item.memo:
            existing_item.memo = item.memo
        db.commit()
        db.refresh(existing_item)
        return existing_item
    else:
        db_item = models.Portfolio(
            ticker=item.ticker,
            target_price=item.target_price,
            qty=item.qty,
            memo=item.memo,
            user_id=current_user.id
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item

@router.get("/api/portfolio")
async def get_portfolio_items(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    items = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    result = []
    
    # Run price fetches concurrently for speed
    tasks = []
    for i in items:
        tasks.append(get_current_price(i.ticker))
        
    prices = await asyncio.gather(*tasks) if items else []
    
    for idx, i in enumerate(items):
        qty = i.qty if hasattr(i, 'qty') and i.qty is not None else 1
        current_price = prices[idx] if idx < len(prices) else 0.0
        result.append({
            "id": i.id, 
            "name": i.ticker, 
            "price": i.target_price or 0,
            "qty": qty,
            "current_price": current_price,
            "memo": i.memo or ""
        })
    return result

@router.delete("/api/portfolio/{item_id}")
def delete_portfolio_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    item = db.query(models.Portfolio).filter(models.Portfolio.id == item_id, models.Portfolio.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="해당 항목을 찾을 수 없습니다.")

@router.put("/api/portfolio/{item_id}")
def update_portfolio_item(item_id: int, item: schemas.PortfolioCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    db_item = db.query(models.Portfolio).filter(models.Portfolio.id == item_id, models.Portfolio.user_id == current_user.id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="해당 항목을 찾을 수 없습니다.")
    
    db_item.target_price = item.target_price
    db_item.qty = item.qty
    db_item.memo = item.memo
    db.commit()
    db.refresh(db_item)
    return db_item

# --- Watchlist API ---
@router.post("/api/watchlist", response_model=schemas.WatchlistResponse)
def add_watchlist_item(item: schemas.WatchlistCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    existing_item = db.query(models.Watchlist).filter(
        models.Watchlist.user_id == current_user.id,
        models.Watchlist.name == item.name,
        models.Watchlist.ticker == item.ticker
    ).first()
    
    if existing_item:
        return existing_item
        
    db_item = models.Watchlist(
        name=item.name,
        ticker=item.ticker,
        user_id=current_user.id
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.get("/api/watchlist")
def get_watchlist_items(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    items = db.query(models.Watchlist).filter(models.Watchlist.user_id == current_user.id).all()
    # Return directly, let frontend group by name
    return items

@router.delete("/api/watchlist/{item_id}")
def delete_watchlist_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    item = db.query(models.Watchlist).filter(models.Watchlist.id == item_id, models.Watchlist.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="해당 항목을 찾을 수 없습니다.")
