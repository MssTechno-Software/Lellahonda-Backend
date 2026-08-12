# main.py
from fastapi import FastAPI, Depends, HTTPException, Query, status, Security
from fastapi.middleware.cors import CORSMiddleware
from zoneinfo import ZoneInfo
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Annotated
from database import Base, engine, get_db
import models 
import schemas
from pydantic import BaseModel, Field
import random 
import time
from typing import Union
from typing import Optional
from datetime import timedelta, datetime, timezone
from jose import JWTError, jwt
from dotenv import load_dotenv
from fastapi import Request, UploadFile, File
import pandas as pd
import io
import os
import pandas as _pd
import io as _io
from datetime import timedelta, datetime, timezone, date
from sqlalchemy import or_
import bcrypt
from fastapi import Query

IST = ZoneInfo("Asia/Kolkata")
# Load environment variables from .env file
load_dotenv()

# --- JWT Security Constants ---
SECRET_KEY_RAW = os.getenv("JWT_SECRET_KEY")

if not SECRET_KEY_RAW:
    raise RuntimeError(
        "Environment variable 'JWT_SECRET_KEY' is not set. "
        "Please set JWT_SECRET_KEY in your environment or .env file to a non-empty string used to sign JWTs."
    )
SECRET_KEY = SECRET_KEY_RAW
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 180
REFRESH_TOKEN_EXPIRE_MINUTES = 200



SUPER_ADMIN_USERNAME = "Superadmin"
SUPER_ADMIN_PASSWORD = "admin1234"
# ------------------------------


#------------------------------------------------------------------
def create_db_tables():
    """Checks for tables and creates them if they don't exist."""
    print("Attempting to create database tables...")
    try:
        # This safely creates tables ONLY IF they don't exist:
        Base.metadata.create_all(bind=engine) 
        print("Database tables created successfully!")
    except Exception as e:
        print(f"FATAL ERROR: Failed to create tables. Ensure PostgreSQL is running. Error: {e}")

create_db_tables() 

app = FastAPI(redirect_slashes=False)

