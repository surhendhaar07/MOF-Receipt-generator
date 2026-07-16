from flask import Blueprint, render_template, request, jsonify, send_from_directory, send_file, current_app, session, redirect, url_for, flash
import os
import uuid
import datetime
from functools import wraps
from models.database import (
    get_db_connection,
    get_last_receipt_number,
    get_next_receipt_number,
    check_reference_exists,
    insert_receipt,
    search_receipts,
    get_receipt_by_number,
    reset_receipt_counter,
    delete_receipt_by_number,
    clear_all_receipts,
    verify_user,
    create_user,
    delete_user,
    get_all_users,
    change_user_password,
    log_access,
    get_access_logs,
    log_audit,
    get_audit_logs,
    insert_transaction,
    delete_ledger_transaction,
    get_transactions,
    get_balance_summary
)
import base64

from utils.excel_parser import parse_receipt_excel
from utils.num_to_words import amount_to_words_indian
from utils.pdf_generator import generate_pdf_from_html
from utils.zip_creator import create_receipts_zip

def get_image_data_uri(static_path):
    basename = os.path.basename(static_path).lower()
    if basename == "phone_icon.png":
        phone_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%235c1d4a"><path d="M6.62 10.79a15.15 15.15 0 006.59 6.59l2.2-2.2a1 1 0 011.11-.27 11.72 11.72 0 003.7.59 1 1 0 011 1V20a1 1 0 01-1 1A17 17 0 013 4a1 1 0 011-1h3.5a1 1 0 011 1 11.72 11.72 0 00.59 3.7 1 1 0 01-.27 1.1l-2.2 2.2z"/></svg>'
        return f"data:image/svg+xml;utf8,{phone_svg}"
    elif basename == "mail_icon.png":
        mail_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%235c1d4a"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>'
        return f"data:image/svg+xml;utf8,{mail_svg}"

    if not os.path.exists(static_path):
        return ""
    with open(static_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    ext = os.path.splitext(static_path)[1].lower()
    mime = "image/png"
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".gif":
        mime = "image/gif"
    return f"data:{mime};base64,{encoded_string}"

main_bp = Blueprint('main', __name__)

# Temporary batch store for zipping (in-memory dict)
batch_store = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('main.login'))
        if session.get('role') != 'admin':
            return jsonify({'error': 'Unauthorized: Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def receipts_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('main.login'))
        if session.get('role') != 'admin' and not session.get('allow_receipts', 0):
            return jsonify({'error': 'Access Denied: Donation Receipts permission required.'}), 403
        return f(*args, **kwargs)
    return decorated_function

def ledger_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('main.login'))
        if session.get('role') != 'admin' and not session.get('allow_ledger', 0):
            return jsonify({'error': 'Access Denied: Account Ledger permission required.'}), 403
        return f(*args, **kwargs)
    return decorated_function

def edit_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('main.login'))
        if session.get('role') != 'admin' and not session.get('can_edit', 0):
            return jsonify({'error': 'Access Denied: Modify/Edit permissions required.'}), 403
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
@login_required
def index():
    """Renders the modern Bootstrap 5 dashboard."""
    current_year = datetime.date.today().year
    return render_template('index.html', current_year=current_year)

@main_bp.route('/api/tracking-state', methods=['GET'])
@receipts_required
def tracking_state():
    """API endpoint returning the last generated receipt number and today's date."""
    db_path = current_app.config['DATABASE']
    last_num = get_last_receipt_number(db_path)
    current_year = datetime.date.today().year
    last_num_formatted = f"SFDR-{current_year}-{last_num:03d}" if last_num > 0 else f"SFDR-{current_year}-000"
    
    system_date = datetime.date.today().strftime('%d/%m/%Y')
    
    return jsonify({
        'last_number': last_num,
        'last_number_formatted': last_num_formatted,
        'system_date': system_date
    })

@main_bp.route('/api/history', methods=['GET'])
@receipts_required
def history():
    """API endpoint returning a filtered history of receipts."""
    db_path = current_app.config['DATABASE']
    search_term = request.args.get('search', '')
    records = search_receipts(db_path, search_term)
    return jsonify(records)

