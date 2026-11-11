# Inventory Pro 📦

A robust, full-stack Inventory and Sales Management System. 
Built with **FastAPI**, **SQLite**, and **Vanilla HTML/CSS/JS** with **Chart.js**.

## Features
- **Stock Management**: Add, Edit, and track standard inventory metrics (SKU, Name, Category, Price, Stock).
- **Sales & Refilling**: Process sales (which deducts stock and records revenue history) and refill stock quantities.
- **Analytics Dashboard**: View aggregate category metrics (Total Value, Item Counts).
- **Sales Trends**: Interactive line charts using Chart.js to visualize sales history per item.
- **Search & Filter**: Find items instantly by name/SKU or filter by categories.
- **CSV Export**: One-click download of the entire inventory table to CSV.

## Quick Start

### 1. Setup Virtual Environment
```bash
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# Windows Command Prompt
venv\Scripts\activate.bat
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Generate Mock Data
Populate the database with 100 realistic items and 6 months of simulated sales history so your charts work out of the box:
```bash
python scripts/generate_mock_data.py
```

### 3. Run the Server
The easiest way to start the application is using the Python runner script:
```bash
python run.py
```

Open `http://localhost:8000` in your browser to view the dashboard!

## API Documentation
Once the server is running, you can access the auto-generated Swagger documentation at:
- `http://localhost:8000/docs`