# CORS configuration
# NOTE: For development allow all origins. In production set a restricted list of origins.
# CORS configuration
origins = [
    "https://leelahonda-frontend.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPER FUNCTIONS ---

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Generates the JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _to_date(val):

    if val is None:
        return None
    try:
        import pandas as _pd
        import datetime as _dt
        if isinstance(val, _pd.Timestamp):
            return val.date()
        if isinstance(val, _dt.datetime):
            return val.date()
        if isinstance(val, _dt.date):
            return val
        if isinstance(val, (int, float)): 
            parsed = _pd.to_datetime(val, origin="1899-12-30", unit="D", errors="coerce")
            return None if parsed is _pd.NaT else parsed.date()
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            parsed = _pd.to_datetime(s, errors="coerce", dayfirst=False)
            return None if parsed is _pd.NaT else parsed.date()
        return None
    except Exception:
        return None

def _normalize_stock_payload(d: dict) -> dict:
    allowed = {
        "Frame",
        "EngineNoMotorNo",
        "ModelVariant",
        "ProductName",
        "Color",
        "ModelName",
        "ManufacturingDate",
        "Location",
        "StockTrasnferDate",
    }
    data = {k: v for k, v in d.items() if k in allowed}

    # Default Location if blank/missing
    loc = data.get("Location")
    if loc is None or str(loc).strip().lower() in {"", "none", "nan"}:
        data["Location"] = "Godown"
    if "ManufacturingDate" in data:
        data["ManufacturingDate"] = _to_date(data.get("ManufacturingDate"))
    if "StockTrasnferDate" in data:
        data["StockTrasnferDate"] = _to_date(data.get("StockTrasnferDate"))

    return data

def _excel_to_records(xlsx_bytes: bytes) -> list[dict]:
    
    try:
        df = pd.read_excel(_io.BytesIO(xlsx_bytes))
    except Exception:
        try:
            df = pd.read_csv(_io.BytesIO(xlsx_bytes))  
        except Exception:
            raise ValueError("File is not a valid Excel or CSV format.")  

    df.columns = [str(c).strip() for c in df.columns]

    # 2) Map variants
    alias_map = {
        # FRAME
        "frame": "Frame",
        "frame no": "Frame",
        "frame number": "Frame",
        "frame #": "Frame",
        "frameno": "Frame",
        "chassis no": "Frame",
        "chassis number": "Frame",

        # ENGINE NO / MOTOR NO
        "engine no": "Engine No/Motor No",
        "engine number": "Engine No/Motor No",
        "motor no": "Engine No/Motor No",
        "motor number": "Engine No/Motor No",
        "engine no/motor no": "Engine No/Motor No",

        # MODEL VARIANT
        "model variant": "Model Variant",
        "variant": "Model Variant",
        "modelvariant": "Model Variant",

        # MODEL NAME (your new field)
        "model name": "Model Name",
        "model": "Model Name",
        "modelname": "Model Name",
        "m name": "Model Name",

        # PRODUCT NAME
        "product name": "Product Name",
        "product": "Product Name",

        # COLOR
        "color": "Color",
        "colour": "Color",

        # MANUFACTURING DATE
        "manufacturing date": "Manufacturing Date",
        "mfg date": "Manufacturing Date",
        "mfd date": "Manufacturing Date",
        "mfd": "Manufacturing Date",
        "mfg": "Manufacturing Date",

        # LOCATION
        "location": "Location",
        "loc": "Location",

        # STOCK TRANSFER DATE (typo preserved because DB has typo)
        "stock trasnfer date": "Stock Trasnfer Date",
        "stock transfer date": "Stock Trasnfer Date",
        "transfer date": "Stock Trasnfer Date",
        "transferdate": "Stock Trasnfer Date",
    }


    kept_cols = {}
    for col in df.columns:
        key = alias_map.get(col.strip().lower())
        if key:
            kept_cols[col] = key

    if not kept_cols:
        raise ValueError(f"No valid columns found. Got: {list(df.columns)}")

    df = df.rename(columns=kept_cols)
    df = df[list(kept_cols.values())]


    # 3) Normalize NaN -> None
    df = df.where(pd.notnull(df), None)

    if "Location" not in df.columns:
        df["Location"] = "Godown"
    else:
        def _fix_loc(v):
            if v is None:
                return "Godown"
            if isinstance(v, float) and pd.isna(v):
                return "Godown"
            if isinstance(v, str) and not v.strip():
                return "Godown"
            return str(v)
        df["Location"] = df["Location"].map(_fix_loc)
    # END LOCATION BLOCK

    # 4) Convert date-like to ISO strings
    def _date_to_iso(val):
        d = _to_date(val)
        return None if d is None else d.isoformat()

    if "Manufacturing Date" in df.columns:
        df["Manufacturing Date"] = df["Manufacturing Date"].map(_date_to_iso)
    if "Stock Trasnfer Date" in df.columns:
        df["Stock Trasnfer Date"] = df["Stock Trasnfer Date"].map(_date_to_iso)

    # 5) Build StockCreate
    raw_rows = df.to_dict(orient="records")
    records = []
    for row in raw_rows:
        sc = schemas.StockCreate(**row)                
        records.append(sc.model_dump(by_alias=False))   
    return records


def _write_location_log(
    db: Session,
    *,
    stock: models.Stock,
    actor: models.User | None,
    transfer_date_val: date | None
):
    log = models.LocationLog(
        frame=stock.Frame,
        location=stock.Location,
        transfer_date=transfer_date_val,
        first_name=(actor.first_name if actor else None),
        last_name=(actor.last_name if actor else None),
        mobile=(actor.phone_no if actor else None),
        role=(actor.role if actor else None),
    )
    db.add(log)
 
# def _move_stock_to_delivered(db: Session, stock: models.Stock, actor: models.User) -> models.Delivered:
#     # skip if already moved (by frame uniqueness)
#     existing = db.query(models.Delivered).filter(models.Delivered.Frame == stock.Frame).first()
#     if existing:
#         # ensure original stock is removed
#         db.delete(stock)
#         return existing

#     delivered_row = models.Delivered(
#         Frame=stock.Frame,
#         EngineNoMotorNo=stock.EngineNoMotorNo,
#         ModelVariant=stock.ModelVariant,
#         ProductName=stock.ProductName,
#         Color=stock.Color,
#         ModelName=stock.ModelName,
#         ManufacturingDate=stock.ManufacturingDate,
#         Location=stock.Location,  # final location at delivery moment
#         DeliveredDateTime=datetime.now(timezone.utc),
#     )
#     db.add(delivered_row)
#     db.delete(stock)  # REMOVE from stocks table
#     return delivered_row

def _move_stock_to_delivered(db: Session, stock: models.Stock, actor: models.User) -> models.Delivered:
    existing = db.query(models.Delivered).filter(models.Delivered.Frame == stock.Frame).first()
    if existing:
        db.delete(stock)
        return existing

    delivered_row = models.Delivered(
        Frame=stock.Frame,
        EngineNoMotorNo=stock.EngineNoMotorNo,
        ModelVariant=stock.ModelVariant,
        ProductName=stock.ProductName,
        Color=stock.Color,
        ModelName=stock.ModelName,
        ManufacturingDate=stock.ManufacturingDate,
        Location=stock.Location,
        DeliveredDateTime=datetime.now(IST),
    )
    db.add(delivered_row)
    db.delete(stock)
    return delivered_row

def _write_audit(
    db: Session,
    *,
    actor: models.User | None,
    action: str,
    count: int = 1,
    frame: str | None = None,
    details: str | None = None,
):
    db.add(models.AuditLog(
        action=action,
        count=count,
        frame=frame,
        details=details,
        actor_username=(actor.username if actor else None),
        actor_first_name=(actor.first_name if actor else None),
        actor_last_name=(actor.last_name if actor else None),
        actor_role=(actor.role if actor else None),
    ))

def _build_change_details(before: dict, stock: models.Stock, fields: list[str]) -> str | None:
    label = {
        "EngineNoMotorNo": "Engine No/Motor No",
        "ModelVariant": "Model Variant",
        "ProductName": "Product Name",
        "ModelName": "Model Name",
        "ManufacturingDate": "Manufacturing Date",
        "StockTrasnferDate": "Stock Trasnfer Date",
        "Location": "Location",
        "Frame": "Frame",
    }
    parts = []
    for f in fields:
        old = before.get(f)
        new = getattr(stock, f, None)
        if old != new:
            parts.append(f"{label.get(f, f)}: {old or 'None'} -> {new or 'None'}")
    return "; ".join(parts) if parts else None



# STOCK: update schemas 

class StockUpdate(BaseModel):
    Frame: Optional[str] = None
    EngineNoMotorNo: Optional[str] = Field(default=None, alias='Engine No/Motor No')
    ModelVariant: Optional[str] = Field(default=None, alias='Model Variant')
    ProductName: Optional[str] = Field(default=None, alias='Product Name')
    Color: Optional[str] = None
    ModelName: Optional[str] = Field(default=None, alias='Model Name')
    ManufacturingDate: Optional[str] = Field(default=None, alias='Manufacturing Date')
    Location: Optional[str] = None
    StockTrasnferDate: Optional[str] = Field(default=None, alias='Stock Trasnfer Date')

    class Config:
        populate_by_name = True 


class LocationUpdate(BaseModel):
    location: Optional[str] = None  # default to "Godown"

class BulkDeleteStocks(BaseModel):
    ids: List[int]  




# ----------------------------- AUTHENTICATION COMPONENTS -----------------------------
 
# --- SECURITY UTILITIES  ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
 
# Function to get the current authenticated username from the JWT token
def get_current_username(token: str = Security(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return username
 
# Function to get the full user object
def get_current_user(username: Annotated[str, Depends(get_current_username)], db: Session = Depends(get_db)):
    # Super admin is not a DB row - build a transient (never added/committed) User object
    # so downstream code (is_admin, audit logs, etc.) works exactly like it does for real users.
    if SUPER_ADMIN_USERNAME and username == SUPER_ADMIN_USERNAME:
        return models.User(
            id=0,
            first_name="Super",
            last_name="Admin",
            username=SUPER_ADMIN_USERNAME,
            phone_no=None,
            location=None,
            role="admin",
        )
 
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Authenticated user not found")
    return user
 
# Dependency to check if the current user is an admin
def is_admin(current_user: Annotated[models.User, Depends(get_current_user)]):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Admin role required.")
    return current_user
 

# ----------------------------- AUTH: REQUEST OTP -----------------------------

from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends

@app.post("/auth/login", response_model=schemas.Token, tags=["auth"])
def login_with_username_password(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # --- Super admin path: not a DB row, checked against the hardcoded credentials above ---
    if form_data.username == SUPER_ADMIN_USERNAME:
        if form_data.password != SUPER_ADMIN_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
 
        access_token = create_access_token(
            data={"sub": SUPER_ADMIN_USERNAME, "role": "admin"},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        refresh_token = create_access_token(
            data={"sub": SUPER_ADMIN_USERNAME, "role": "admin", "type": "refresh"},
            expires_delta=timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES),
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "role": "admin",
        }
 
    # Find user
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()
 
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
 
    # Verify password
    if not verify_password(
        form_data.password,
        getattr(user, "password_hash", "") or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
 
    # Access token
    access_token_expires = timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
 
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role
        },
        expires_delta=access_token_expires,
    )
 
    # Refresh token
    refresh_token_expires = timedelta(
        minutes=REFRESH_TOKEN_EXPIRE_MINUTES
    )
 
    refresh_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "type": "refresh"
        },
        expires_delta=refresh_token_expires,
    )
 
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role,
    }