@main_bp.route('/generate', methods=['POST'])
@receipts_required
@edit_required
def generate():
    """
    Main endpoint for parsing Excel files and generating receipt records/PDFs.
    Checks for duplicate reference numbers.
    """
    db_path = current_app.config['DATABASE']
    uploads_dir = current_app.config['UPLOAD_FOLDER']
    receipts_dir = current_app.config['RECEIPTS_FOLDER']
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        return jsonify({'error': 'Invalid file type. Please upload an Excel spreadsheet (.xlsx or .xls)'}), 400
        
    # Save spreadsheet to uploads folder
    temp_excel_name = f"{uuid.uuid4()}_{file.filename}"
    temp_excel_path = os.path.join(uploads_dir, temp_excel_name)
    file.save(temp_excel_path)
    
    try:
        # Parse Excel records
        records = parse_receipt_excel(temp_excel_path)
    except ValueError as val_err:
        # Cleanup file before returning error
        if os.path.exists(temp_excel_path):
            os.remove(temp_excel_path)
        return jsonify({'error': str(val_err)}), 400
    except Exception as e:
        if os.path.exists(temp_excel_path):
            os.remove(temp_excel_path)
        return jsonify({'error': f"Failed to parse Excel file: {str(e)}"}), 500
        
    # Clean up uploaded Excel file
    if os.path.exists(temp_excel_path):
        os.remove(temp_excel_path)
        
    generated_count = 0
    skipped_duplicates = []
    batch_pdf_paths = []
    pdf_details = []
    
    today_str = datetime.date.today().strftime('%d/%m/%Y')
    
    try:
        for row in records:
            ref_number = row['reference_number']
            
            # Check database duplicate reference
            if check_reference_exists(db_path, ref_number):
                skipped_duplicates.append(ref_number)
                continue
                
            payer_name = row['payer_name']
            amount = row['amount']
            payment_date = row['payment_date']
            event_name = row['event_name']
            
            # Generate the next serial number
            receipt_number = get_next_receipt_number(db_path)
            
            # Format the amount to words (Indian English)
            amount_words = amount_to_words_indian(amount)
            
            # Clean filename to avoid bad characters in filename
            clean_payer_name = "".join(c for c in payer_name if c.isalnum() or c in (' ', '_', '-')).strip()
            pdf_filename = f"{clean_payer_name}.pdf"
            pdf_path = os.path.join(receipts_dir, pdf_filename)
            
            # If file already exists, make filename unique using the receipt number
            if os.path.exists(pdf_path):
                pdf_filename = f"{clean_payer_name}_{receipt_number}.pdf"
                pdf_path = os.path.join(receipts_dir, pdf_filename)
                
            # Render HTML markup to a temporary HTML file for PDF printing
            try:
                static_dir = os.path.abspath(os.path.join(current_app.root_path, 'static'))
                logo_url = get_image_data_uri(os.path.join(static_dir, 'logo.png'))
                stamp_url = get_image_data_uri(os.path.join(static_dir, 'stamp.png'))
                signature_url = get_image_data_uri(os.path.join(static_dir, 'signature.png'))
                phone_icon_url = get_image_data_uri(os.path.join(static_dir, 'phone_icon.png'))
                mail_icon_url = get_image_data_uri(os.path.join(static_dir, 'mail_icon.png'))

                rendered_html = render_template(
                    'receipt.html',
                    payer_name=payer_name,
                    receipt_number=receipt_number,
                    payment_date=payment_date,
                    receipt_date=today_str,
                    amount=f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}",
                    amount_words=amount_words,
                    reference_number=ref_number,
                    event_name=event_name,
                    donor_address=row.get('donor_address', ''),
                    donor_email=row.get('donor_email', ''),
                    donor_mobile=row.get('donor_mobile', ''),
                    donor_pan=row.get('donor_pan', ''),
                    donor_aadhaar=row.get('donor_aadhaar', ''),
                    payment_mode=row.get('payment_mode', 'Online'),
                    logo_url=logo_url,
                    stamp_url=stamp_url,
                    signature_url=signature_url,
                    phone_icon_url=phone_icon_url,
                    mail_icon_url=mail_icon_url
                )
                
                temp_html_path = os.path.join(uploads_dir, f"temp_{receipt_number}.html")
                with open(temp_html_path, 'w', encoding='utf-8') as hf:
                    hf.write(rendered_html)
                    
                # Compile HTML to PDF
                pdf_success = generate_pdf_from_html(temp_html_path, pdf_path)
                
                # Clean up temp html file
                if os.path.exists(temp_html_path):
                    os.remove(temp_html_path)
                    
                if not pdf_success:
                    raise Exception("PDF compilation engine failed.")
                    
            except Exception as pdf_err:
                return jsonify({'error': f"Failed to generate receipt PDF for {payer_name}: {str(pdf_err)}"}), 500
                
            # Record receipt details in SQLite
            db_success = insert_receipt(
                db_path,
                receipt_number=receipt_number,
                payer_name=payer_name,
                payment_date=payment_date,
                receipt_date=today_str,
                amount=amount,
                amount_words=amount_words,
                reference_number=ref_number,
                event_name=event_name,
                pdf_file=pdf_filename,
                donor_address=row.get('donor_address', ''),
                donor_email=row.get('donor_email', ''),
                donor_mobile=row.get('donor_mobile', ''),
                donor_pan=row.get('donor_pan', ''),
                donor_aadhaar=row.get('donor_aadhaar', ''),
                payment_mode=row.get('payment_mode', 'Online')
            )
            
            if db_success:
                generated_count += 1
                batch_pdf_paths.append(pdf_path)
                pdf_details.append({
                    'url': f"/download/pdf/{receipt_number}",
                    'name': pdf_filename
                })
    except Exception as batch_err:
        return jsonify({'error': f"Failed during batch processing: {str(batch_err)}"}), 500
            
    # Save batch items for download ZIP
    batch_id = str(uuid.uuid4())
    if batch_pdf_paths:
        batch_store[batch_id] = batch_pdf_paths
        
    summary_msg = f"Successfully generated {generated_count} receipt(s)."
    if len(skipped_duplicates) > 0:
        summary_msg += f" Skipped {len(skipped_duplicates)} duplicate payment reference(s)."
        
    log_audit(db_path, session['username'], 'generate_receipts', f"Generated {generated_count} receipt(s).")
        
    return jsonify({
        'message': summary_msg,
        'count': generated_count,
        'batch_id': batch_id,
        'skipped_duplicates': skipped_duplicates,
        'pdf_urls': pdf_details
    })

