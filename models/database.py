import sqlite3
import os
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

def get_db_connection(db_path):
    """Establishes a connection to the SQLite database with Row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Initializes the database schema and seeds the receipt counter/default users if empty."""
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
            pdf_file TEXT,
            donor_address TEXT,
            donor_email TEXT,
            donor_mobile TEXT,
            donor_pan TEXT,
            donor_aadhaar TEXT,
            payment_mode TEXT DEFAULT 'Online'
        )
    ''')

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
            allow_receipts INTEGER DEFAULT 1,
            allow_ledger INTEGER DEFAULT 1,
            can_edit INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Run ALTER TABLE schema migrations dynamically for existing databases
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN allow_receipts INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN allow_ledger INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN can_edit INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT DEFAULT 'cash'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE transactions ADD COLUMN transaction_number TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN donor_address TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN donor_email TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN donor_mobile TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN donor_pan TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN donor_aadhaar TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN payment_mode TEXT DEFAULT 'Online'")
    except sqlite3.OperationalError:
        pass

    # Create access_logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT
        )
    ''')

    # Create audit_logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    ''')

    # Create transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            amount REAL,
            date TEXT,
            event_name TEXT,
            person_name TEXT,
            remarks TEXT,
            created_by TEXT,
            payment_method TEXT DEFAULT 'cash',
            transaction_number TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Seed the receipt counter if empty
    cursor.execute("SELECT COUNT(*) FROM receipt_counter")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO receipt_counter (id, last_number) VALUES (1, 10)")

    # Seed default users if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        admin_hash = generate_password_hash('adminpassword')
        staff_hash = generate_password_hash('staffpassword')
        cursor.execute("INSERT INTO users (username, password_hash, role, allow_receipts, allow_ledger, can_edit) VALUES (?, ?, ?, 1, 1, 1)", ('admin', admin_hash, 'admin'))
        cursor.execute("INSERT INTO users (username, password_hash, role, allow_receipts, allow_ledger, can_edit) VALUES (?, ?, ?, 1, 1, 1)", ('staff', staff_hash, 'user'))
        
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
    """Increments the counter, saves it, and returns the formatted receipt number (e.g. SFDR-{year}-011)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Increment counter
    cursor.execute("UPDATE receipt_counter SET last_number = last_number + 1 WHERE id = 1")
    cursor.execute("SELECT last_number FROM receipt_counter WHERE id = 1")
    last_val = cursor.fetchone()['last_number']
    
    conn.commit()
    conn.close()
    
    current_year = datetime.date.today().year
    return f"SFDR-{current_year}-{last_val:03d}"

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

def insert_receipt(db_path, receipt_number, payer_name, payment_date, receipt_date, amount, amount_words, reference_number, event_name, pdf_file,
                   donor_address='', donor_email='', donor_mobile='', donor_pan='', donor_aadhaar='', payment_mode='Online'):
    """Logs a newly generated receipt into the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO receipts (
                receipt_number, payer_name, payment_date, receipt_date, 
                amount, amount_words, reference_number, event_name, pdf_file,
                donor_address, donor_email, donor_mobile, donor_pan, donor_aadhaar, payment_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            receipt_number, payer_name, payment_date, receipt_date,
            float(amount), amount_words, reference_number.strip() if reference_number else None,
            event_name, pdf_file,
            donor_address, donor_email, donor_mobile, donor_pan, donor_aadhaar, payment_mode
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

# --- User Management Helpers ---
def create_user(db_path, username, password, role='user', allow_receipts=1, allow_ledger=1, can_edit=1):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        pw_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash, role, allow_receipts, allow_ledger, can_edit) VALUES (?, ?, ?, ?, ?, ?)", (username.strip(), pw_hash, role, int(allow_receipts), int(allow_ledger), int(can_edit)))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def verify_user(db_path, username, password):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    if row and check_password_hash(row['password_hash'], password):
        return dict(row)
    return None

def delete_user(db_path, username):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    # Prevent deleting the last admin
    cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if row and row['role'] == 'admin':
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if cursor.fetchone()[0] <= 1:
            conn.close()
            return False, "Cannot delete the last admin user."
            
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True, "User deleted successfully."

def get_all_users(db_path):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, allow_receipts, allow_ledger, can_edit, created_at FROM users ORDER BY username ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def change_user_password(db_path, username, new_password):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    pw_hash = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username))
    conn.commit()
    conn.close()

# --- Activity & Access Logging Helpers ---
def log_access(db_path, username, action, ip_address):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO access_logs (username, action, ip_address) VALUES (?, ?, ?)", (username, action, ip_address))
    conn.commit()
    conn.close()

def get_access_logs(db_path):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT 500")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def log_audit(db_path, username, action, details):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?)", (username, action, details))
    conn.commit()
    conn.close()

def get_audit_logs(db_path):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 500")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# --- Transaction Ledger Helpers ---
def insert_transaction(db_path, tx_type, amount, date_str, event_name, person_name, remarks, created_by, payment_method='cash', transaction_number=None):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO transactions (type, amount, date, event_name, person_name, remarks, created_by, payment_method, transaction_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (tx_type, float(amount), date_str.strip(), event_name.strip(), person_name.strip(), remarks.strip(), created_by, payment_method, transaction_number))
        conn.commit()
        success = cursor.lastrowid
    except Exception:
        success = None
    finally:
        conn.close()
    return success

def delete_ledger_transaction(db_path, tx_id):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()

def get_transactions(db_path, search_term=None, tx_type=None, start_date=None, end_date=None, event_name=None, person_name=None):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    
    if tx_type and tx_type != 'all':
        query += " AND type = ?"
        params.append(tx_type)
        
    if event_name:
        query += " AND event_name LIKE ?"
        params.append(f"%{event_name.strip()}%")
        
    if person_name:
        query += " AND person_name LIKE ?"
        params.append(f"%{person_name.strip()}%")
        
    if search_term:
        query += " AND (event_name LIKE ? OR person_name LIKE ? OR remarks LIKE ? OR created_by LIKE ?)"
        term = f"%{search_term.strip()}%"
        params.extend([term, term, term, term])
        
    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = [dict(row) for row in rows]
    
    # Filter by date range in Python if needed
    if start_date or end_date:
        import datetime
        filtered_results = []
        
        try:
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        except ValueError:
            start_dt = None
            
        try:
            end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        except ValueError:
            end_dt = None
            
        for r in results:
            try:
                # Convert stored date (DD/MM/YYYY) to date object
                r_date = datetime.datetime.strptime(r['date'], "%d/%m/%Y").date()
                if start_dt and r_date < start_dt:
                    continue
                if end_dt and r_date > end_dt:
                    continue
            except ValueError:
                pass
            filtered_results.append(r)
        return filtered_results
        
    return results

def get_balance_summary(db_path):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type = 'add'")
    row_add = cursor.fetchone()
    total_added = row_add[0] if row_add and row_add[0] is not None else 0.0
    
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE type = 'remove'")
    row_rem = cursor.fetchone()
    total_removed = row_rem[0] if row_rem and row_rem[0] is not None else 0.0
    
    conn.close()
    
    return {
        'total_added': total_added,
        'total_removed': total_removed,
        'current_balance': total_added - total_removed
    }
