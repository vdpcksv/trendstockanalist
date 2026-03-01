from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from dependencies import get_db, templates
import models
import schemas
import auth
from routers.analysis import resolve_ticker

router = APIRouter(tags=["Community"])

@router.get("/leaderboard", response_class=HTMLResponse)
async def read_leaderboard(request: Request):
    return templates.TemplateResponse(request=request, name="leaderboard.html")

@router.post("/api/comments/{ticker}", response_model=schemas.CommentResponse)
def create_comment(ticker: str, comment: schemas.CommentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    resolved_ticker = resolve_ticker(ticker)
    db_comment = models.Comment(
        user_id=current_user.id,
        ticker=resolved_ticker,
        content=comment.content
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    
    return schemas.CommentResponse(
        id=db_comment.id,
        content=db_comment.content,
        ticker=db_comment.ticker,
        user_id=db_comment.user_id,
        created_at=db_comment.created_at,
        username=current_user.username
    )

@router.get("/api/comments/{ticker}")
def get_comments(ticker: str, db: Session = Depends(get_db)):
    resolved_ticker = resolve_ticker(ticker)
    comments = db.query(models.Comment, models.User.username)\
        .join(models.User, models.Comment.user_id == models.User.id)\
        .filter(models.Comment.ticker == resolved_ticker)\
        .order_by(models.Comment.created_at.desc())\
        .limit(50).all()
        
    result = []
    for c, uname in comments:
        result.append({
            "id": c.id,
            "content": c.content,
            "ticker": c.ticker,
            "user_id": c.user_id,
            "created_at": c.created_at.isoformat(),
            "username": uname
        })
    return result

@router.post("/api/votes/{ticker}")
def cast_vote(ticker: str, vote: schemas.VoteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    resolved_ticker = resolve_ticker(ticker)
    existing_vote = db.query(models.Vote).filter(
        models.Vote.user_id == current_user.id,
        models.Vote.ticker == resolved_ticker
    ).first()
    
    if existing_vote:
        existing_vote.vote_type = vote.vote_type
    else:
        new_vote = models.Vote(
            user_id=current_user.id,
            ticker=resolved_ticker,
            vote_type=vote.vote_type
        )
        db.add(new_vote)
        
    db.commit()
    return {"status": "success"}

@router.get("/api/votes/{ticker}")
def get_votes(ticker: str, db: Session = Depends(get_db)):
    resolved_ticker = resolve_ticker(ticker)
    bull_count = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BULL').count()
    bear_count = db.query(models.Vote).filter(models.Vote.ticker == resolved_ticker, models.Vote.vote_type == 'BEAR').count()
    total = bull_count + bear_count
    
    return {
        "bull": bull_count,
        "bear": bear_count,
        "total": total,
        "bull_ratio": round(bull_count / total * 100) if total > 0 else 0,
        "bear_ratio": round(bear_count / total * 100) if total > 0 else 0
    }

@router.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db), limit: int = 10):
    top_users = db.query(models.User.username, models.User.total_return)\
        .filter(models.User.total_return.isnot(None))\
        .order_by(models.User.total_return.desc())\
        .limit(limit).all()
        
    return [{"rank": i+1, "username": u.username, "return": u.total_return} for i, u in enumerate(top_users)]