@main_bp.route('/preview/<receipt_number>', methods=['GET'])
@receipts_required
def preview(receipt_number):
    """Renders receipt in HTML format inside browser for previewing."""
    db_path = current_app.config['DATABASE']
    item = get_receipt_by_number(db_path, receipt_number)
    if not item:
        return "Receipt not found.", 404
        
    # Standardize float display
    amount_float = float(item['amount'])
    amount_str = f"{int(amount_float)}" if amount_float.is_integer() else f"{amount_float:.2f}"
    
    static_dir = os.path.abspath(os.path.join(current_app.root_path, 'static'))
    logo_url = get_image_data_uri(os.path.join(static_dir, 'logo.png'))
    stamp_url = get_image_data_uri(os.path.join(static_dir, 'stamp.png'))
    signature_url = get_image_data_uri(os.path.join(static_dir, 'signature.png'))
    phone_icon_url = get_image_data_uri(os.path.join(static_dir, 'phone_icon.png'))
    mail_icon_url = get_image_data_uri(os.path.join(static_dir, 'mail_icon.png'))

    return render_template(
        'receipt.html',
        payer_name=item['payer_name'],
        receipt_number=item['receipt_number'],
        payment_date=item['payment_date'],
        receipt_date=item['receipt_date'],
        amount=amount_str,
        amount_words=item['amount_words'],
        reference_number=item['reference_number'],
        event_name=item['event_name'],
        donor_address=item.get('donor_address') or '',
        donor_email=item.get('donor_email') or '',
        donor_mobile=item.get('donor_mobile') or '',
        donor_pan=item.get('donor_pan') or '',
        donor_aadhaar=item.get('donor_aadhaar') or '',
        payment_mode=item.get('payment_mode') or 'Online',
        logo_url=logo_url,
        stamp_url=stamp_url,
        signature_url=signature_url,
        phone_icon_url=phone_icon_url,
        mail_icon_url=mail_icon_url
    )

