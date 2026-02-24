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
