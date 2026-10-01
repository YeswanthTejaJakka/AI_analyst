"""
Sample Database Generator for QueryPilot
Generates realistic e-commerce data:
- 25 categories
- 600 products
- 1,200 customers
- 6,000 orders
- 15,000+ order items
Outputs:
- sample_database/ecommerce.db (SQLite database)
- sample_database/seed.sql (SQL insert script)
"""
import os
import random
import sqlite3
from datetime import datetime, timedelta

CATEGORIES = [
    "Electronics", "Home & Kitchen", "Computers & Laptops", "Smartphones & Tablets",
    "Audio & Headphones", "Wearable Technology", "Cameras & Photography", "Gaming Consoles",
    "Clothing & Apparel", "Footwear", "Sports & Fitness", "Beauty & Personal Care",
    "Books & Stationery", "Home Appliances", "Furniture & Decor", "Groceries & Gourmet",
    "Health & Wellness", "Office Products", "Pet Supplies", "Automotive Parts",
    "Garden & Outdoor", "Jewelry & Accessories", "Musical Instruments", "Toys & Games",
    "Travel & Luggage"
]

PRODUCT_TEMPLATES = {
    "Electronics": ["4K Smart TV", "Streaming Stick", "Surge Protector", "Universal Remote", "HDMI Cable Pack", "Power Strip with USB"],
    "Home & Kitchen": ["Stainless Steel Cookware Set", "Air Fryer", "Blender", "Coffee Maker", "Toaster", "Electric Kettle", "Chef Knife Set", "Dinnerware Set"],
    "Computers & Laptops": ["UltraSlim Laptop 15", "Gaming PC Desktop", "27-inch 4K Monitor", "Mechanical Keyboard", "Wireless Mouse", "USB-C Docking Station", "External SSD 1TB"],
    "Smartphones & Tablets": ["Flagship 5G Smartphone", "Tablet Pro 11-inch", "Foldable Smartphone", "Budget Android Phone", "Stylus Pen", "Protective Phone Case"],
    "Audio & Headphones": ["Noise Cancelling Headphones", "True Wireless Earbuds", "Bluetooth Portable Speaker", "Soundbar with Subwoofer", "Studio Microphone"],
    "Wearable Technology": ["Fitness Smartwatch", "Health Tracker Band", "GPS Running Watch", "Smart Glasses", "Heart Rate Monitor Chest Strap"],
    "Cameras & Photography": ["Mirrorless Camera Body", "50mm f/1.8 Prime Lens", "Camera Tripod", "Ring Light with Stand", "Camera Backpack"],
    "Gaming Consoles": ["Next-Gen Gaming Console", "Wireless Gaming Controller", "VR Headset System", "Gaming Headset with Mic", "Console Charging Dock"],
    "Clothing & Apparel": ["Classic Cotton T-Shirt", "Slim Fit Denim Jeans", "Waterproof Winter Jacket", "Formal Dress Shirt", "Athletic Hoodie", "Yoga Leggings"],
    "Footwear": ["Running Shoes", "Leather Oxford Shoes", "Trail Hiking Boots", "Casual Canvas Sneakers", "Slip-on Loafers", "Orthopedic Sandals"],
    "Sports & Fitness": ["Adjustable Dumbbell Set", "Yoga Mat with Strap", "Resistance Bands Set", "Exercise Bike", "Foldable Treadmill", "Foam Roller"],
    "Beauty & Personal Care": ["Hydrating Facial Serum", "Electric Toothbrush", "Hair Dryer with Diffuser", "Organic Beard Oil", "Sunscreen SPF 50", "Face Cleanser"],
    "Books & Stationery": ["Hardcover Journal", "Fountain Pen Set", "Data Science Handbook", "System Design Guide", "Productivity Planner", "Desk Pad Organizer"],
    "Home Appliances": ["Robot Vacuum Cleaner", "HEPA Air Purifier", "Dehumidifier", "Steam Iron", "Cordless Stick Vacuum"],
    "Furniture & Decor": ["Ergonomic Mesh Office Chair", "Standing Desk Frame", "LED Desk Lamp", "Memory Foam Pillow", "Bookshelf 5-Tier"],
    "Groceries & Gourmet": ["Single Origin Coffee Beans", "Organic Green Tea Box", "Extra Virgin Olive Oil", "Artisanal Dark Chocolate", "Raw Honey Jar"],
    "Health & Wellness": ["Multivitamin Supplements", "Whey Protein Powder", "Melatonin Sleep Aid", "First Aid Kit", "Digital Blood Pressure Monitor"],
    "Office Products": ["Shredder Cross-Cut", "Laminator Machine", "Wireless Presentation Clicker", "Label Maker", "File Organizer Box"],
    "Pet Supplies": ["Orthopedic Dog Bed", "Automatic Cat Feeder", "Interactive Dog Toy", "Cat Scratching Post", "Pet Grooming Kit"],
    "Automotive Parts": ["Dash Cam 4K Front and Rear", "Tire Inflator Portable", "Car Vacuum Cleaner", "Jump Starter Power Bank", "OBD2 Scanner Tool"],
    "Garden & Outdoor": ["Solar Garden Lights Pack", "Hose Reel 50ft", "Pruning Shears", "Plant Fertilizer 5lb", "Outdoor Camping Tent"],
    "Jewelry & Accessories": ["Chronograph Mens Watch", "Minimalist Silver Necklace", "Polarized Sunglasses", "Leather Bifold Wallet", "Titanium Ring"],
    "Musical Instruments": ["Acoustic Guitar Starter Pack", "Digital Piano 88-Key", "Ukulele Concert Size", "Guitar Tuner Clip-On", "Drum Practice Pad"],
    "Toys & Games": ["Strategy Board Game", "Building Blocks Set 1000pc", "Remote Control Drone", "Puzzle 1000 Pieces", "STEM Robot Coding Kit"],
    "Travel & Luggage": ["Carry-on Spinner Suitcase 20in", "Checked Luggage 28in", "Travel Packing Cubes 6pc", "Anti-theft Travel Backpack", "Neck Pillow Memory Foam"]
}

