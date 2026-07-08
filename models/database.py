import sqlite3
import os

def get_db_connection(db_path):
    """Establishes a connection to the SQLite database with Row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Initializes the database schema and seeds the receipt counter if empty."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Create receipt_counter table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receipt_counter (
            id INTEGER PRIMARY KEY,
            last_number INTEGER
        )
    ''')
    
    # Create receipts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_number TEXT UNIQUE,
            payer_name TEXT,
            payment_date TEXT,
            receipt_date TEXT,
            amount REAL,
            amount_words TEXT,
            reference_number TEXT UNIQUE,
            event_name TEXT,
            pdf_file TEXT
        )
    ''')
    
    # Seed the receipt counter if empty. Seed with 10 so the first generated 
    # receipt is MOFDR011, matching the reference receipt in the example.
    cursor.execute("SELECT COUNT(*) FROM receipt_counter")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO receipt_counter (id, last_number) VALUES (1, 10)")
        
    conn.commit()
    conn.close()

def get_last_receipt_number(db_path):
    """Retrieves the last generated receipt counter value."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT last_number FROM receipt_counter WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['last_number']
    return 0

def get_next_receipt_number(db_path):
    """Increments the counter, saves it, and returns the formatted receipt number (e.g. MOFDR011)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Increment counter
    cursor.execute("UPDATE receipt_counter SET last_number = last_number + 1 WHERE id = 1")
    cursor.execute("SELECT last_number FROM receipt_counter WHERE id = 1")
    last_val = cursor.fetchone()['last_number']
    
    conn.commit()
    conn.close()
    
    return f"MOFDR{last_val:03d}"

def reset_receipt_counter(db_path, reset_value=0):
    """Resets the counter to a specific value (default 0)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE receipt_counter SET last_number = ? WHERE id = 1", (reset_value,))
    conn.commit()
    conn.close()

def check_reference_exists(db_path, reference_number):
    """Checks if a payment reference number is already present in the database."""
    if not reference_number:
        return False
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM receipts WHERE reference_number = ?", (reference_number.strip(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def insert_receipt(db_path, receipt_number, payer_name, payment_date, receipt_date, amount, amount_words, reference_number, event_name, pdf_file):
    """Logs a newly generated receipt into the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO receipts (
                receipt_number, payer_name, payment_date, receipt_date, 
                amount, amount_words, reference_number, event_name, pdf_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            receipt_number, payer_name, payment_date, receipt_date,
            float(amount), amount_words, reference_number.strip() if reference_number else None,
            event_name, pdf_file
        ))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def search_receipts(db_path, search_term=None):
    """
    Searches for receipts matching a search term in columns:
    receipt_number, payer_name, reference_number, payment_date, or receipt_date.
    Returns a list of dicts.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    if search_term:
        term = f"%{search_term.strip()}%"
        cursor.execute('''
            SELECT * FROM receipts 
            WHERE receipt_number LIKE ? 
               OR payer_name LIKE ? 
               OR reference_number LIKE ? 
               OR payment_date LIKE ? 
               OR receipt_date LIKE ?
            ORDER BY id DESC
        ''', (term, term, term, term, term))
    else:
        cursor.execute('SELECT * FROM receipts ORDER BY id DESC')
        
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_receipt_by_number(db_path, receipt_number):
    """Retrieves details of a specific receipt by its serial identifier."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM receipts WHERE receipt_number = ?", (receipt_number,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def delete_receipt_by_number(db_path, receipt_number):
    """Deletes a receipt log record from SQLite."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM receipts WHERE receipt_number = ?", (receipt_number,))
    conn.commit()
    conn.close()

def clear_all_receipts(db_path):
    """Deletes all receipt logs from SQLite."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM receipts")
    conn.commit()
    conn.close()
