from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from dependencies import get_db
import models
import schemas
import auth
from routers.analysis import resolve_ticker

router = APIRouter(tags=["Alerts"])

@router.post("/api/alerts", response_model=schemas.AlertResponse)
def create_alert(alert: schemas.AlertCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    if alert.condition_type not in ('ABOVE', 'BELOW'):
        raise HTTPException(status_code=400, detail="조건 유형은 'ABOVE' 또는 'BELOW'만 가능합니다.")
    
    active_count = db.query(models.Alert).filter(
        models.Alert.user_id == current_user.id,
        models.Alert.is_active == 1
    ).count()
    if active_count >= 10:
        raise HTTPException(status_code=400, detail="활성 알림은 최대 10개까지 설정할 수 있습니다.")
    
    resolved_ticker = resolve_ticker(alert.ticker)
    
    db_alert = models.Alert(
        user_id=current_user.id,
        ticker=resolved_ticker,
        target_price=alert.target_price,
        condition_type=alert.condition_type,
        is_active=1
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@router.get("/api/alerts")
def get_my_alerts(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    alerts = db.query(models.Alert).filter(
        models.Alert.user_id == current_user.id
    ).order_by(models.Alert.created_at.desc()).all()
    
    return [{
        "id": a.id,
        "ticker": a.ticker,
        "target_price": a.target_price,
        "condition_type": a.condition_type,
        "is_active": a.is_active,
        "created_at": str(a.created_at)
    } for a in alerts]

@router.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    alert = db.query(models.Alert).filter(
        models.Alert.id == alert_id,
        models.Alert.user_id == current_user.id
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    
    db.delete(alert)
    db.commit()
    return {"status": "success", "message": "알림이 삭제되었습니다."}
