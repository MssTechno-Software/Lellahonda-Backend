from sqlalchemy import Column, DateTime, Integer, String, Float, Date 
from database import Base
from sqlalchemy.sql import func
from datetime import datetime
from sqlalchemy.types import Text as SAText

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True, nullable=False)
    last_name = Column(String, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone_no = Column(String, nullable=True) 
    location = Column(String, nullable=True) 
    role = Column(String, default="user", nullable=False)

class Stock(Base):
    __tablename__ = "stocks"
    id = Column(Integer, primary_key=True, index=True)
    Frame = Column(String, unique=True, index=True, nullable=False)
    EngineNoMotorNo = Column('Engine No/Motor No', String, nullable=False)
    ModelVariant = Column('Model Variant', String, nullable=True)
    ProductName = Column('Product Name', String, nullable=False)
    ModelName = Column("Model Name", String, nullable=True)
    Color = Column(String, nullable=True)
    ManufacturingDate = Column('Manufacturing Date', Date, nullable=True) 
    Location = Column(String, nullable=True) 
    StockTrasnferDate = Column('Stock Trasnfer Date', Date, nullable=True)

class LocationLog(Base):
    __tablename__ = "location_log"

    id = Column(Integer, primary_key=True, index=True)
    frame = Column(String, index=True, nullable=False)
    location = Column(String, nullable=True)
    transfer_date = Column(Date, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    role = Column(String, nullable=True)

class Delivered(Base):
    __tablename__ = "delivered"

    id = Column(Integer, primary_key=True, index=True)

    #mirror key Stock fields
    Frame = Column(String, unique=True, index=True, nullable=False)
    EngineNoMotorNo = Column('Engine No/Motor No', String, nullable=False)
    ModelVariant = Column('Model Variant', String, nullable=True)
    ProductName = Column('Product Name', String, nullable=False)
    ModelName = Column("Model Name", String, nullable=True)
    Color = Column(String, nullable=True)
    ManufacturingDate = Column('Manufacturing Date', Date, nullable=True)
    Location = Column(String, nullable=True)
    # delivery metadata
    #DeliveredDateTime = Column('Delivered DateTime', DateTime, nullable=False, default=datetime.utcnow)
    DeliveredDateTime = Column('Delivered DateTime', DateTime(timezone=True), nullable=False, default=lambda: datetime.now(IST))
    
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)          # e.g. create | update | deliver | delete | bulk_delete | upload
    count  = Column(Integer, nullable=False, default=1)
    frame  = Column(String, nullable=True)           # for single-stock actions
    details = Column(SAText, nullable=True)          # "FieldA: old -> new, FieldB: old -> new"
    actor_username   = Column(String, nullable=True)
    actor_first_name = Column(String, nullable=True)
    actor_last_name  = Column(String, nullable=True)
    actor_role       = Column(String, nullable=True)
    at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)