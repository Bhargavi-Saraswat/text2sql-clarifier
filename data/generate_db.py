"""
Generates a small synthetic e-commerce SQLite database for the
Text-to-SQL + Clarification Engine demo.

Schema is intentionally a bit "realistic and messy" so there's genuine
ambiguity for the clarification engine to catch:
  - orders.status has multiple values (pending/shipped/delivered/cancelled/returned)
  - two date columns on orders (order_date, delivered_date) so "recent" is ambiguous
  - products.category vs products.subcategory
  - customers.region

Run:
    python generate_db.py
Produces: sample.db in this folder.
"""

import os
import random
import sqlite3
from datetime import timedelta

import pandas as pd
from faker import Faker

DB_PATH = os.path.join(os.path.dirname(__file__), "sample.db")

fake = Faker()
Faker.seed(42)
random.seed(42)

SCHEMA = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    region TEXT,           -- 'North', 'South', 'East', 'West'
    signup_date TEXT
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,         -- 'Electronics', 'Apparel', 'Home', 'Books'
    subcategory TEXT,
    unit_price REAL NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    delivered_date TEXT,           -- NULL if not delivered yet
    status TEXT NOT NULL,          -- pending/shipped/delivered/cancelled/returned
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,      -- price at time of order (can differ from products.unit_price)
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
"""

REGIONS = ["North", "South", "East", "West"]
STATUSES = ["pending", "shipped", "delivered", "cancelled", "returned"]
STATUS_WEIGHTS = [0.10, 0.15, 0.55, 0.10, 0.10]

# Product catalog is hand-written (not Faker) since it needs to read like
# real product names, not lorem-ipsum-style filler.
PRODUCT_NAMES = {
    "Phones": ["Galaxy Pulse X", "Nova Phone 12", "Orbit Lite", "Zenith Pro"],
    "Laptops": ["AeroBook 14", "ThinkLine Slim", "PixelBook Air", "CoreMax 5"],
    "Audio": ["BassBuds Pro", "EchoPods", "SoundWave 2", "AirTune Mini"],
    "Accessories": ["FastCharge 65W", "GripCase", "ScreenShield", "CarryPouch"],
    "Men": ["Classic Tee", "Denim Fit Jeans", "Bomber Jacket", "Chino Trousers"],
    "Women": ["Wrap Dress", "High-Rise Jeans", "Knit Cardigan", "Linen Top"],
    "Kids": ["Graphic Tee Jr", "Cargo Shorts Jr", "Rain Jacket Jr", "Sneakers Jr"],
    "Kitchen": ["Non-Stick Pan Set", "Blender Max", "Cutlery Set", "Air Fryer"],
    "Furniture": ["Study Desk", "Bookshelf 5-Tier", "Bean Bag", "Bar Stool"],
    "Decor": ["Wall Clock", "Table Lamp", "Photo Frame Set", "Wall Art Canvas"],
    "Fiction": ["The Silent Orbit", "Paper Lanterns", "Midnight Ledger", "River of Ash"],
    "Non-Fiction": ["Deep Focus", "The Habit Code", "Quiet Ambition", "Systems First"],
    "Comics": ["Ironclad Vol.1", "Skybound Saga", "Nightfall Chronicles", "Pixel Heroes"],
}
CATEGORIES = {
    "Electronics": ["Phones", "Laptops", "Audio", "Accessories"],
    "Apparel": ["Men", "Women", "Kids"],
    "Home": ["Kitchen", "Furniture", "Decor"],
    "Books": ["Fiction", "Non-Fiction", "Comics"],
}


def make_customers(n: int) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "customer_id": i,
            "name": fake.name(),
            "email": fake.unique.email(),
            "region": random.choice(REGIONS),
            "signup_date": fake.date_between("-3y", "-3m").isoformat(),
        }
        for i in range(1, n + 1)
    ])


def make_products() -> pd.DataFrame:
    rows = [
        {
            "product_id": pid,
            "name": name,
            "category": category,
            "subcategory": sub,
            "unit_price": round(random.uniform(8, 1500), 2),
        }
        for category, subs in CATEGORIES.items()
        for sub in subs
        for pid, name in enumerate(PRODUCT_NAMES[sub], start=1)
    ]
    # re-number product_id sequentially across the whole catalog
    for i, row in enumerate(rows, start=1):
        row["product_id"] = i
    return pd.DataFrame(rows)


def make_orders_and_items(n_orders: int, customers: pd.DataFrame, products: pd.DataFrame):
    orders, items = [], []
    item_id = 1
    for order_id in range(1, n_orders + 1):
        customer_id = random.choice(customers["customer_id"].tolist())
        order_date = fake.date_between("-2y", "today")
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        delivered_date = None
        if status in ("delivered", "returned"):
            delivered_date = (order_date + timedelta(days=random.randint(2, 12))).isoformat()
        orders.append({
            "order_id": order_id,
            "customer_id": customer_id,
            "order_date": order_date.isoformat(),
            "delivered_date": delivered_date,
            "status": status,
        })

        for _, product in products.sample(n=random.randint(1, 4)).iterrows():
            items.append({
                "order_item_id": item_id,
                "order_id": order_id,
                "product_id": product["product_id"],
                "quantity": random.randint(1, 3),
                "unit_price": product["unit_price"],
            })
            item_id += 1

    return pd.DataFrame(orders), pd.DataFrame(items)


def generate():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    customers = make_customers(120)
    products = make_products()
    orders, items = make_orders_and_items(600, customers, products)

    for table, df in [("customers", customers), ("products", products),
                       ("orders", orders), ("order_items", items)]:
        df.to_sql(table, conn, if_exists="append", index=False)

    conn.commit()
    conn.close()
    print(f"Created {DB_PATH}")
    print(f"  customers: {len(customers)}, products: {len(products)}, "
          f"orders: {len(orders)}, order_items: {len(items)}")


if __name__ == "__main__":
    generate()
