import sys, os
sys.path.insert(0, os.getcwd())
import io
import csv
from app.database import SessionLocal, InventoryItem, SalesHistory, User
from app.main import (
    app,
    load_models,
    get_all_sales_history,
    get_sales_summary,
    export_sales_csv,
    get_sales_history,
    get_ml_insights
)

load_models()

db = SessionLocal()
admin = db.query(User).filter(User.username == 'admin').first()

print("--- 1. Database Integrity ---")
total_items = db.query(InventoryItem).count()
total_sales = db.query(SalesHistory).count()
distinct_items_with_sales = db.query(SalesHistory.item_id).distinct().count()

print(f"Total Items: {total_items}")
print(f"Total Sales: {total_sales}")
print(f"Items with sales: {distinct_items_with_sales} / {total_items}")

assert total_items >= 200, f"Expected at least 200 items, got {total_items}"
assert total_sales >= 3905, f"Expected at least 3905 sales, got {total_sales}"
assert distinct_items_with_sales == total_items, f"Expected {total_items} items with sales, got {distinct_items_with_sales}"

# Verify no revenue mismatches
mismatches = 0
for s in db.query(SalesHistory).all():
    item = db.query(InventoryItem).filter(InventoryItem.id == s.item_id).first()
    expected = round(s.quantity_sold * item.price, 2)
    if abs(s.total_revenue - expected) > 0.05:
        mismatches += 1
print(f"Revenue Mismatches: {mismatches}")
assert mismatches == 0, f"Expected 0 mismatches, got {mismatches}"

print("\n--- 2. Sales API Endpoint (/sales/ & /sales/summary) ---")
summary = get_sales_summary(db=db, user=admin)
print(f"get_sales_summary: {summary}")
assert summary["total_count"] == total_sales

all_sales = get_all_sales_history(db=db, user=admin)
print(f"get_all_sales_history count: {len(all_sales)}")
assert len(all_sales) == total_sales, f"Expected {total_sales}, got {len(all_sales)}"

search_res = get_all_sales_history(search="Smart", db=db, user=admin)
print(f"get_all_sales_history(search='Smart') count: {len(search_res)}")
assert len(search_res) > 0, "Search for 'Smart' should return results"

limit_res = get_all_sales_history(skip=0, limit=50, db=db, user=admin)
print(f"get_all_sales_history(skip=0, limit=50) count: {len(limit_res)}")
assert len(limit_res) == 50, f"Expected 50, got {len(limit_res)}"

print("\n--- 3. Per-Item Sales API (/items/{id}/sales) ---")
# Check previously unpopulated items (e.g. 101, 150, 200)
for test_id in [1, 101, 150, 200]:
    item_sales = get_sales_history(item_id=test_id, db=db, user=admin)
    print(f"Item {test_id} sales count: {len(item_sales)}")
    assert len(item_sales) > 0, f"Item {test_id} should have sales"

print("\n--- 4. ML Insights for Repaired Items ---")
# Item 105 insight test
insight_105 = get_ml_insights(item_id=105, db=db, user=admin)
print(f"Item 105 ML Insight: {insight_105}")
assert "segment" in insight_105
assert "predicted_demand_30d" in insight_105

print("\n--- 5. Sales CSV Export ---")
import asyncio

async def test_csv():
    csv_resp = export_sales_csv(db=db, user=admin)
    chunks = []
    async for chunk in csv_resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode('utf-8'))
    content = "".join(chunks)
    csv_lines = content.strip().splitlines()
    print(f"Export CSV lines count: {len(csv_lines)} (including header)")
    assert len(csv_lines) == total_sales + 1, f"Expected {total_sales + 1} lines (header + {total_sales} rows), got {len(csv_lines)}"

asyncio.run(test_csv())

print("\nALL SALES HISTORY REPAIR VERIFICATIONS PASSED!")
db.close()
