from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import datetime

os.makedirs('data', exist_ok=True)
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/inventory.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="staff") # "admin" or "staff"

class InventoryItem(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)
    price = Column(Float)
    stock_quantity = Column(Integer, default=0)
    reorder_level = Column(Integer, default=10)

    sales = relationship("SalesHistory", back_populates="item")

class SalesHistory(Base):
    __tablename__ = "sales_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory.id"))
    quantity_sold = Column(Integer)
    sale_date = Column(DateTime, default=datetime.datetime.utcnow)
    total_revenue = Column(Float)

    item = relationship("InventoryItem", back_populates="sales")

Base.metadata.create_all(bind=engine)