@main_bp.route('/download/pdf/<receipt_number>', methods=['GET'])
@receipts_required
def download_pdf(receipt_number):
    """Serves a generated PDF as an attachment."""
    db_path = current_app.config['DATABASE']
    item = get_receipt_by_number(db_path, receipt_number)
    if not item or not item['pdf_file']:
        return "Receipt not found.", 404
        
    receipts_dir = current_app.config['RECEIPTS_FOLDER']
    return send_from_directory(
        receipts_dir,
        item['pdf_file'],
        as_attachment=True
    )

@main_bp.route('/download/zip/<batch_id>', methods=['GET'])
@receipts_required
def download_zip(batch_id):
    """Zips and returns all PDFs in the current upload batch."""
    if batch_id not in batch_store:
        return "Batch not found or expired.", 404
        
    pdf_paths = batch_store[batch_id]
    uploads_dir = current_app.config['UPLOAD_FOLDER']
    
    zip_filename = f"Receipts_{batch_id[:8]}.zip"
    zip_path = os.path.join(uploads_dir, zip_filename)
    
    # Create the ZIP
    success = create_receipts_zip(pdf_paths, zip_path)
    if not success:
        return "Failed to package ZIP archive.", 500
        
    return send_from_directory(
        uploads_dir,
        zip_filename,
        as_attachment=True,
        download_name="Receipts.zip"
    )

@main_bp.route('/admin/reset-counter', methods=['POST'])
@receipts_required
@edit_required
def reset_counter():
    """Resets the serial numbering sequence."""
    db_path = current_app.config['DATABASE']
    data = request.get_json() or {}
    start_val_str = data.get('start_val', '')
    
    try:
        if start_val_str != '':
            start_val = int(start_val_str)
            if start_val < 0:
                return jsonify({'error': 'Start counter value must be non-negative.'}), 400
        else:
            start_val = 0
            
        reset_receipt_counter(db_path, start_val)
        current_year = datetime.date.today().year
        formatted_val = f"SFDR-{current_year}-{start_val:03d}" if start_val > 0 else f"SFDR-{current_year}-000"
        log_audit(db_path, session['username'], 'reset_counter', f"Reset receipt counter start value to {start_val} ({formatted_val}).")
        return jsonify({
            'message': f"Receipt counter successfully reset. The next generated receipt will be formatted as number after {formatted_val}."
        })
    except ValueError:
        return jsonify({'error': 'Invalid integer input for counter value.'}), 400

@main_bp.route('/api/delete-receipt/<receipt_number>', methods=['POST'])
@receipts_required
@edit_required
def delete_receipt(receipt_number):
    """Deletes a particular receipt and removes its PDF file from disk."""
    db_path = current_app.config['DATABASE']
    receipts_dir = current_app.config['RECEIPTS_FOLDER']
    
    item = get_receipt_by_number(db_path, receipt_number)
    if not item:
        return jsonify({'error': 'Receipt not found.'}), 404
        
    # Remove file from disk
    if item['pdf_file']:
        pdf_path = os.path.join(receipts_dir, item['pdf_file'])
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception as file_err:
            print(f"Error removing PDF file {pdf_path}: {file_err}")
            
    # Delete from database
    delete_receipt_by_number(db_path, receipt_number)
    log_audit(db_path, session['username'], 'delete_receipt', f"Deleted receipt {receipt_number} (payer: {item['payer_name']}).")
    
    return jsonify({
        'message': f"Receipt {receipt_number} has been deleted successfully."
    })

