from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from dependencies import get_db
import models
import auth

router = APIRouter(tags=["Payment (Monetization)"])

@router.get("/api/membership")
def get_membership(current_user: models.User = Depends(auth.get_current_user)):
    return {
        "username": current_user.username,
        "membership": current_user.membership or "basic",
        "features": {
            "ai_analysis": True,
            "community": True,
            "alerts": current_user.membership == "premium",
            "unlimited_alerts": current_user.membership == "premium",
            "priority_support": current_user.membership == "premium",
        }
    }

@router.post("/api/membership/upgrade")
def upgrade_membership(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    current_user.membership = "premium"
    db.commit()
    return {"status": "success", "message": "프리미엄 회원으로 업그레이드되었습니다!", "membership": "premium"}

@router.post("/api/payment/confirm")
async def payment_confirm(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        payment_key = body.get("paymentKey", "")
        order_id = body.get("orderId", "")
        amount = body.get("amount", 0)
        
        if not payment_key or not order_id or not amount:
            raise HTTPException(status_code=400, detail="필수 결제 정보(paymentKey, orderId, amount)가 누락되었습니다.")
        
        print(f"[Payment] Received: key={payment_key}, order={order_id}, amount={amount}")
        return {"status": "success", "message": "결제 확인이 완료되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"결제 처리 중 오류: {str(e)}")

@router.post("/api/membership/downgrade")
def downgrade_membership(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    current_user.membership = "basic"
    db.commit()
    return {"status": "success", "message": "기본 회원으로 전환되었습니다.", "membership": "basic"}