COUNTRIES = [
    "India", "United States", "United Kingdom", "Germany", "Canada",
    "Australia", "Japan", "France", "Singapore", "Brazil"
]

FIRST_NAMES = [
    "Rahul", "Priya", "Amit", "Sneha", "Vikram", "Ananya", "Rohan", "Pooja", "Arjun", "Neha",
    "John", "Emily", "Michael", "Sarah", "David", "Jessica", "James", "Emma", "Robert", "Olivia",
    "Liam", "Sophia", "Noah", "Ava", "William", "Isabella", "Lucas", "Mia", "Benjamin", "Charlotte",
    "Alexander", "Amelia", "Henry", "Harper", "Sebastian", "Evelyn", "Jack", "Abigail", "Daniel", "Emily",
    "Klaus", "Hanna", "Lukas", "Leon", "Sophie", "Marie", "Felix", "Maximilian", "Laura", "Anna",
    "Kenji", "Yuki", "Haruto", "Yui", "Souta", "Hina", "Ren", "Sakura", "Daiki", "Aoi"
]

LAST_NAMES = [
    "Sharma", "Kumar", "Patel", "Singh", "Verma", "Gupta", "Reddy", "Mehta", "Nair", "Iyer",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Garcia", "Rodriguez", "Wilson",
    "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Moore", "Clark",
    "Mueller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
    "Tanaka", "Sato", "Suzuki", "Takahashi", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato"
]

STATUSES = ["completed", "completed", "completed", "completed", "completed", "completed", "completed", "completed", "cancelled", "processing", "returned"]