@main_bp.route('/admin/clear-history', methods=['POST'])
@receipts_required
@edit_required
def clear_history():
    """Deletes all receipts from the database and removes all generated PDFs from disk."""
    db_path = current_app.config['DATABASE']
    receipts_dir = current_app.config['RECEIPTS_FOLDER']
    
    # Fetch all records to delete their files
    records = search_receipts(db_path)
    
    deleted_files_count = 0
    for record in records:
        if record['pdf_file']:
            pdf_path = os.path.join(receipts_dir, record['pdf_file'])
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    deleted_files_count += 1
            except Exception as file_err:
                print(f"Error removing PDF file {pdf_path}: {file_err}")
                
    # Clear database history
    clear_all_receipts(db_path)
    log_audit(db_path, session['username'], 'clear_history', f"Cleared all receipt records. Deleted {deleted_files_count} PDF file(s).")
    
    return jsonify({
        'message': f"All history logs cleared successfully. Deleted {deleted_files_count} PDF file(s) from storage."
    })


# --- Authentication Routes ---

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        db_path = current_app.config['DATABASE']
        user = verify_user(db_path, username, password)
        if user:
            session['username'] = user['username']
            session['role'] = user['role']
            session['allow_receipts'] = user.get('allow_receipts', 1)
            session['allow_ledger'] = user.get('allow_ledger', 1)
            session['can_edit'] = user.get('can_edit', 1)
            
            ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
            log_access(db_path, user['username'], 'login', ip_addr)
            return redirect(url_for('main.index'))
        else:
            ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
            log_access(db_path, username if username else 'unknown', 'failed_login', ip_addr)
            flash('Invalid username or password', 'danger')
            
    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    username = session.get('username')
    db_path = current_app.config['DATABASE']
    if username:
        ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
        log_access(db_path, username, 'logout', ip_addr)
    session.clear()
    return redirect(url_for('main.login'))


# --- Accounts Ledger API Routes ---

@main_bp.route('/api/balance', methods=['GET'])
@ledger_required
def api_balance():
    db_path = current_app.config['DATABASE']
    summary = get_balance_summary(db_path)
    return jsonify(summary)

@main_bp.route('/api/transactions', methods=['GET', 'POST'])
@ledger_required
def api_transactions():
    db_path = current_app.config['DATABASE']
    
    if request.method == 'GET':
        search = request.args.get('search', '')
        tx_type = request.args.get('type', 'all')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        event_name = request.args.get('event_name', '')
        person_name = request.args.get('person_name', '')
        
        txs = get_transactions(
            db_path,
            search_term=search,
            tx_type=tx_type,
            start_date=start_date,
            end_date=end_date,
            event_name=event_name,
            person_name=person_name
        )
        return jsonify(txs)
        
    elif request.method == 'POST':
        if session.get('role') != 'admin' and not session.get('can_edit', 0):
            return jsonify({'error': 'Access Denied: Modify/Edit permissions required.'}), 403
        data = request.get_json() or {}
        tx_type = data.get('type')
        amount = data.get('amount')
        date_val = data.get('date')
        event_name = data.get('event_name', 'General')
        person_name = data.get('person_name', '')
        remarks = data.get('remarks', '')
        payment_method = data.get('payment_method', 'cash')
        transaction_number = data.get('transaction_number', '')
        
        if not tx_type or tx_type not in ('add', 'remove'):
            return jsonify({'error': 'Invalid transaction type.'}), 400
            
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({'error': 'Amount must be a positive number.'}), 400
            
        if not date_val:
            return jsonify({'error': 'Date is required.'}), 400
            
        try:
            dt = datetime.datetime.strptime(date_val, "%Y-%m-%d")
            formatted_date = dt.strftime("%d/%m/%Y")
        except ValueError:
            formatted_date = date_val
            
        if payment_method not in ('cash', 'upi', 'bank_transfer'):
            payment_method = 'cash'
            
        if payment_method in ('upi', 'bank_transfer') and not transaction_number:
            return jsonify({'error': 'Transaction number is required for UPI or Bank Transfer.'}), 400
            
        created_by = session['username']
        success = insert_transaction(
            db_path,
            tx_type=tx_type,
            amount=amount_float,
            date_str=formatted_date,
            event_name=event_name,
            person_name=person_name,
            remarks=remarks,
            created_by=created_by,
            payment_method=payment_method,
            transaction_number=transaction_number
        )
        
        if success:
            action_desc = f"Added funds: ₹{amount_float:.2f} (from {person_name} for {event_name})" if tx_type == 'add' else f"Removed funds: ₹{amount_float:.2f} (to {person_name} for {event_name})"
            log_audit(db_path, created_by, f"{tx_type}_funds", action_desc)
            return jsonify({'message': 'Transaction recorded successfully.', 'tx_id': success})
            
        return jsonify({'error': 'Failed to record transaction.'}), 500

