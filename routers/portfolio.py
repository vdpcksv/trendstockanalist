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

def get_current_price(stock_name: str) -> float:
    try:
        ticker = resolve_ticker(stock_name)
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        df = fdr.DataReader(ticker, start=start_date)
        if not df.empty:
            return float(df.iloc[-1]['Close'])
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
        db.commit()
        db.refresh(existing_item)
        return existing_item
    else:
        db_item = models.Portfolio(
            ticker=item.ticker,
            target_price=item.target_price,
            qty=item.qty,
            user_id=current_user.id
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item

@router.get("/api/portfolio")
def get_portfolio_items(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    items = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    result = []
    for i in items:
        qty = i.qty if hasattr(i, 'qty') and i.qty is not None else 1
        current_price = get_current_price(i.ticker)
        result.append({
            "id": i.id, 
            "name": i.ticker, 
            "price": i.target_price or 0,
            "qty": qty,
            "current_price": current_price
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
