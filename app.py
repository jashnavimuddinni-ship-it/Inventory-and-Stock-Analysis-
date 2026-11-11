
from flask import Flask, jsonify, request, send_file
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mysql.connector
from io import BytesIO

app = Flask(__name__)

def fetch_all(sql, params=()):
    db = config.connect()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        db.close()


def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute_query(sql, params=()):
    db = config.connect()
    cursor = db.cursor()
    try:
        cursor.execute(sql, params)
        db.commit()
        return cursor.lastrowid, cursor.rowcount
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()


def error_response(message, status=400):
    return jsonify({"error": message}), status


def apply_stock_change(cursor, product_id, transaction_type, quantity):
    """Apply or reverse a stock transaction."""
    change = quantity if transaction_type == "STOCK_IN" else -quantity

    cursor.execute(
        "SELECT quantity FROM products WHERE product_id = %s FOR UPDATE",
        (product_id,)
    )
    product = cursor.fetchone()

    if product is None:
        raise ValueError("Product not found")

    new_quantity = product[0] + change

    if new_quantity < 0:
        raise ValueError("Insufficient stock for this transaction")

    cursor.execute(
        "UPDATE products SET quantity = %s WHERE product_id = %s",
        (new_quantity, product_id)
    )


import config


# -------------------- HOME --------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "StockSense Inventory Management API",
        "status": "running"
    })
@app.route("/products", methods=["GET"])
def get_products():
    products = fetch_all("""
        SELECT * FROM products
        ORDER BY product_id 
    """)
    return jsonify(products)


@app.route("/products", methods=["POST"])
def add_product():
    data = request.get_json(silent=True) or {}

    required = [
        "product_name", "category", "unit_cost", "selling_price"
    ]

    if any(data.get(field) is None for field in required):
        return error_response("Provide product_name, category, unit_cost and selling_price")

    try:
        product_id, _ = execute_query("""
            INSERT INTO products
            (product_name, category, unit_cost, selling_price,
             quantity, reorder_level, supplier_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data["product_name"],
            data["category"],
            data["unit_cost"],
            data["selling_price"],
            data.get("quantity", 0),
            data.get("reorder_level", 10),
            data.get("supplier_id")
        ))

        return jsonify({
            "message": "Product added successfully",
            "product_id": product_id
        }), 201

    except (ValueError, TypeError) as exc:
        return error_response(str(exc))


@app.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = fetch_one(
        "SELECT * FROM products WHERE product_id = %s",
        (product_id,)
    )

    if not product:
        return error_response("Product not found", 404)

    return jsonify(product)


@app.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    data = request.get_json(silent=True) or {}

    allowed = {
        "product_name", "category", "unit_cost",
        "selling_price", "reorder_level", "supplier_id"
    }

    updates = {key: value for key, value in data.items() if key in allowed}

    if not updates:
        return error_response("Provide at least one valid field to update")

    if not fetch_one(
        "SELECT product_id FROM products WHERE product_id = %s",
        (product_id,)
    ):
        return error_response("Product not found", 404)

    columns = ", ".join(f"{column} = %s" for column in updates)
    values = list(updates.values()) + [product_id]

    execute_query(
        f"UPDATE products SET {columns} WHERE product_id = %s",
        values
    )

    return jsonify({"message": "Product updated successfully"})


@app.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    try:
        _, affected = execute_query(
            "DELETE FROM products WHERE product_id = %s",
            (product_id,)
        )

        if affected == 0:
            return error_response("Product not found", 404)

        return jsonify({"message": "Product deleted successfully"})

    except mysql.connector.Error:
        return error_response(
            "Cannot delete this product. It may have related stock transactions.",
            409
        )
@app.route("/suppliers", methods=["GET"])
def get_suppliers():
    return jsonify(fetch_all("""
        SELECT * FROM suppliers
        ORDER BY supplier_id DESC
    """))


@app.route("/suppliers", methods=["POST"])
def add_supplier():
    data = request.get_json(silent=True) or {}

    if not data.get("supplier_name"):
        return error_response("supplier_name is required")

    supplier_id, _ = execute_query("""
        INSERT INTO suppliers
        (supplier_name, contact_person, phone, email, address)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        data["supplier_name"],
        data.get("contact_person"),
        data.get("phone"),
        data.get("email"),
        data.get("address")
    ))

    return jsonify({
        "message": "Supplier added successfully",
        "supplier_id": supplier_id
    }), 201


