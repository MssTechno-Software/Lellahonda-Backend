
from pydantic import BaseModel, Field,constr,ConfigDict
from typing import List, Optional, Literal
from datetime import date, datetime




# ----------------------------- USER CRUD SCHEMAS -----------------------------

# Schema for creating a new user
class UserCreate(BaseModel):
    first_name: str
    last_name: str
    username: str
    password: constr(min_length=8) = Field(..., description="Raw password; will be hashed server-side")
    phone_no: str | None = None
    location: str | None = None
    role: Literal["user", "admin"] = "user"

# Schema for reading user data
class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    username: str
    phone_no: Optional[str] = None
    location: Optional[str] = None
    role: Literal["user", "admin"] = "user"
    model_config = ConfigDict(from_attributes=True)
          

# Schema for updating an existing user
class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone_no: Optional[str] = None
    location: Optional[str] = None
    role: Optional[str] = None


class StockSummaryItem(BaseModel):
    location: str
    count: int
    percentage: float

# ----------------------------- AUTHENTICATION SCHEMAS -----------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


# Schema for the successful login response
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role:str
    


# ----------------------------- STOCK SCHEMAS -----------------------------
class StockCreate(BaseModel):
    Frame: str
    EngineNoMotorNo: str = Field(alias='Engine No/Motor No')
    ModelVariant: str = Field(alias='Model Variant')
    ProductName: str = Field(alias='Product Name')
    ModelName: Optional[str] = Field(alias="Model Name", default=None)
    Color: str
    ManufacturingDate: date | None = Field(alias='Manufacturing Date', default=None)
    Location: str | None = None
    StockTrasnferDate: date | None = Field(alias='Stock Trasnfer Date', default=None)

    
class Stock(StockCreate):
    id: int
    class Config:
        from_attributes = True
        populate_by_name = True

class StockSummary(BaseModel):
    total_remaining: int
    by_location: List[StockSummaryItem]
    stocks: List[Stock]

    model_config = ConfigDict(from_attributes=True)        

class LocationLogRead(BaseModel):
    id: int
    frame: str
    location: str | None = None
    transfer_date: date | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile: str | None = None
    role: str | None = None

    class Config:
        from_attributes = True

class DeliveredCreate(BaseModel):
    Frame: str
    EngineNoMotorNo: str = Field(alias='Engine No/Motor No')
    ModelVariant: Optional[str] = Field(default=None, alias='Model Variant')
    ProductName: str = Field(alias='Product Name')
    ModelName: Optional[str] = Field(alias="Model Name", default=None)
    Color: Optional[str] = None
    ManufacturingDate: Optional[date] = Field(default=None, alias='Manufacturing Date')
    Location: Optional[str] = None
    DeliveredDateTime: datetime = Field(alias='Delivered DateTime')
    model_config = ConfigDict(populate_by_name=True)

class Delivered(BaseModel):
    id: int
    Frame: str
    EngineNoMotorNo: str = Field(alias='Engine No/Motor No')
    ModelVariant: Optional[str] = Field(default=None, alias='Model Variant')
    ProductName: str = Field(alias='Product Name')
    ModelName: Optional[str] = Field(alias="Model Name", default=None)
    Color: Optional[str] = None
    ManufacturingDate: Optional[date] = Field(default=None, alias='Manufacturing Date')
    Location: Optional[str] = None
    DeliveredDateTime: datetime = Field(alias='Delivered DateTime')
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DeliveredList(BaseModel):
    total_delivered: int
    today_delivered: int
    month_delivered: int
    filtered_total: int
    items: List[Delivered]


class AuditLogRead(BaseModel):
    id: int
    action: str
    count: int
    frame: str | None = None
    details: str | None = None
    actor_username: str | None = None
    actor_first_name: str | None = None
    actor_last_name: str | None = None
    actor_role: str | None = None
    at: datetime
    model_config = ConfigDict(from_attributes=True)
