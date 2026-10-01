# QueryPilot Sample E-Commerce Database

This directory contains the preconfigured, realistic e-commerce database used for **Mode A (Built-in Sample Database)** in QueryPilot.

## Schema Overview

- **`categories`** (25 categories)
  - `id`: INTEGER PRIMARY KEY
  - `name`: VARCHAR(100) UNIQUE (e.g., Electronics, Home & Kitchen, Books)

- **`products`** (600 products)
  - `id`: INTEGER PRIMARY KEY
  - `name`: VARCHAR(255)
  - `category_id`: INTEGER REFERENCES `categories(id)`
  - `price`: NUMERIC(10, 2)
  - `stock_quantity`: INTEGER

- **`customers`** (1,200 customers)
  - `id`: INTEGER PRIMARY KEY
  - `name`: VARCHAR(255)
  - `email`: VARCHAR(255) UNIQUE
  - `country`: VARCHAR(100) (India, United States, Germany, Japan, etc.)
  - `created_at`: TIMESTAMP

- **`orders`** (6,000 orders)
  - `id`: INTEGER PRIMARY KEY
  - `customer_id`: INTEGER REFERENCES `customers(id)`
  - `order_date`: TIMESTAMP (2024 to 2026)
  - `status`: VARCHAR(50) (`completed`, `cancelled`, `processing`, `returned`)
  - `total_amount`: NUMERIC(10, 2)

- **`order_items`** (15,000+ line items)
  - `id`: INTEGER PRIMARY KEY
  - `order_id`: INTEGER REFERENCES `orders(id)`
  - `product_id`: INTEGER REFERENCES `products(id)`
  - `quantity`: INTEGER
  - `unit_price`: NUMERIC(10, 2)

## Relationships

```
customers (1) ───< (N) orders (1) ───< (N) order_items (N) >─── (1) products (N) >─── (1) categories
```

## Regeneration

To regenerate `ecommerce.db`:
```bash
python generate_data.py
```
