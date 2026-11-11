import sqlite3
import os
import sys

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'inventory.db')

def repair_sales_history():
    if not os.path.exists(DB_FILE):
        print(f"Database file not found at: {DB_FILE}")
        return False

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    print("=== Sales History Diagnostic and Repair Tool ===")
    
    # 1. Gather initial statistics
    cursor.execute("SELECT COUNT(*) FROM inventory")
    total_items = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sales_history")
    total_sales = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT item_id) FROM sales_history")
    items_with_sales_before = cursor.fetchone()[0]

    print(f"Total inventory items: {total_items}")
    print(f"Total sales records: {total_sales}")
    print(f"Items with sales before repair: {items_with_sales_before} / {total_items}")

    # 2. Identify records that match item_id + 100 price
    cursor.execute("""
        SELECT s.id, s.item_id, s.quantity_sold, s.total_revenue, i1.price as curr_price, i2.price as offset_price
        FROM sales_history s
        JOIN inventory i1 ON s.item_id = i1.id
        LEFT JOIN inventory i2 ON (s.item_id + 100) = i2.id
    """)
    rows = cursor.fetchall()

    repaired_to_offset = 0
    recalculated_revenue = 0

    for sale_id, item_id, qty, rev, curr_price, offset_price in rows:
        expected_curr = round(qty * curr_price, 2)
        if abs(rev - expected_curr) > 0.05:
            # Check if this sale was intended for item_id + 100
            if offset_price is not None:
                expected_offset = round(qty * offset_price, 2)
                if abs(rev - expected_offset) <= 0.05:
                    cursor.execute("""
                        UPDATE sales_history
                        SET item_id = ?
                        WHERE id = ?
                    """, (item_id + 100, sale_id))
                    repaired_to_offset += 1
                    continue

            # If revenue still doesn't match current price, fix revenue
            correct_rev = round(qty * curr_price, 2)
            cursor.execute("""
                UPDATE sales_history
                SET total_revenue = ?
                WHERE id = ?
            """, (correct_rev, sale_id))
            recalculated_revenue += 1

    conn.commit()

    # 3. Final verification
    cursor.execute("SELECT COUNT(DISTINCT item_id) FROM sales_history")
    items_with_sales_after = cursor.fetchone()[0]

    # Check for any remaining revenue mismatches
    cursor.execute("""
        SELECT COUNT(*)
        FROM sales_history s
        JOIN inventory i ON s.item_id = i.id
        WHERE ABS(s.total_revenue - (s.quantity_sold * i.price)) > 0.05
    """)
    remaining_mismatches = cursor.fetchone()[0]

    # Check orphan sales
    cursor.execute("""
        SELECT COUNT(*)
        FROM sales_history s
        LEFT JOIN inventory i ON s.item_id = i.id
        WHERE i.id IS NULL
    """)
    orphan_sales = cursor.fetchone()[0]

    print("\n=== Repair Results ===")
    print(f"Sales records reassigned to correct item (item_id + 100): {repaired_to_offset}")
    print(f"Sales records with adjusted revenue: {recalculated_revenue}")
    print(f"Items with sales after repair: {items_with_sales_after} / {total_items}")
    print(f"Remaining revenue mismatches: {remaining_mismatches}")
    print(f"Orphan sales records: {orphan_sales}")

    conn.close()
    print("Repair completed successfully!")
    return True

if __name__ == '__main__':
    repair_sales_history()