@main_bp.route('/api/transactions/delete/<int:tx_id>', methods=['POST'])
@ledger_required
@edit_required
def api_delete_transaction(tx_id):
    db_path = current_app.config['DATABASE']
    delete_ledger_transaction(db_path, tx_id)
    log_audit(db_path, session['username'], 'delete_transaction', f"Deleted ledger transaction ID {tx_id}")
    return jsonify({'message': 'Ledger transaction deleted successfully.'})

@main_bp.route('/api/transactions/generate-receipt/<int:tx_id>', methods=['POST'])
@ledger_required
@edit_required
def api_generate_receipt_from_transaction(tx_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized: Admin access required'}), 403
        
    db_path = current_app.config['DATABASE']
    uploads_dir = current_app.config['UPLOAD_FOLDER']
    receipts_dir = current_app.config['RECEIPTS_FOLDER']
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    tx = cursor.fetchone()
    conn.close()
    
    if not tx:
        return jsonify({'error': 'Transaction not found'}), 404
        
    if tx['type'] != 'add':
        return jsonify({'error': 'Receipts can only be generated for Credit (Add Funds) transactions.'}), 400
        
    ref_number = f"{tx['transaction_number']} (LGR-{tx['id']})" if tx['transaction_number'] else f"LGR-{tx['id']}"
    
    if check_reference_exists(db_path, ref_number):
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT receipt_number FROM receipts WHERE reference_number = ?", (ref_number,))
        existing_receipt = cursor.fetchone()
        conn.close()
        if existing_receipt:
            return jsonify({
                'message': 'Receipt already exists for this transaction.',
                'receipt_number': existing_receipt['receipt_number'],
                'url': f"/download/pdf/{existing_receipt['receipt_number']}"
            })
            
    payer_name = tx['person_name'] or 'Anonymous Donor'
    amount = tx['amount']
    payment_date = tx['date']
    event_name = tx['event_name'] or 'General'
    today_str = datetime.date.today().strftime('%d/%m/%Y')
    
    receipt_number = get_next_receipt_number(db_path)
    amount_words = amount_to_words_indian(amount)
    
    clean_payer_name = "".join(c for c in payer_name if c.isalnum() or c in (' ', '_', '-')).strip()
    pdf_filename = f"{clean_payer_name}.pdf"
    pdf_path = os.path.join(receipts_dir, pdf_filename)
    
    if os.path.exists(pdf_path):
        pdf_filename = f"{clean_payer_name}_{receipt_number}.pdf"
        pdf_path = os.path.join(receipts_dir, pdf_filename)
        
    tx_payment_method = tx.get('payment_method') or 'cash'
    payment_mode = 'Cash'
    if tx_payment_method == 'upi':
        payment_mode = 'UPI'
    elif tx_payment_method == 'bank_transfer':
        payment_mode = 'Bank Transfer'

    try:
        static_dir = os.path.abspath(os.path.join(current_app.root_path, 'static'))
        logo_url = get_image_data_uri(os.path.join(static_dir, 'logo.png'))
        stamp_url = get_image_data_uri(os.path.join(static_dir, 'stamp.png'))
        signature_url = get_image_data_uri(os.path.join(static_dir, 'signature.png'))
        phone_icon_url = get_image_data_uri(os.path.join(static_dir, 'phone_icon.png'))
        mail_icon_url = get_image_data_uri(os.path.join(static_dir, 'mail_icon.png'))

        rendered_html = render_template(
            'receipt.html',
            payer_name=payer_name,
            receipt_number=receipt_number,
            payment_date=payment_date,
            receipt_date=today_str,
            amount=f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}",
            amount_words=amount_words,
            reference_number=ref_number,
            event_name=event_name,
            donor_address='',
            donor_email='',
            donor_mobile='',
            donor_pan='',
            donor_aadhaar='',
            payment_mode=payment_mode,
            logo_url=logo_url,
            stamp_url=stamp_url,
            signature_url=signature_url,
            phone_icon_url=phone_icon_url,
            mail_icon_url=mail_icon_url
        )
        
        temp_html_path = os.path.join(uploads_dir, f"temp_{receipt_number}.html")
        with open(temp_html_path, 'w', encoding='utf-8') as hf:
            hf.write(rendered_html)
            
        pdf_success = generate_pdf_from_html(temp_html_path, pdf_path)
        
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)
            
        if not pdf_success:
            raise Exception("PDF compilation engine failed.")
            
    except Exception as pdf_err:
        return jsonify({'error': f"Failed to generate receipt PDF: {str(pdf_err)}"}), 500
        
    db_success = insert_receipt(
        db_path,
        receipt_number=receipt_number,
        payer_name=payer_name,
        payment_date=payment_date,
        receipt_date=today_str,
        amount=amount,
        amount_words=amount_words,
        reference_number=ref_number,
        event_name=event_name,
        pdf_file=pdf_filename,
        donor_address='',
        donor_email='',
        donor_mobile='',
        donor_pan='',
        donor_aadhaar='',
        payment_mode=payment_mode
    )
    
    if db_success:
        log_audit(db_path, session['username'], 'generate_receipt_from_ledger', f"Generated receipt {receipt_number} from ledger transaction ID {tx_id}")
        return jsonify({
            'message': f"Receipt {receipt_number} generated successfully.",
            'receipt_number': receipt_number,
            'url': f"/download/pdf/{receipt_number}"
        })
        
    return jsonify({'error': 'Failed to log receipt to database.'}), 500

