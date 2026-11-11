
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import datetime
import io
import csv
import os
import base64
import hashlib
import joblib
import pandas as pd

from . import database

app = FastAPI(title="Inventory Management API")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
ML_OUTPUT_DIR = PROJECT_ROOT / "ml_training" / "outputs"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ItemBase(BaseModel):
    sku: str
    name: str
    category: str
    price: float
    stock_quantity: int
    reorder_level: int


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    reorder_level: Optional[int] = None


class ItemResponse(ItemBase):
    id: int

    class Config:
        from_attributes = True


class SaleRequest(BaseModel):
    quantity: int


class RefillRequest(BaseModel):
    quantity: int


class SaleHistoryResponse(BaseModel):
    id: int
    quantity_sold: int
    sale_date: datetime.datetime
    total_revenue: float

    class Config:
        from_attributes = True


class GlobalSaleHistoryResponse(BaseModel):
    id: int
    item_id: int
    item_name: str
    quantity_sold: int
    sale_date: datetime.datetime
    total_revenue: float

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str


def get_password_hash(password: str):
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.split(" ", 1)[1]

    try:
        username = base64.b64decode(token).decode()
        user = db.query(database.User).filter(
            database.User.username == username
        ).first()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(user: database.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@app.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(database.User).filter(
        database.User.username == req.username
    ).first()

    if not user or user.password_hash != get_password_hash(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = base64.b64encode(user.username.encode()).decode()

    return {
        "access_token": token,
        "role": user.role,
        "username": user.username
    }


@app.post("/api/users")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_admin: database.User = Depends(require_admin)
):
    if user.role not in ["admin", "staff"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    existing = db.query(database.User).filter(
        database.User.username == user.username
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    db_user = database.User(
        username=user.username,
        password_hash=get_password_hash(user.password),
        role=user.role
    )

    db.add(db_user)
    db.commit()

    return {"message": "User created successfully"}


@app.get("/api/users")
def get_users(
    db: Session = Depends(get_db),
    current_admin: database.User = Depends(require_admin)
):
    users = db.query(database.User).all()

    return [
        {"id": u.id, "username": u.username, "role": u.role}
        for u in users
    ]


DEMAND_MODEL_FILE = PROJECT_ROOT / "models" / "demand_model.pkl"
SEGMENT_MODEL_FILE = PROJECT_ROOT / "models" / "segment_model.pkl"

demand_model = None
segment_model = None


@app.on_event("startup")
def load_models():
    global demand_model, segment_model

    if DEMAND_MODEL_FILE.exists():
        demand_model = joblib.load(DEMAND_MODEL_FILE)

    if SEGMENT_MODEL_FILE.exists():
        segment_model = joblib.load(SEGMENT_MODEL_FILE)


@app.get("/api/ml/insights/{item_id}")
def get_ml_insights(
    item_id: int,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    if demand_model is None or segment_model is None:
        raise HTTPException(status_code=500, detail="ML Models not loaded")

    query = text("""
        SELECT i.price,
               i.stock_quantity,
               COALESCE(SUM(s.quantity_sold), 0) AS total_sales_vol
        FROM inventory i
        LEFT JOIN sales_history s ON i.id = s.item_id
        WHERE i.id = :item_id
        GROUP BY i.id
    """)

    result = db.execute(query, {"item_id": item_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Item not found")

    price, stock_quantity, total_sales_vol = result

    seg_input = pd.DataFrame([{
        "price": price,
        "stock_quantity": stock_quantity,
        "total_sales_vol": total_sales_vol
    }])

    segment_idx = int(segment_model.predict(seg_input)[0])

    segments = ["Dead Stock / Slow", "Fast Moving", "High Value"]
    segment_label = segments[segment_idx % 3]

    recent_sales_query = text("""
        SELECT SUM(quantity_sold)
        FROM sales_history
        WHERE item_id = :item_id
        AND sale_date >= date('now', '-30 days')
    """)

    recent_sales_res = db.execute(
        recent_sales_query,
        {"item_id": item_id}
    ).fetchone()

    recent_sales = recent_sales_res[0] if recent_sales_res and recent_sales_res[0] else 0

    try:
        demand_pred = demand_model.predict([[recent_sales]])[0]
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Demand model input format does not match the loaded model"
        )

    predicted_demand = max(0, int(round(float(demand_pred))))

    return {
        "segment": segment_label,
        "predicted_demand_30d": predicted_demand,
        "recent_sales_30d": recent_sales
    }


@app.get("/api/ml/evaluation")
def get_ml_evaluation(
    user: database.User = Depends(get_current_user)
):
    comparison_file = ML_OUTPUT_DIR / "model_comparison.csv"

    if not comparison_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Model comparison results not found. Run train_ml.py first."
        )

    try:
        with open(comparison_file, "r", newline="", encoding="utf-8") as file:
            models = list(csv.DictReader(file))

        return {
            "models": models,
            "graphs": [
                "model_comparison.png",
                "actual_vs_predicted.png",
                "residual_plot.png",
                "kmeans_clusters.png"
            ]
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read evaluation results: {str(error)}"
        )


@app.get("/api/ml/evaluation/graphs/{filename}")
def get_ml_evaluation_graph(
    filename: str,
    user: database.User = Depends(get_current_user)
):
    allowed_files = {
        "model_comparison.png",
        "actual_vs_predicted.png",
        "residual_plot.png",
        "kmeans_clusters.png"
    }

    if filename not in allowed_files:
        raise HTTPException(status_code=404, detail="Graph not found")

    graph_path = ML_OUTPUT_DIR / filename

    if not graph_path.is_file():
        raise HTTPException(status_code=404, detail="Graph file not found")

    return FileResponse(graph_path, media_type="image/png")


@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")


@app.post("/items/", response_model=ItemResponse)
def create_item(
    item: ItemCreate,
    db: Session = Depends(get_db),
    admin: database.User = Depends(require_admin)
):
    existing = db.query(database.InventoryItem).filter(
        database.InventoryItem.sku == item.sku
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")

    db_item = database.InventoryItem(**item.model_dump())

    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    return db_item


@app.get("/items/", response_model=List[ItemResponse])
def read_items(
    search: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    query = db.query(database.InventoryItem)

    if search:
        query = query.filter(
            database.InventoryItem.name.ilike(f"%{search}%")
        )

    if category and category != "All":
        query = query.filter(
            database.InventoryItem.category == category
        )

    return query.offset(skip).limit(limit).all()


@app.put("/items/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: int,
    item: ItemUpdate,
    db: Session = Depends(get_db),
    admin: database.User = Depends(require_admin)
):
    db_item = db.query(database.InventoryItem).filter(
        database.InventoryItem.id == item_id
    ).first()

    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    update_data = item.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(db_item, key, value)

    db.commit()
    db.refresh(db_item)

    return db_item


@app.post("/items/{item_id}/sell")
def sell_item(
    item_id: int,
    sale: SaleRequest,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    if sale.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    db_item = db.query(database.InventoryItem).filter(
        database.InventoryItem.id == item_id
    ).first()

    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    if db_item.stock_quantity < sale.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock")

    db_item.stock_quantity -= sale.quantity

    revenue = db_item.price * sale.quantity

    sale_record = database.SalesHistory(
        item_id=item_id,
        quantity_sold=sale.quantity,
        total_revenue=revenue
    )

    db.add(sale_record)
    db.commit()

    return {
        "message": "Sale recorded successfully",
        "new_stock": db_item.stock_quantity
    }


@app.post("/items/{item_id}/refill")
def refill_item(
    item_id: int,
    refill: RefillRequest,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    if refill.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    db_item = db.query(database.InventoryItem).filter(
        database.InventoryItem.id == item_id
    ).first()

    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db_item.stock_quantity += refill.quantity
    db.commit()

    return {
        "message": "Stock refilled successfully",
        "new_stock": db_item.stock_quantity
    }


@app.get("/items/{item_id}/sales", response_model=List[SaleHistoryResponse])
def get_sales_history(
    item_id: int,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    return db.query(database.SalesHistory).filter(
        database.SalesHistory.item_id == item_id
    ).order_by(database.SalesHistory.sale_date).all()


@app.get("/summary/categories")
def get_category_summary(
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    summary = db.query(
        database.InventoryItem.category,
        func.sum(database.InventoryItem.stock_quantity).label("total_stock"),
        func.sum(
            database.InventoryItem.stock_quantity *
            database.InventoryItem.price
        ).label("total_value")
    ).group_by(database.InventoryItem.category).all()

    return [
        {
            "category": row[0],
            "total_stock": row[1],
            "total_value": row[2] if row[2] else 0
        }
        for row in summary
    ]


@app.get("/export/csv")
def export_csv(
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    items = db.query(database.InventoryItem).all()

    stream = io.StringIO()
    writer = csv.writer(stream)

    writer.writerow([
        "ID", "SKU", "Name", "Category",
        "Price", "Stock Quantity", "Reorder Level"
    ])

    for item in items:
        writer.writerow([
            item.id,
            item.sku,
            item.name,
            item.category,
            item.price,
            item.stock_quantity,
            item.reorder_level
        ])

    response = StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=inventory_export.csv"
    )

    return response


@app.get("/export/sales-csv")
def export_sales_csv(
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    sales = db.query(
        database.SalesHistory.id,
        database.SalesHistory.item_id,
        database.InventoryItem.sku.label("item_sku"),
        database.InventoryItem.name.label("item_name"),
        database.SalesHistory.quantity_sold,
        database.SalesHistory.sale_date,
        database.SalesHistory.total_revenue
    ).join(
        database.InventoryItem,
        database.SalesHistory.item_id == database.InventoryItem.id
    ).order_by(database.SalesHistory.sale_date.desc()).all()

    stream = io.StringIO()
    writer = csv.writer(stream)

    writer.writerow([
        "Sale ID", "Item ID", "SKU", "Item Name",
        "Quantity Sold", "Sale Date", "Total Revenue"
    ])

    for s in sales:
        date_str = s.sale_date.isoformat() if hasattr(s.sale_date, 'isoformat') else str(s.sale_date)
        writer.writerow([
            s.id,
            s.item_id,
            s.item_sku,
            s.item_name,
            s.quantity_sold,
            date_str,
            s.total_revenue
        ])

    response = StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=sales_history_export.csv"
    )

    return response


def _apply_sales_filters(query, search: Optional[str] = None, category: Optional[str] = None):
    if search:
        query = query.filter(
            database.InventoryItem.name.ilike(f"%{search}%") |
            database.InventoryItem.sku.ilike(f"%{search}%")
        )
    if category and category != "All":
        query = query.filter(database.InventoryItem.category == category)
    return query


@app.get("/sales/summary")
def get_sales_summary(
    search: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    query = db.query(
        func.count(database.SalesHistory.id),
        func.coalesce(func.sum(database.SalesHistory.quantity_sold), 0),
        func.coalesce(func.sum(database.SalesHistory.total_revenue), 0.0)
    ).join(
        database.InventoryItem,
        database.SalesHistory.item_id == database.InventoryItem.id
    )

    query = _apply_sales_filters(query, search=search, category=category)
    total_count, total_units, total_revenue = query.first()

    return {
        "total_count": int(total_count or 0),
        "total_units": int(total_units or 0),
        "total_revenue": float(total_revenue or 0.0)
    }


@app.get("/sales/", response_model=List[GlobalSaleHistoryResponse])
def get_all_sales_history(
    search: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    user: database.User = Depends(get_current_user)
):
    query = db.query(
        database.SalesHistory.id,
        database.SalesHistory.item_id,
        database.InventoryItem.name.label("item_name"),
        database.SalesHistory.quantity_sold,
        database.SalesHistory.sale_date,
        database.SalesHistory.total_revenue
    ).join(
        database.InventoryItem,
        database.SalesHistory.item_id == database.InventoryItem.id
    )

    query = _apply_sales_filters(query, search=search, category=category)
    query = query.order_by(database.SalesHistory.sale_date.desc(), database.SalesHistory.id.desc())

    if skip:
        query = query.offset(skip)
    if limit:
        query = query.limit(limit)

    sales = query.all()

    return [
        {
            "id": s.id,
            "item_id": s.item_id,
            "item_name": s.item_name,
            "quantity_sold": s.quantity_sold,
            "sale_date": s.sale_date,
            "total_revenue": s.total_revenue
        }
        for s in sales
    ]