@app.route("/suppliers/<int:supplier_id>", methods=["GET"])
def get_supplier(supplier_id):
    supplier = fetch_one(
        "SELECT * FROM suppliers WHERE supplier_id = %s",
        (supplier_id,)
    )

    if not supplier:
        return error_response("Supplier not found", 404)

    return jsonify(supplier)


@app.route("/suppliers/<int:supplier_id>", methods=["PUT"])
def update_supplier(supplier_id):
    data = request.get_json(silent=True) or {}

    allowed = {
        "supplier_name", "contact_person", "phone", "email", "address"
    }
    updates = {key: value for key, value in data.items() if key in allowed}

    if not updates:
        return error_response("Provide at least one valid field to update")

    if not fetch_one(
        "SELECT supplier_id FROM suppliers WHERE supplier_id = %s",
        (supplier_id,)
    ):
        return error_response("Supplier not found", 404)

    columns = ", ".join(f"{column} = %s" for column in updates)
    execute_query(
        f"UPDATE suppliers SET {columns} WHERE supplier_id = %s",
        list(updates.values()) + [supplier_id]
    )

    return jsonify({"message": "Supplier updated successfully"})


@app.route("/suppliers/<int:supplier_id>", methods=["DELETE"])
def delete_supplier(supplier_id):
    try:
        _, affected = execute_query(
            "DELETE FROM suppliers WHERE supplier_id = %s",
            (supplier_id,)
        )

        if affected == 0:
            return error_response("Supplier not found", 404)

        return jsonify({"message": "Supplier deleted successfully"})

    except mysql.connector.Error:
        return error_response(
            "Cannot delete this supplier because it may be linked to products.",
            409
        )
@app.route("/stock-transactions", methods=["GET"])
@app.route("/transactions", methods=["GET"])
def get_transactions():
    transactions = fetch_all("""
        SELECT st.*, p.product_name
        FROM stock_transactions st
        JOIN products p ON st.product_id = p.product_id
        ORDER BY st.transaction_date DESC, st.transaction_id DESC
    """)
    return jsonify(transactions)


@app.route("/stock-transactions", methods=["POST"])
@app.route("/transactions", methods=["POST"])
def add_transaction():
    data = request.get_json(silent=True) or {}

    required = ["product_id", "transaction_type", "quantity", "unit_price"]
    if any(data.get(field) is None for field in required):
        return error_response("Provide product_id, transaction_type, quantity and unit_price")

    transaction_type = data["transaction_type"]
    if transaction_type not in ("STOCK_IN", "STOCK_OUT"):
        return error_response("transaction_type must be STOCK_IN or STOCK_OUT")

    try:
        quantity = int(data["quantity"])
        if quantity <= 0:
            return error_response("quantity must be greater than zero")

        db = config.connect()
        cursor = db.cursor()

        try:
            apply_stock_change(
                cursor, int(data["product_id"]), transaction_type, quantity
            )

            cursor.execute("""
                INSERT INTO stock_transactions
                (product_id, transaction_type, quantity, unit_price, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                int(data["product_id"]),
                transaction_type,
                quantity,
                data["unit_price"],
                data.get("notes")
            ))

            transaction_id = cursor.lastrowid
            db.commit()

            return jsonify({
                "message": "Stock transaction recorded",
                "transaction_id": transaction_id
            }), 201

        except Exception:
            db.rollback()
            raise
        finally:
            cursor.close()
            db.close()

    except ValueError as exc:
        return error_response(str(exc))
    except (TypeError, mysql.connector.Error) as exc:
        return error_response(str(exc))


@app.route("/stock-transactions/<int:transaction_id>", methods=["GET"])
def get_transaction(transaction_id):
    transaction = fetch_one("""
        SELECT st.*, p.product_name
        FROM stock_transactions st
        JOIN products p ON st.product_id = p.product_id
        WHERE st.transaction_id = %s
    """, (transaction_id,))

    if not transaction:
        return error_response("Transaction not found", 404)

    return jsonify(transaction)


@app.route("/stock-transactions/<int:transaction_id>", methods=["DELETE"])
def delete_transaction(transaction_id):
    db = config.connect()
    cursor = db.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM stock_transactions
            WHERE transaction_id = %s FOR UPDATE
        """, (transaction_id,))
        transaction = cursor.fetchone()

        if not transaction:
            return error_response("Transaction not found", 404)
        reverse_type = (
            "STOCK_OUT"
            if transaction["transaction_type"] == "STOCK_IN"
            else "STOCK_IN"
        )

        apply_stock_change(
            cursor,
            transaction["product_id"],
            reverse_type,
            transaction["quantity"]
        )

        cursor.execute(
            "DELETE FROM stock_transactions WHERE transaction_id = %s",
            (transaction_id,)
        )

        db.commit()
        return jsonify({"message": "Transaction deleted and stock adjusted"})

    except ValueError as exc:
        db.rollback()
        return error_response(str(exc))
    except mysql.connector.Error as exc:
        db.rollback()
        return error_response(str(exc), 500)
    finally:
        cursor.close()
        db.close()