@main_bp.route('/api/transactions/export', methods=['GET'])
@ledger_required
def api_export_transactions():
    db_path = current_app.config['DATABASE']
    
    search = request.args.get('search', '')
    tx_type = request.args.get('type', 'all')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    event_name = request.args.get('event_name', '')
    person_name = request.args.get('person_name', '')
    
    txs = get_transactions(
        db_path,
        search_term=search,
        tx_type=tx_type,
        start_date=start_date,
        end_date=end_date,
        event_name=event_name,
        person_name=person_name
    )
    
    import pandas as pd
    import io
    
    data_list = []
    for tx in txs:
        data_list.append({
            'Date': tx['date'],
            'Type': 'Credit' if tx['type'] == 'add' else 'Debit',
            'Amount (₹)': tx['amount'],
            'Event/Purpose': tx['event_name'],
            'Person Name': tx['person_name'] or '',
            'Payment Method': (tx.get('payment_method') or 'cash').upper().replace('_', ' '),
            'Transaction Number': tx.get('transaction_number') or '',
            'Remarks': tx['remarks'] or '',
            'Recorded By': tx['created_by']
        })
        
    df = pd.DataFrame(data_list)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Ledger Transactions')
    output.seek(0)
    
    current_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"ledger_transactions_{current_time}.xlsx"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# --- Admin User Management & Logging APIs ---

@main_bp.route('/api/admin/users', methods=['GET', 'POST'])
@admin_required
def api_admin_users():
    db_path = current_app.config['DATABASE']
    
    if request.method == 'GET':
        users = get_all_users(db_path)
        return jsonify(users)
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        role = data.get('role', 'user')
        
        if not username or len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters.'}), 400
        if not password or len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters.'}), 400
        if role not in ('admin', 'user'):
            return jsonify({'error': 'Invalid role.'}), 400
            
        allow_receipts = data.get('allow_receipts', 1)
        allow_ledger = data.get('allow_ledger', 1)
        can_edit = data.get('can_edit', 1)
            
        success = create_user(db_path, username, password, role, allow_receipts=allow_receipts, allow_ledger=allow_ledger, can_edit=can_edit)
        if success:
            log_audit(db_path, session['username'], 'create_user', f"Created user {username} with role {role} (Permissions - Receipts: {allow_receipts}, Ledger: {allow_ledger}, Edit: {can_edit})")
            return jsonify({'message': f"User '{username}' created successfully."})
        return jsonify({'error': 'Username already exists.'}), 400

