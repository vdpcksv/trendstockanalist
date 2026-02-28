from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    membership = Column(String, default="basic") # "basic" or "premium"
    total_return = Column(Float, default=0.0) # Phase 2: Mock investment cache
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolios = relationship("Portfolio", back_populates="owner")
    comments = relationship("Comment", back_populates="user")
    votes = relationship("Vote", back_populates="user")
    alerts = relationship("Alert", back_populates="user")

class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True) # Stock code or Theme name
    target_price = Column(Float, nullable=True)
    qty = Column(Integer, default=1)
    added_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="portfolios")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="comments")

class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True)
    vote_type = Column(String) # 'BULL' or 'BEAR'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="votes")

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True)
    target_price = Column(Float)
    condition_type = Column(String) # 'ABOVE' or 'BELOW'
    is_active = Column(Integer, default=1) # 1 for active, 0 for inactive, SQLite default bool replacement
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="alerts")
