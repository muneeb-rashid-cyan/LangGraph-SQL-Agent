"""
setup_db.py — Creates and seeds the e-commerce SQLite database.

Run once before starting the agent:
    python setup_db.py

Schema:
    customers   → id, name, email, city, created_at
    products    → id, name, category, price, stock_quantity
    orders      → id, customer_id, status, total_amount, created_at
    order_items → id, order_id, product_id, quantity, unit_price
"""

import os
import sqlite3
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "ecommerce.db")

# ── Sample data pools ─────────────────────────────────────────────────────────

CUSTOMERS = [
    ("Alice Johnson",   "alice@example.com",   "New York"),
    ("Bob Smith",       "bob@example.com",     "Los Angeles"),
    ("Carol White",     "carol@example.com",   "Chicago"),
    ("David Brown",     "david@example.com",   "Houston"),
    ("Eva Martinez",    "eva@example.com",     "Phoenix"),
    ("Frank Lee",       "frank@example.com",   "Philadelphia"),
    ("Grace Kim",       "grace@example.com",   "San Antonio"),
    ("Henry Davis",     "henry@example.com",   "San Diego"),
    ("Iris Wilson",     "iris@example.com",    "Dallas"),
    ("Jack Taylor",     "jack@example.com",    "San Jose"),
    ("Karen Anderson",  "karen@example.com",   "Austin"),
    ("Leo Thomas",      "leo@example.com",     "Jacksonville"),
    ("Mia Jackson",     "mia@example.com",     "Fort Worth"),
    ("Noah Harris",     "noah@example.com",    "Columbus"),
    ("Olivia Martin",   "olivia@example.com",  "Charlotte"),
    ("Paul Thompson",   "paul@example.com",    "Indianapolis"),
    ("Quinn Garcia",    "quinn@example.com",   "San Francisco"),
    ("Rachel Martinez", "rachel@example.com",  "Seattle"),
    ("Sam Robinson",    "sam@example.com",     "Denver"),
    ("Tina Clark",      "tina@example.com",    "Nashville"),
]

PRODUCTS = [
    # (name, category, price, stock_quantity)
    ("Wireless Headphones",    "Electronics",   89.99,  120),
    ("Bluetooth Speaker",      "Electronics",   59.99,   85),
    ("USB-C Hub",              "Electronics",   45.99,  200),
    ("Mechanical Keyboard",    "Electronics",  129.99,   60),
    ("Gaming Mouse",           "Electronics",   49.99,   95),
    ("4K Monitor",             "Electronics",  399.99,   30),
    ("Webcam HD",              "Electronics",   79.99,   55),
    ("Laptop Stand",           "Accessories",   39.99,  150),
    ("Cable Organizer",        "Accessories",   14.99,  300),
    ("Phone Case",             "Accessories",   19.99,  400),
    ("Screen Cleaner Kit",     "Accessories",    9.99,  250),
    ("Desk Mat XL",            "Accessories",   34.99,  180),
    ("Running Shoes",          "Footwear",     119.99,   70),
    ("Casual Sneakers",        "Footwear",      89.99,   90),
    ("Hiking Boots",           "Footwear",     149.99,   40),
    ("Yoga Mat",               "Sports",        29.99,  110),
    ("Resistance Bands Set",   "Sports",        24.99,  130),
    ("Water Bottle (32oz)",    "Sports",        22.99,  220),
    ("Protein Shaker",         "Sports",        18.99,  175),
    ("Dumbbells 10kg Pair",    "Sports",        54.99,   45),
    ("Python Programming Book","Books",          44.99,   80),
    ("Data Science Handbook",  "Books",          49.99,   60),
    ("Clean Code",             "Books",          39.99,   95),
    ("The Pragmatic Programmer","Books",         42.99,   70),
    ("Coffee Maker",           "Kitchen",       79.99,   55),
    ("Electric Kettle",        "Kitchen",       49.99,   85),
    ("Air Fryer",              "Kitchen",      119.99,   35),
    ("Blender Pro",            "Kitchen",       89.99,   50),
    ("Noise Cancelling Earbuds","Electronics", 159.99,   75),
    ("Smart Watch",            "Electronics",  249.99,   40),
]

ORDER_STATUSES = ["completed", "completed", "completed", "shipped", "processing", "cancelled"]


def seed_database():
    # Change working directory to script location so DB is created there
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_full_path = os.path.join(script_dir, DB_PATH)

    conn = sqlite3.connect(db_full_path)
    cursor = conn.cursor()

    # ── Create tables ─────────────────────────────────────────────────────────
    cursor.executescript("""
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            city        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE products (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT    NOT NULL,
            category       TEXT    NOT NULL,
            price          REAL    NOT NULL,
            stock_quantity INTEGER NOT NULL
        );

        CREATE TABLE orders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id  INTEGER NOT NULL REFERENCES customers(id),
            status       TEXT    NOT NULL,
            total_amount REAL    NOT NULL,
            created_at   TEXT    NOT NULL
        );

        CREATE TABLE order_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL REFERENCES orders(id),
            product_id  INTEGER NOT NULL REFERENCES products(id),
            quantity    INTEGER NOT NULL,
            unit_price  REAL    NOT NULL
        );
    """)

    # ── Seed customers ────────────────────────────────────────────────────────
    base_date = datetime(2023, 1, 1)
    customer_rows = [
        (name, email, city, (base_date + timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d"))
        for name, email, city in CUSTOMERS
    ]
    cursor.executemany(
        "INSERT INTO customers (name, email, city, created_at) VALUES (?, ?, ?, ?)",
        customer_rows,
    )

    # ── Seed products ─────────────────────────────────────────────────────────
    cursor.executemany(
        "INSERT INTO products (name, category, price, stock_quantity) VALUES (?, ?, ?, ?)",
        PRODUCTS,
    )

    num_customers = len(CUSTOMERS)
    num_products  = len(PRODUCTS)

    # ── Seed orders + order_items ─────────────────────────────────────────────
    random.seed(42)  # reproducible data
    for _ in range(150):  # 150 orders
        customer_id = random.randint(1, num_customers)
        status      = random.choice(ORDER_STATUSES)
        days_ago    = random.randint(1, 365)
        order_date  = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        # Each order has 1–4 different products
        num_items = random.randint(1, 4)
        item_product_ids = random.sample(range(1, num_products + 1), num_items)

        total = 0.0
        items = []
        for pid in item_product_ids:
            qty        = random.randint(1, 3)
            unit_price = PRODUCTS[pid - 1][2]  # price from our list
            total     += qty * unit_price
            items.append((pid, qty, unit_price))

        cursor.execute(
            "INSERT INTO orders (customer_id, status, total_amount, created_at) VALUES (?, ?, ?, ?)",
            (customer_id, status, round(total, 2), order_date),
        )
        order_id = cursor.lastrowid

        cursor.executemany(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            [(order_id, pid, qty, price) for pid, qty, price in items],
        )

    conn.commit()

    # ── Summary ───────────────────────────────────────────────────────────────
    for table in ["customers", "products", "orders", "order_items"]:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<15} {count:>4} rows")

    conn.close()
    print(f"\nDatabase created at: {db_full_path}")


if __name__ == "__main__":
    print("Setting up e-commerce database...")
    seed_database()
    print("Done. You can now run: python main.py")