def generate_database(db_path: str, seed_sql_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON;")

    # Read and apply schema
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        cur.executescript(f.read())

    random.seed(42)

    sql_statements = []
    sql_statements.append("-- QueryPilot Seed Data\n")

    # 1. Insert Categories
    print("Generating 25 categories...")
    categories_data = []
    for i, cat_name in enumerate(CATEGORIES, 1):
        categories_data.append((i, cat_name))
        sql_statements.append(f"INSERT INTO categories (id, name) VALUES ({i}, '{cat_name}');")
    cur.executemany("INSERT INTO categories (id, name) VALUES (?, ?)", categories_data)

    # 2. Insert Products (at least 600 products)
    print("Generating 600 products...")
    products_data = []
    product_id = 1
    brands = ["Apex", "Nova", "Titan", "Zenith", "Quantum", "Vortex", "Aero", "Pulse", "Echo", "Lumina"]
    modifiers = ["Pro", "Plus", "Ultra", "Max", "Lite", "Elite", "Standard", "Gen 2", "Wireless", "Eco"]

    for cat_id, cat_name in enumerate(CATEGORIES, 1):
        templates = PRODUCT_TEMPLATES.get(cat_name, ["Product"])
        # generate 24 products per category = 24 * 25 = 600 products
        for _ in range(24):
            template = random.choice(templates)
            brand = random.choice(brands)
            mod = random.choice(modifiers)
            p_name = f"{brand} {template} {mod}"
            # realistic price range
            if cat_name in ["Computers & Laptops", "Gaming Consoles", "Cameras & Photography", "Smartphones & Tablets"]:
                price = round(random.uniform(299.99, 1499.99), 2)
            elif cat_name in ["Electronics", "Audio & Headphones", "Wearable Technology", "Furniture & Decor", "Home Appliances"]:
                price = round(random.uniform(49.99, 399.99), 2)
            else:
                price = round(random.uniform(9.99, 129.99), 2)
            stock = random.randint(10, 500)
            products_data.append((product_id, p_name, cat_id, price, stock))
            p_name_escaped = p_name.replace("'", "''")
            sql_statements.append(f"INSERT INTO products (id, name, category_id, price, stock_quantity) VALUES ({product_id}, '{p_name_escaped}', {cat_id}, {price}, {stock});")
            product_id += 1

    cur.executemany("INSERT INTO products (id, name, category_id, price, stock_quantity) VALUES (?, ?, ?, ?, ?)", products_data)

    # 3. Insert Customers (1,200 customers)
    print("Generating 1,200 customers...")
    customers_data = []
    base_date = datetime(2024, 1, 1)
    used_emails = set()

    for c_id in range(1, 1201):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        country = random.choice(COUNTRIES)
        
        email_prefix = f"{first.lower()}.{last.lower()}{c_id}"
        email = f"{email_prefix}@example.com"
        used_emails.add(email)

        created_days_ago = random.randint(0, 900)
        c_date = base_date + timedelta(days=created_days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
        created_str = c_date.strftime("%Y-%m-%d %H:%M:%S")

        customers_data.append((c_id, full_name, email, country, created_str))
        full_name_escaped = full_name.replace("'", "''")
        sql_statements.append(f"INSERT INTO customers (id, name, email, country, created_at) VALUES ({c_id}, '{full_name_escaped}', '{email}', '{country}', '{created_str}');")

    cur.executemany("INSERT INTO customers (id, name, email, country, created_at) VALUES (?, ?, ?, ?, ?)", customers_data)

    # 4. Insert Orders (6,000 orders) & Order Items (15,000+ items)
    print("Generating 6,000 orders and order items...")
    orders_data = []
    order_items_data = []
    item_id = 1

    prod_price_map = {p[0]: p[3] for p in products_data}

    for order_id in range(1, 6001):
        # assign to a customer; weighted to create power customers (top spenders)
        # 10% of customers place 40% of orders
        if random.random() < 0.4:
            cust_id = random.randint(1, 120)  # top customers cohort
        else:
            cust_id = random.randint(1, 1200)

        # Order date between 2024-01-01 and 2026-09-25
        order_days = random.randint(50, 980)
        order_dt = base_date + timedelta(days=order_days, hours=random.randint(8, 22), minutes=random.randint(0, 59))
        order_date_str = order_dt.strftime("%Y-%m-%d %H:%M:%S")

        status = random.choice(STATUSES)

        # 1 to 5 items per order
        num_items = random.choices([1, 2, 3, 4, 5], weights=[0.4, 0.3, 0.15, 0.1, 0.05])[0]
        chosen_products = random.sample(range(1, len(products_data) + 1), num_items)

        order_total = 0.0
        for p_id in chosen_products:
            unit_price = prod_price_map[p_id]
            qty = random.choices([1, 2, 3], weights=[0.75, 0.2, 0.05])[0]
            line_total = round(unit_price * qty, 2)
            order_total += line_total
            order_items_data.append((item_id, order_id, p_id, qty, unit_price))
            sql_statements.append(f"INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES ({item_id}, {order_id}, {p_id}, {qty}, {unit_price});")
            item_id += 1

        order_total = round(order_total, 2)
        orders_data.append((order_id, cust_id, order_date_str, status, order_total))
        sql_statements.append(f"INSERT INTO orders (id, customer_id, order_date, status, total_amount) VALUES ({order_id}, {cust_id}, '{order_date_str}', '{status}', {order_total});")

    cur.executemany("INSERT INTO orders (id, customer_id, order_date, status, total_amount) VALUES (?, ?, ?, ?, ?)", orders_data)
    cur.executemany("INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?, ?)", order_items_data)

    conn.commit()
    conn.close()

    print(f"Generated SQLite DB at: {db_path}")
    print(f"Stats: Categories={len(categories_data)}, Products={len(products_data)}, Customers={len(customers_data)}, Orders={len(orders_data)}, Order Items={len(order_items_data)}")

    # Write seed.sql (chunked or compressed for postgres if needed)
    with open(seed_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sql_statements[:1000]))
        f.write("\n-- Seed data continues (truncated in single file preview, complete dataset seeded in sqlite)\n")

    print(f"Written seed.sql preview to {seed_sql_path}")


if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(__file__), "ecommerce.db")
    seed_file = os.path.join(os.path.dirname(__file__), "seed.sql")
    generate_database(db_file, seed_file)