# ----------------------------- USER ENDPOINTS (COMPLETE CRUD) -----------------------------

@app.get("/")
def read_root():
    return {"message": "System operational. Check /docs for endpoints."}

'''@app.post("/create_users", response_model=schemas.User)
def create_user(user: schemas.UserCreate,admin_user: Annotated[models.User, Depends(is_admin)], db: Session = Depends(get_db)):'''
@app.post("/create_users", response_model=schemas.User)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Creates a new user and ensures the phone number is not already registered."""
    
    # Check 1: Duplicate username
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")

    # Check 2: Unique phone number constraint
    if user.phone_no: 
        if db.query(models.User).filter(models.User.phone_no == user.phone_no).first():
            raise HTTPException(status_code=400, detail="Mobile number is already linked to another account.")

    # Build the ORM user
    db_user = models.User(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        phone_no=user.phone_no,
        location=user.location,
        role=user.role,
        password_hash=hash_password(user.password),  # <-- NEW: store ONLY the hash
)

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# @app.get("/get_users", response_model=List[schemas.User])
# def read_all_users(admin_user: Annotated[models.User, Depends(is_admin)], db: Session = Depends(get_db)):
#     """Retrieves all user records."""
#     users = db.query(models.User).all()
#     return users

@app.get("/get_users", response_model=List[schemas.User])
def read_all_users(admin_user: Annotated[models.User, Depends(is_admin)], db: Session = Depends(get_db)):
    """Retrieves all user records, excluding other admin accounts."""
    users = (
        db.query(models.User)
        .filter(
            or_(
                models.User.role != "admin",
                models.User.id == admin_user.id,
            )
        )
        .all()
    )
    return users

@app.get("/get_users/{user_id}", response_model=schemas.User)
def read_user_by_id(user_id: int,admin_user: Annotated[models.User, Depends(is_admin)], db: Session = Depends(get_db)):
    """Retrieves a single user record by its ID."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# update user with role & admin guards