@app.route("/low-stock", methods=["GET"])
@app.route("/reports/low-stock", methods=["GET"])
def low_stock():
    products = fetch_all("""
        SELECT product_id, product_name, category, quantity, reorder_level
        FROM products
        WHERE quantity <= reorder_level
        ORDER BY quantity ASC
    """)
    return jsonify(products)
@app.route("/reports/current-stock", methods=["GET"])
def current_stock():
    return jsonify(fetch_all("""
        SELECT product_id, product_name, category, quantity, reorder_level
        FROM products
        ORDER BY product_name
    """))
@app.route("/reports/inventory-value", methods=["GET"])
def inventory_value():
    result = fetch_one("""
        SELECT
            COUNT(*) AS total_products,
            COALESCE(SUM(quantity), 0) AS total_stock_units,
            COALESCE(SUM(quantity * unit_cost), 0) AS inventory_cost,
            COALESCE(SUM(quantity * selling_price), 0) AS potential_sales_value
        FROM products
    """)

    return jsonify(result)
@app.route("/analytics/movement-summary", methods=["GET"])
def movement_summary():
    rows = fetch_all("""
        SELECT
            p.product_id,
            p.product_name,
            COALESCE(SUM(
                CASE WHEN st.transaction_type = 'STOCK_IN'
                THEN st.quantity ELSE 0 END
            ), 0) AS total_stock_in,
            COALESCE(SUM(
                CASE WHEN st.transaction_type = 'STOCK_OUT'
                THEN st.quantity ELSE 0 END
            ), 0) AS total_stock_out
        FROM products p
        LEFT JOIN stock_transactions st ON p.product_id = st.product_id
        GROUP BY p.product_id, p.product_name
        ORDER BY p.product_name
    """)
    for row in rows:
        row["net_movement"] = (
            row["total_stock_in"] - row["total_stock_out"]
        )

    return jsonify(rows)
@app.route("/analytics/fast-moving", methods=["GET"])
def fast_moving():
    rows = fetch_all("""
        SELECT
            p.product_id,
            p.product_name,
            COALESCE(SUM(st.quantity), 0) AS total_units_moved
        FROM products p
        LEFT JOIN stock_transactions st ON p.product_id = st.product_id
        GROUP BY p.product_id, p.product_name
        ORDER BY total_units_moved DESC
    """)
    return jsonify(rows)
@app.route("/analytics/trends", methods=["GET"])
def movement_trends():
    rows = fetch_all("""
        SELECT
            DATE(transaction_date) AS movement_date,
            transaction_type,
            SUM(quantity) AS total_quantity
        FROM stock_transactions
        GROUP BY DATE(transaction_date), transaction_type
        ORDER BY movement_date
    """)

    for row in rows:
        if row["movement_date"] is not None:
            row["movement_date"] = row["movement_date"].isoformat()
# ----------------charts-------------------------------------------
    return jsonify(rows)
def chart_response():
    image_buffer = BytesIO()
    plt.tight_layout()
    plt.savefig(image_buffer, format="png", bbox_inches="tight")
    image_buffer.seek(0)
    plt.close()
    return send_file(image_buffer, mimetype="image/png")
