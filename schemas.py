from pydantic import BaseModel
from typing import Optional

class PortfolioBase(BaseModel):
    ticker: str
    target_price: Optional[float] = None
    qty: Optional[int] = 1

class PortfolioCreate(PortfolioBase):
    pass

class Portfolio(PortfolioBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    username: str
    password: str

# --- Phase 2: Community Schemas ---
from datetime import datetime

class CommentBase(BaseModel):
    content: str
    ticker: str

class CommentCreate(CommentBase):
    pass

class CommentResponse(CommentBase):
    id: int
    user_id: int
    created_at: datetime
    # 작성자 이름을 보여주기 위해 추가
    username: Optional[str] = None

    class Config:
        from_attributes = True

class VoteBase(BaseModel):
    ticker: str
    vote_type: str # 'BULL' or 'BEAR'

class VoteCreate(VoteBase):
    pass

class VoteResponse(VoteBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Phase 3: Alert Schemas ---
class AlertBase(BaseModel):
    ticker: str
    target_price: float
    condition_type: str  # 'ABOVE' or 'BELOW'

class AlertCreate(AlertBase):
    pass

class AlertResponse(AlertBase):
    id: int
    user_id: int
    is_active: int
    created_at: datetime

    class Config:
        from_attributes = True