# @app.put("/update_users/{user_id}", response_model=schemas.User)
# def update_user(
#     user_id: int,
#     user_update: schemas.UserUpdate,
#     admin_user: Annotated[models.User, Depends(is_admin)],   
#     db: Session = Depends(get_db),
# ):
#     """
#     Admin-only: update a user's details.
#     - Enforces phone number uniqueness.
#     - Demotion guard: cannot demote the LAST remaining admin to user.
#     """
#     db_user = db.query(models.User).filter(models.User.id == user_id).first()
#     if not db_user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # Phone number uniqueness
#     if user_update.phone_no:
#         existing_user_with_phone = (
#             db.query(models.User).filter(models.User.phone_no == user_update.phone_no).first()
#         )
#         if existing_user_with_phone and existing_user_with_phone.id != user_id:
#             raise HTTPException(status_code=400, detail="Mobile number is already linked to another account.")

#     # Demotion guard: prevent removing the last admin
#     if user_update.role is not None and db_user.role == "admin" and user_update.role == "user":
#         total_admins = db.query(models.User).filter(models.User.role == "admin").count()
#         if total_admins <= 1:
#             raise HTTPException(
#                 status_code=403,
#                 detail="Demotion Guard: Cannot remove the last remaining admin."
#             )

#     # Apply updates
#     update_data = user_update.model_dump(exclude_unset=True)
#     for key, value in update_data.items():
#         setattr(db_user, key, value)

#     db.commit()
#     db.refresh(db_user)
#     return db_user

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

@app.put("/update_users/{user_id}", response_model=schemas.User)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    admin_user: Annotated[models.User, Depends(is_admin)],
    db: Session = Depends(get_db),
):
    """
    Admin-only: update a user's details.
    - Enforces phone number uniqueness.
    - Demotion guard: cannot demote the LAST remaining admin to user.
    - Optionally updates password (hashed before storage).
    """
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Phone number uniqueness
    if user_update.phone_no:
        existing_user_with_phone = (
            db.query(models.User).filter(models.User.phone_no == user_update.phone_no).first()
        )
        if existing_user_with_phone and existing_user_with_phone.id != user_id:
            raise HTTPException(status_code=400, detail="Mobile number is already linked to another account.")

    # Demotion guard: prevent removing the last admin
    if user_update.role is not None and db_user.role == "admin" and user_update.role == "user":
        total_admins = db.query(models.User).filter(models.User.role == "admin").count()
        if total_admins <= 1:
            raise HTTPException(
                status_code=403,
                detail="Demotion Guard: Cannot remove the last remaining admin."
            )

    # Apply updates
    update_data = user_update.model_dump(exclude_unset=True)

    # Handle password separately — hash before storing, never mass-assign raw
    if "password" in update_data:
        raw_password = update_data.pop("password")
        if raw_password:  # guard against empty string
            db_user.password_hash = hash_password(raw_password)  # fixed: matches models.User.password_hash

    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.commit()
    db.refresh(db_user)
    return db_user

# delete returns 200 with message; guards preserved 
@app.delete("/delete_users/{user_id}", status_code=200)
def delete_user(
    user_id: int, 
    admin_user: Annotated[models.User, Depends(is_admin)],
    db: Session = Depends(get_db), 
):
    """Deletes a user record. Requires admin privileges and enforces deletion guards."""
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. IMPLEMENT SELF-DELETE GUARD
    if db_user.id == admin_user.id:
        raise HTTPException(status_code=403, detail="Self-Delete Guard: Cannot delete your own account.")

    # 2. IMPLEMENT DELETION GUARD
    if db_user.role == "admin":
        total_admins = db.query(models.User).filter(models.User.role == "admin").count()
        if total_admins <= 1:
            raise HTTPException(
                status_code=403, 
                detail="Deletion Guard: Cannot delete the last remaining admin."
            )
            
    # 3. Execute Deletion
    db.delete(db_user)
    db.commit()
    
    return {"message": "User deleted successfully"}

# ----------------------------- STOCK ENDPOINTS (CRUD) -----------------------------