@main_bp.route('/api/admin/users/delete/<username>', methods=['POST'])
@admin_required
def api_admin_delete_user(username):
    db_path = current_app.config['DATABASE']
    success, msg = delete_user(db_path, username)
    if success:
        log_audit(db_path, session['username'], 'delete_user', f"Deleted user {username}")
        return jsonify({'message': msg})
    return jsonify({'error': msg}), 400

@main_bp.route('/api/admin/users/update/<int:user_id>', methods=['POST'])
@admin_required
def api_admin_update_user(user_id):
    db_path = current_app.config['DATABASE']
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')  # optional password
    role = data.get('role', 'user')
    allow_receipts = data.get('allow_receipts', 1)
    allow_ledger = data.get('allow_ledger', 1)
    can_edit = data.get('can_edit', 1)
    
    if not username or len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters.'}), 400
    if role not in ('admin', 'user'):
        return jsonify({'error': 'Invalid role.'}), 400
        
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Check if username is already taken by another user
    cursor.execute("SELECT id, username FROM users WHERE username = ? AND id != ?", (username, user_id))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return jsonify({'error': f"Username '{username}' is already taken."}), 400
        
    # Get user details
    cursor.execute("SELECT username, role FROM users WHERE id = ?", (user_id,))
    target_user = cursor.fetchone()
    if not target_user:
        conn.close()
        return jsonify({'error': 'User not found.'}), 404
        
    # Prevent changing role/permissions of the main default 'admin' user
    if target_user['username'] == 'admin':
        if role != 'admin' or not allow_receipts or not allow_ledger or not can_edit:
            conn.close()
            return jsonify({'error': "Cannot restrict or demote the default 'admin' account."}), 400
            
    # Update user details
    cursor.execute("""
        UPDATE users 
        SET username = ?, role = ?, allow_receipts = ?, allow_ledger = ?, can_edit = ?
        WHERE id = ?
    """, (username, role, int(allow_receipts), int(allow_ledger), int(can_edit), user_id))
    
    # Update password if provided
    if password:
        if len(password) < 6:
            conn.close()
            return jsonify({'error': 'Password must be at least 6 characters.'}), 400
        from werkzeug.security import generate_password_hash
        pw_hash = generate_password_hash(password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        
    conn.commit()
    conn.close()
    
    log_audit(db_path, session['username'], 'update_user', f"Updated user ID {user_id} (New Username: {username}, Role: {role}, Receipts: {allow_receipts}, Ledger: {allow_ledger}, Edit: {can_edit})")
    
    # Update session if logged-in user edited themselves
    if target_user['username'] == session.get('username'):
        session['username'] = username
        session['role'] = role
        session['allow_receipts'] = allow_receipts
        session['allow_ledger'] = allow_ledger
        session['can_edit'] = can_edit
        
    return jsonify({'message': f"User '{username}' updated successfully."})

@main_bp.route('/api/admin/logs', methods=['GET'])
@admin_required
def api_admin_logs():
    db_path = current_app.config['DATABASE']
    access = get_access_logs(db_path)
    audit = get_audit_logs(db_path)
    return jsonify({
        'access_logs': access,
        'audit_logs': audit
    })

@main_bp.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    db_path = current_app.config['DATABASE']
    data = request.get_json() or {}
    new_password = data.get('password', '')
    
    if not new_password or len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
        
    change_user_password(db_path, session['username'], new_password)
    log_audit(db_path, session['username'], 'change_password', "Changed account password")
    return jsonify({'message': 'Password updated successfully.'})
