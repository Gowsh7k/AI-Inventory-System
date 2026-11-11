import sqlite3
import random
import datetime
import os
from faker import Faker

fake = Faker()
os.makedirs('data', exist_ok=True)
DB_FILE = 'data/inventory.db'

CATEGORIES = ['Electronics', 'Clothing', 'Office Supplies', 'Home Goods', 'Sports']

def generate_mock_data():
    from app.database import engine, Base
    Base.metadata.create_all(bind=engine)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    import hashlib
    def get_hash(pw):
        return hashlib.sha256(pw.encode()).hexdigest()

    print("Generating default users...")
    # Using INSERT OR IGNORE to avoid errors if they already exist
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    ''', ('admin', get_hash('admin123'), 'admin'))
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    ''', ('staff', get_hash('staff123'), 'staff'))
    
    print("Generating 100 inventory items...")
    items = []
    for _ in range(100):
        sku = fake.unique.bothify(text='ITM-####-???')
        # Simple product name generation since faker.commerce isn't standard in all faker versions
        adjectives = ['Smart', 'Ergonomic', 'Wireless', 'Portable', 'Durable']
        nouns = ['Widget', 'Device', 'Tool', 'Kit', 'Apparatus']
        name = f"{random.choice(adjectives)} {random.choice(nouns)} {fake.word().capitalize()}"
        
        category = random.choice(CATEGORIES)
        price = round(random.uniform(5.0, 500.0), 2)
        stock_quantity = random.randint(10, 200)
        reorder_level = random.randint(5, 20)
        
        cursor.execute('''
            INSERT INTO inventory (sku, name, category, price, stock_quantity, reorder_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (sku, name, category, price, stock_quantity, reorder_level))
        
        item_id = cursor.lastrowid
        items.append((item_id, price)) # store actual inserted ID and price for sales simulation
    
    conn.commit()
    
    print("Simulating 6 months of sales history...")
    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=180)
    
    for item_id, price in items:
        # Generate 10-30 sales per item over the last 6 months
        num_sales = random.randint(10, 30)
        for _ in range(num_sales):
            quantity_sold = random.randint(1, 5)
            total_revenue = quantity_sold * price
            
            # Random date within the last 6 months
            random_days = random.randint(0, 180)
            sale_date = start_date + datetime.timedelta(days=random_days)
            
            cursor.execute('''
                INSERT INTO sales_history (item_id, quantity_sold, sale_date, total_revenue)
                VALUES (?, ?, ?, ?)
            ''', (item_id, quantity_sold, sale_date.strftime("%Y-%m-%d %H:%M:%S"), total_revenue))

    conn.commit()
    conn.close()
    print("Mock data generated successfully!")

if __name__ == "__main__":
    import sys
    # Add parent directory to path to allow importing app.database
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    generate_mock_data()