@app.post("/create_stocks", response_model=schemas.Stock)
def create_stock(
    stock: schemas.StockCreate,
    admin_user: Annotated[models.User, Depends(is_admin)], 
    db: Session = Depends(get_db),
):
    """Creates a single new stock record (admin only)."""
    if db.query(models.Stock).filter(models.Stock.Frame == stock.Frame).first():
        raise HTTPException(status_code=400, detail="Frame number already exists")

    data = _normalize_stock_payload(stock.model_dump(by_alias=False))
    data["StockTrasnferDate"] = date.today()
    db_stock = models.Stock(**data)
    db.add(db_stock)
    db.commit()
    db.refresh(db_stock)
    _write_location_log(db, stock=db_stock, actor=admin_user, transfer_date_val=db_stock.StockTrasnferDate)
    _write_audit(
        db,
        actor=admin_user,
        action="create",
        count=1,
        frame=db_stock.Frame,
        details=f"Created stock with Frame {db_stock.Frame}",
    )
    db.commit()

    return db_stock




INVENTORY_LOCATIONS = [
    "Godown",
    "Anakapalli",
    "Narsipatnam",
    "Ealamanchili",
    "Payakaraopet",
    "Adduroad",
    "Paderu",
    "Makavaripalem",
    "Vizag",
    "Ravikamatham",
]


# @app.get(
#     "/stocks",
#     response_model=schemas.StockSummary,
#     tags=["stocks"]
# )
# def get_stocks(
#     bucket: str = Query(default="all", description="one of: all or a specific location name"),
#     page: int = Query(1, ge=1),
#     limit: int = Query(20, ge=1, le=100),
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(get_current_user),
# ):
#     total_remaining = db.query(models.Stock).count()

#     summary_items = []

#     for loc in INVENTORY_LOCATIONS:
#         c = db.query(models.Stock).filter(models.Stock.Location == loc).count()

#         percentage = round((c / total_remaining * 100), 2) if total_remaining else 0

#         summary_items.append(
#             schemas.StockSummaryItem(
#                 location=loc,
#                 count=c,
#                 percentage=percentage      # <-- Add this field
#             )
#         )

#     query = db.query(models.Stock).order_by(models.Stock.id.desc())

#     # Apply location filter
#     norm_bucket = bucket.strip().lower()
#     if norm_bucket != "all":
#         for loc in INVENTORY_LOCATIONS:
#             if norm_bucket == loc.lower():
#                 query = query.filter(models.Stock.Location == loc)
#                 break

#     stock_list = (
#         query
#         .offset((page - 1) * limit)
#         .limit(limit)
#         .all()
#     )

#     return {
#         "total_remaining": total_remaining,
#         "by_location": summary_items,
#         "stocks": stock_list
#     }