@app.route("/charts/stock-levels", methods=["GET"])
def stock_levels_chart():
    rows = fetch_all("""
        SELECT product_name, quantity
        FROM products
        ORDER BY product_name
    """)

    names = [row["product_name"] for row in rows]
    quantities = [row["quantity"] for row in rows]

    plt.figure(figsize=(10, 5))
    plt.bar(names, quantities)
    plt.title("Current Stock Levels")
    plt.xlabel("Product")
    plt.ylabel("Quantity")
    plt.xticks(rotation=45, ha="right")

    return chart_response()


@app.route("/charts/product-movement", methods=["GET"])
def product_movement_chart():
    rows = fetch_all("""
        SELECT
            p.product_name,
            COALESCE(SUM(
                CASE WHEN st.transaction_type = 'STOCK_IN'
                THEN st.quantity ELSE 0 END
            ), 0) AS stock_in,
            COALESCE(SUM(
                CASE WHEN st.transaction_type = 'STOCK_OUT'
                THEN st.quantity ELSE 0 END
            ), 0) AS stock_out
        FROM products p
        LEFT JOIN stock_transactions st ON p.product_id = st.product_id
        GROUP BY p.product_id, p.product_name
        ORDER BY p.product_name
    """)

    names = [row["product_name"] for row in rows]
    stock_in = [row["stock_in"] for row in rows]
    stock_out = [row["stock_out"] for row in rows]

    positions = list(range(len(names)))
    width = 0.4

    plt.figure(figsize=(10, 5))
    plt.bar(
        [position - width / 2 for position in positions],
        stock_in, width, label="Stock In"
    )
    plt.bar(
        [position + width / 2 for position in positions],
        stock_out, width, label="Stock Out"
    )

    plt.xticks(positions, names, rotation=45, ha="right")
    plt.title("Product Stock Movement")
    plt.xlabel("Product")
    plt.ylabel("Quantity")
    plt.legend()

    return chart_response()


# -------------------- NUMPY AND PANDAS ANALYTICS (ADDED) --------------------
# These are additional endpoints. Existing routes above are left unchanged.

import numpy as np
import pandas as pd


@app.route("/analytics/movement-summary-pandas", methods=["GET"])
def movement_summary_pandas():
    """Return product stock movement summary using Pandas."""
    rows = fetch_all("""
        SELECT
            p.product_id,
            p.product_name,
            COALESCE(SUM(
                CASE WHEN st.transaction_type = 'STOCK_IN'
                THEN st.quantity ELSE 0 END
            ), 0) AS total_stock_in,
            COALESCE(SUM(
                CASE WHEN st.transaction_type = 'STOCK_OUT'
                THEN st.quantity ELSE 0 END
            ), 0) AS total_stock_out
        FROM products p
        LEFT JOIN stock_transactions st ON p.product_id = st.product_id
        GROUP BY p.product_id, p.product_name
        ORDER BY p.product_name
    """)

    df = pd.DataFrame(rows)
    if df.empty:
        return jsonify([])

    df["net_movement"] = df["total_stock_in"] - df["total_stock_out"]
    return jsonify(df.to_dict(orient="records"))


@app.route("/analytics/inventory-valuation-numpy", methods=["GET"])
def inventory_valuation_numpy():
    """Calculate inventory valuation using NumPy arrays."""
    rows = fetch_all("""
        SELECT product_id, product_name, quantity, unit_cost, selling_price
        FROM products
        ORDER BY product_name
    """)

    if not rows:
        return jsonify({
            "products": [],
            "total_inventory_cost": 0.0,
            "total_potential_sales_value": 0.0
        })

    quantities = np.array([float(row["quantity"] or 0) for row in rows], dtype=float)
    unit_costs = np.array([float(row["unit_cost"] or 0) for row in rows], dtype=float)
    selling_prices = np.array([float(row["selling_price"] or 0) for row in rows], dtype=float)

    inventory_costs = quantities * unit_costs
    sales_values = quantities * selling_prices

    products = []
    for index, row in enumerate(rows):
        products.append({
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "quantity": float(quantities[index]),
            "inventory_cost": round(float(inventory_costs[index]), 2),
            "potential_sales_value": round(float(sales_values[index]), 2)
        })

    return jsonify({
        "products": products,
        "total_inventory_cost": round(float(np.sum(inventory_costs)), 2),
        "total_potential_sales_value": round(float(np.sum(sales_values)), 2)
    })


if __name__ == "__main__":
    app.run(debug=True)
