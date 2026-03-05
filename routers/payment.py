from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from dependencies import get_db, templates
from datetime import datetime, timedelta
import requests
import base64
import models
import auth

router = APIRouter(tags=["Payment (Monetization)"])

# Toss Payments Developer Test Keys
TOSS_SECRET_KEY = "test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R"

@router.get("/payment", response_class=HTMLResponse)
def get_payment_page(request: Request):
    """결제(구독) 페이지 렌더링"""
    return templates.TemplateResponse(request=request, name="payment.html", context={})

@router.get("/api/membership")
def get_membership(current_user: models.User = Depends(auth.get_current_user)):
    return {
        "username": current_user.username,
        "membership": current_user.membership or "basic",
        "expires_at": str(current_user.premium_expires_at) if current_user.premium_expires_at else None,
        "features": {
            "ai_analysis": True,
            "community": True,
            "alerts": current_user.membership == "premium",
            "unlimited_alerts": current_user.membership == "premium",
            "priority_support": current_user.membership == "premium",
        }
    }

@router.post("/api/payment/confirm")
async def payment_confirm(request: Request, db: Session = Depends(get_db)):
    """토스페이먼츠 연동 서버 승인 및 유저 등급 업그레이드"""
    try:
        body = await request.json()
        payment_key = body.get("paymentKey", "")
        order_id = body.get("orderId", "")
        amount = body.get("amount", 0)
        
        if not payment_key or not order_id or not amount:
            raise HTTPException(status_code=400, detail="필수 결제 정보가 누락되었습니다.")
            
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="인증되지 않은 요청입니다. 다시 로그인해주세요.")
            
        user = await auth.get_current_user(token.split(" ")[1], db)
        
        # 1. 토스 서버로 승인 권한 서버간 통신 전송
        toss_url = "https://api.tosspayments.com/v1/payments/confirm"
        credential = base64.b64encode(f"{TOSS_SECRET_KEY}:".encode('utf-8')).decode('utf-8')
        
        headers = {
            "Authorization": f"Basic {credential}",
            "Content-Type": "application/json"
        }
        data = {
            "paymentKey": payment_key,
            "orderId": order_id,
            "amount": amount
        }
        
        res = requests.post(toss_url, headers=headers, json=data)
        
        if res.status_code != 200:
            error_data = res.json()
            raise HTTPException(status_code=res.status_code, detail=f"토스페이먼츠 승인 실패: {error_data.get('message', '알 수 없는 오류')}")

        # 2. 결제 승인 성공 시 DB 업데이트 (PRO 권한 30일 부여)
        user.membership = "premium"
        if user.premium_expires_at and user.premium_expires_at > datetime.utcnow():
            user.premium_expires_at = user.premium_expires_at + timedelta(days=30)
        else:
            user.premium_expires_at = datetime.utcnow() + timedelta(days=30)
            
        db.commit()
        
        return {"status": "success", "message": "결제가 성공적으로 승인되었습니다. PRO 회원이 되신 것을 환영합니다!", "membership": "premium"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"결제 처리 중 서버 에러: {str(e)}")

@router.post("/api/membership/upgrade")
def upgrade_membership_mock(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Mock upgrade endpoint for testing/admin purposes"""
    current_user.membership = "premium"
    current_user.premium_expires_at = datetime.utcnow() + timedelta(days=30)
    db.commit()
    return {"status": "success", "message": "프리미엄 회원으로 업그레이드 조치되었습니다.", "membership": "premium"}

@router.post("/api/membership/downgrade")
def downgrade_membership(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    current_user.membership = "basic"
    db.commit()
    return {"status": "success", "message": "기본 회원으로 전환되었습니다.", "membership": "basic"}