@app.get(
    "/stocks",
    response_model=schemas.StockSummary,
    tags=["stocks"]
)
def get_stocks(
    bucket: str = Query(default="all", description="one of: all or a specific location name"),
    search: Optional[str] = Query(default=None, description="Search by Frame, Engine/Motor No, Product, Model, Color, or Location"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    total_remaining = db.query(models.Stock).count()

    summary_items = []
    for loc in INVENTORY_LOCATIONS:
        c = db.query(models.Stock).filter(models.Stock.Location == loc).count()
        percentage = round((c / total_remaining * 100), 2) if total_remaining else 0
        summary_items.append(
            schemas.StockSummaryItem(location=loc, count=c, percentage=percentage)
        )

    query = db.query(models.Stock)

    # Apply location filter
    norm_bucket = bucket.strip().lower()
    if norm_bucket != "all":
        for loc in INVENTORY_LOCATIONS:
            if norm_bucket == loc.lower():
                query = query.filter(models.Stock.Location == loc)
                break

    # Apply search filter
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.Stock.Frame.ilike(term),
                models.Stock.EngineNoMotorNo.ilike(term),
                models.Stock.ModelVariant.ilike(term),
                models.Stock.ProductName.ilike(term),
                models.Stock.ModelName.ilike(term),
                models.Stock.Color.ilike(term),
                models.Stock.Location.ilike(term),
            )
        )

    filtered_total = query.count()

    stock_list = (
        query
        .order_by(models.Stock.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "total_remaining": total_remaining,
        "filtered_total": filtered_total,
        "by_location": summary_items,
        "stocks": stock_list
    }


@app.get("/stocks/{stock_id}", response_model=schemas.Stock)
def read_stock_by_id(
    stock_id: int,
    admin_user: Annotated[models.User, Depends(is_admin)],  
    db: Session = Depends(get_db),
):
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return stock

@app.put("/update_stocks/{stock_id}", response_model=Union[schemas.Stock, schemas.Delivered])
def admin_update_stock(
    stock_id: int,
    stock_update: StockUpdate,
    admin_user: Annotated[models.User, Depends(is_admin)], 
    db: Session = Depends(get_db),
):
    """Admin can update any stock field."""
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    update_data = stock_update.model_dump(exclude_unset=True, by_alias=False)

    # Enforce unique Frame if changing
    new_frame = update_data.get("Frame")
    if new_frame and new_frame != stock.Frame:
        if db.query(models.Stock).filter(models.Stock.Frame == new_frame).first():
            raise HTTPException(status_code=400, detail="Frame number already exists")

    # Coerce dates & default location
    clean = _normalize_stock_payload(update_data)

    before = {
    "Frame": stock.Frame,
    "EngineNoMotorNo": stock.EngineNoMotorNo,
    "ModelVariant": stock.ModelVariant,
    "ProductName": stock.ProductName,
    "Color": stock.Color,
    "ModelName": stock.ModelName,
    "ManufacturingDate": stock.ManufacturingDate,
    "Location": stock.Location,
    }

    for k, v in clean.items():
        setattr(stock, k, v)

    # Only treat this as a "transfer" if the Location actually changed.
    location_changed = stock.Location != before.get("Location")
    if location_changed:
        stock.StockTrasnferDate = date.today()

    all_fields = [
        "Frame",
        "EngineNoMotorNo",
        "ModelVariant",
        "ProductName",
        "Color",
        "ModelName",
        "ManufacturingDate",
        "Location",
    ]

        # ------------ MOVE TO DELIVERED IF LOCATION == "Delivered" -------------
    loc_norm = (stock.Location or "").strip().lower()
    if loc_norm == "delivered":
        details = _build_change_details(before, stock, all_fields)
        delivered_row = _move_stock_to_delivered(db, stock, admin_user)  # admin is performing this action
        _write_audit(
            db,
            actor=admin_user,
            action="deliver",
            count=1,
            frame=delivered_row.Frame,
            details=details,
        )

        db.commit()
        db.refresh(delivered_row)
        return delivered_row

    # Only write a location-history row when the Location field actually changed,
    # otherwise every unrelated update (e.g. editing Color) creates a duplicate track entry.
    if location_changed:
        _write_location_log(db, stock=stock, actor=admin_user, transfer_date_val=stock.StockTrasnferDate)

    details = _build_change_details(before, stock, all_fields)

    _write_audit(db, actor=admin_user, action="update", count=1, frame=stock.Frame, details=details)

    db.commit()
    db.refresh(stock)
    return stock



@app.delete("/delete_stocks/{stock_id}", status_code=200)
def delete_stock(
    stock_id: int,
    admin_user: Annotated[models.User, Depends(is_admin)], 
    db: Session = Depends(get_db),
):
    """Deletes a stock (admin only)."""
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    frame_copy = stock.Frame
    db.delete(stock)
    _write_audit(
        db,
        actor=admin_user,
        action="delete",
        count=1,
        frame=frame_copy,
        details="Deleted a single stock",
    )
    db.commit()
    return {"message": "Stock deleted successfully"}

@app.post("/stocks/bulk-delete", status_code=200)
def bulk_delete_stocks(
    payload: BulkDeleteStocks,
    admin_user: Annotated[models.User, Depends(is_admin)], 
    db: Session = Depends(get_db),
):
    """
    Deletes multiple stocks by IDs (admin only).
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No stock IDs provided.")

    # Fetch all stocks matching provided IDs
    stocks_to_delete = db.query(models.Stock).filter(models.Stock.id.in_(payload.ids)).all()

    if not stocks_to_delete:
        raise HTTPException(status_code=404, detail="No matching stock IDs found.")

    deleted_ids = [s.id for s in stocks_to_delete]
    for stock in stocks_to_delete:
        db.delete(stock)

    _write_audit(
    db,
    actor=admin_user,
    action="bulk_delete",
    count=len(deleted_ids),
    frame=None,
    details=f"Deleted IDs={deleted_ids}",)    

    db.commit()

    return {
        "message": f"Deleted {len(deleted_ids)} stocks successfully.",
        "deleted_ids": deleted_ids
    }


@app.patch("/stocks/{stock_id}/location", response_model=Union[schemas.Stock, schemas.Delivered])
def update_stock_location(
    stock_id: int,
    payload: LocationUpdate,
    current_user: Annotated[models.User, Depends(get_current_user)],  # any authenticated user
    db: Session = Depends(get_db),
):
    """
    Non-admin users can update only Location via this endpoint.
    Admins can also use this, but they already have full update.
    """
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    old_loc = stock.Location
    new_loc = payload.location
    if new_loc is None or str(new_loc).strip().lower() in {"", "none", "nan"}:
        new_loc = "Godown" 

    location_changed = str(new_loc) != (old_loc or "")
    stock.Location = str(new_loc)
    if location_changed:
        stock.StockTrasnferDate = date.today()

        # ------------ MOVE TO DELIVERED IF LOCATION == "Delivered" -------------
    loc_norm = (stock.Location or "").strip().lower()
    if loc_norm == "delivered":
        delivered_row = _move_stock_to_delivered(db, stock, current_user)
        _write_audit(
        db,
        actor=current_user,
        action="deliver",
        count=1,
        frame=delivered_row.Frame,
        details=f"Location: {old_loc or 'Godown'} -> Delivered",)
        db.commit()
        db.refresh(delivered_row)
        return delivered_row

    if not location_changed:
        # Nothing actually changed - return as-is without logging a fake transfer.
        db.commit()
        db.refresh(stock)
        return stock

    _write_location_log(db, stock=stock, actor=current_user, transfer_date_val=stock.StockTrasnferDate)
    details = _build_change_details(
      {"Location": old_loc},
       stock,
       ["Location"],
    )
    _write_audit(db,actor=current_user,action="update",count=1,frame=stock.Frame,details=details,)
    db.commit()
    db.refresh(stock)
    return stock


from fastapi import UploadFile, File
from typing import Annotated

@app.post("/stocks/upload-excel-binary")
async def upload_stocks_excel_binary(
    file: UploadFile = File(...),
    admin_user: models.User = Depends(is_admin),
    db: Session = Depends(get_db),
):
    xlsx_bytes = await file.read()

    try:
        records = _excel_to_records(xlsx_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel: {e}")

    created, skipped, errors = 0, [], []

    for i, rec in enumerate(records, start=1):
        try:
            if db.query(models.Stock).filter(models.Stock.Frame == rec["Frame"]).first():
                skipped.append({"row": i, "reason": f"Duplicate Frame '{rec['Frame']}'"})
                continue

            data = _normalize_stock_payload(rec)
            data["StockTrasnferDate"] = date.today()

            obj = models.Stock(**data)
            db.add(obj)
            db.flush()

            _write_location_log(
                db,
                stock=obj,
                actor=admin_user,
                transfer_date_val=obj.StockTrasnferDate
            )

            created += 1

        except Exception as e:
            errors.append({"row": i, "error": str(e)})

    _write_audit(
        db,
        actor=admin_user,
        action="upload",
        count=created,
        details=f"Excel upload: created={created}, skipped={len(skipped)}, errors={len(errors)}"
    )

    db.commit()

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors
    }



# @app.get("/delivered", response_model=schemas.DeliveredList, tags=["delivered"])
# def list_delivered(
#     delivered_date: Optional[date] = Query(default=None, description="Filter by exact date YYYY-MM-DD"),
#     date_from: Optional[date] = Query(default=None, description="Filter range start date"),
#     date_to: Optional[date] = Query(default=None, description="Filter range end date"),
#     page: int = Query(1, ge=1),
#     limit: int = Query(20, ge=1, le=100),
#     db: Session = Depends(get_db),
#     admin_user: models.User = Depends(is_admin),
# ):
#     q = db.query(models.Delivered)

#     if delivered_date:
#         start = datetime.combine(delivered_date, datetime.min.time(), tzinfo=timezone.utc)
#         end = datetime.combine(delivered_date, datetime.max.time(), tzinfo=timezone.utc)
#         q = q.filter(
#             models.Delivered.DeliveredDateTime >= start,
#             models.Delivered.DeliveredDateTime <= end
#         )
#     else:
#         if date_from:
#             start = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
#             q = q.filter(models.Delivered.DeliveredDateTime >= start)
#         if date_to:
#             end = datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
#             q = q.filter(models.Delivered.DeliveredDateTime <= end)

#     filtered_total = q.count()

#     records = (
#         q.order_by(models.Delivered.DeliveredDateTime.desc())
#         .offset((page - 1) * limit)
#         .limit(limit)
#         .all()
#     )

#     # --- Summary counts (independent of the date filters above) ---
#     now = datetime.now(timezone.utc)
#     today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
#     today_end = datetime.combine(now.date(), datetime.max.time(), tzinfo=timezone.utc)
#     month_start = datetime.combine(now.date().replace(day=1), datetime.min.time(), tzinfo=timezone.utc)

#     total_delivered = db.query(models.Delivered).count()

#     today_delivered = (
#         db.query(models.Delivered)
#         .filter(
#             models.Delivered.DeliveredDateTime >= today_start,
#             models.Delivered.DeliveredDateTime <= today_end,
#         )
#         .count()
#     )

#     month_delivered = (
#         db.query(models.Delivered)
#         .filter(models.Delivered.DeliveredDateTime >= month_start)
#         .count()
#     )

#     return {
#         "total_delivered": total_delivered,      # all-time total (unaffected by filters/pagination)
#         "today_delivered": today_delivered,
#         "month_delivered": month_delivered,
#         "filtered_total": filtered_total,         # count matching the applied date filters, if any
#         "items": records
#     }

@app.get("/delivered", response_model=schemas.DeliveredList, tags=["delivered"])
def list_delivered(
    search: Optional[str] = Query(default=None, description="Search by Frame, Engine/Motor No, Product, Model, or Color"),
    delivered_date: Optional[date] = Query(default=None, description="Filter by exact date YYYY-MM-DD"),
    date_from: Optional[date] = Query(default=None, description="Filter range start date"),
    date_to: Optional[date] = Query(default=None, description="Filter range end date"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
    #admin_user: models.User = Depends(is_admin),
):
    q = db.query(models.Delivered)

    # --- date filters, now interpreted as IST calendar days ---
    if delivered_date:
        start = datetime.combine(delivered_date, datetime.min.time(), tzinfo=IST)
        end = datetime.combine(delivered_date, datetime.max.time(), tzinfo=IST)
        q = q.filter(
            models.Delivered.DeliveredDateTime >= start,
            models.Delivered.DeliveredDateTime <= end
        )
    else:
        if date_from:
            start = datetime.combine(date_from, datetime.min.time(), tzinfo=IST)
            q = q.filter(models.Delivered.DeliveredDateTime >= start)
        if date_to:
            end = datetime.combine(date_to, datetime.max.time(), tzinfo=IST)
            q = q.filter(models.Delivered.DeliveredDateTime <= end)

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.Delivered.Frame.ilike(term),
                models.Delivered.EngineNoMotorNo.ilike(term),
                models.Delivered.ModelVariant.ilike(term),
                models.Delivered.ProductName.ilike(term),
                models.Delivered.ModelName.ilike(term),
                models.Delivered.Color.ilike(term),
            )
        )

    filtered_total = q.count()

    records = (
        q.order_by(models.Delivered.DeliveredDateTime.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    # --- summary counts, now using IST "today" / "this month" ---
    now = datetime.now(IST)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=IST)
    today_end = datetime.combine(now.date(), datetime.max.time(), tzinfo=IST)
    month_start = datetime.combine(now.date().replace(day=1), datetime.min.time(), tzinfo=IST)

    total_delivered = db.query(models.Delivered).count()

    today_delivered = (
        db.query(models.Delivered)
        .filter(
            models.Delivered.DeliveredDateTime >= today_start,
            models.Delivered.DeliveredDateTime <= today_end,
        )
        .count()
    )

    month_delivered = (
        db.query(models.Delivered)
        .filter(models.Delivered.DeliveredDateTime >= month_start)
        .count()
    )

    return {
        "total_delivered": total_delivered,
        "today_delivered": today_delivered,
        "month_delivered": month_delivered,
        "filtered_total": filtered_total,
        "items": records
    }

@app.get("/location_logs/track/{frame}")
def get_location_log_simple(
    frame: str,
    admin_user: Annotated[models.User, Depends(is_admin)],
    db: Session = Depends(get_db),
):
    logs = (
        db.query(models.LocationLog)
        .filter(models.LocationLog.frame == frame)
        .order_by(models.LocationLog.transfer_date.asc(), models.LocationLog.id.asc())
        .all()
    )
    if not logs:
        raise HTTPException(status_code=404, detail=f"No location history found for frame '{frame}'.")

    out = []
    for r in logs:
        full_name = f"{(r.first_name or '').strip()} {(r.last_name or '').strip()}".strip()
        out.append({
            "location": r.location,
            "transfer_date": r.transfer_date.strftime("%Y-%m-%d") if r.transfer_date else None,
            "updated_by": full_name
        })
    return {"frame": frame, "records": out}


from fastapi import Query

# @app.get("/audit_logs", tags=["audit"])
# def get_audit_logs(
#     admin_user: Annotated[models.User, Depends(is_admin)],
#     db: Session = Depends(get_db),
#     page: int = Query(1, ge=1),
#     limit: int = Query(20, ge=1, le=100)
# ):
#     """
#     Returns simplified audit entries:
#       - username
#       - done_by (First Last if available, else username)
#       - role of the user who performed the action
#       - action, count, frame, details, at
#     """

#     offset = (page - 1) * limit

#     logs = (
#         db.query(models.AuditLog)
#         .order_by(models.AuditLog.at.desc())
#         .offset(offset)
#         .limit(limit)
#         .all()
#     )

#     out = []
#     for l in logs:
#         full_name = f"{(l.actor_first_name or '').strip()} {(l.actor_last_name or '').strip()}".strip()
#         done_by = full_name if full_name else (l.actor_username or "")

#         out.append({
#             "action": l.action,
#             "count": l.count,
#             "frame": l.frame,
#             "details": l.details,
#             "username": l.actor_username,
#             "done_by": done_by,
#             "role": l.actor_role,
#             "at": l.at,
#         })

#     return out

@app.get("/audit_logs", tags=["audit"])
def get_audit_logs(
    #admin_user: Annotated[models.User, Depends(is_admin)],
    db: Session = Depends(get_db),
    search: Optional[str] = Query(default=None, description="Search by username, actor name, action, frame, or details"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    query = db.query(models.AuditLog)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.AuditLog.actor_username.ilike(term),
                models.AuditLog.actor_first_name.ilike(term),
                models.AuditLog.actor_last_name.ilike(term),
                models.AuditLog.action.ilike(term),
                models.AuditLog.frame.ilike(term),
                models.AuditLog.details.ilike(term),
            )
        )

    filtered_total = query.count()
    offset = (page - 1) * limit

    logs = (
        query
        .order_by(models.AuditLog.at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    out = []
    for l in logs:
        full_name = f"{(l.actor_first_name or '').strip()} {(l.actor_last_name or '').strip()}".strip()
        done_by = full_name if full_name else (l.actor_username or "")
        out.append({
            "action": l.action,
            "count": l.count,
            "frame": l.frame,
            "details": l.details,
            "username": l.actor_username,
            "done_by": done_by,
            "role": l.actor_role,
            "at": l.at,
        })

    return {
        "filtered_total": filtered_total,
        "page": page,
        "limit": limit,
        "items": out,
    }