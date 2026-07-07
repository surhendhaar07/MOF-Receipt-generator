from flask import Blueprint, render_template, request, jsonify, send_from_directory, current_app
import os
import uuid
import datetime
from models.database import (
    get_last_receipt_number,
    get_next_receipt_number,
    check_reference_exists,
    insert_receipt,
    search_receipts,
    get_receipt_by_number,
    reset_receipt_counter,
    delete_receipt_by_number,
    clear_all_receipts
)
from utils.excel_parser import parse_receipt_excel
from utils.num_to_words import amount_to_words_indian
from utils.pdf_generator import generate_pdf_from_html
from utils.zip_creator import create_receipts_zip

main_bp = Blueprint('main', __name__)

# Temporary batch store for zipping (in-memory dict)
batch_store = {}

@main_bp.route('/')
def index():
    """Renders the modern Bootstrap 5 dashboard."""
    return render_template('index.html')

@main_bp.route('/api/tracking-state', methods=['GET'])
def tracking_state():
    """API endpoint returning the last generated receipt number and today's date."""
    db_path = current_app.config['DATABASE']
    last_num = get_last_receipt_number(db_path)
    last_num_formatted = f"MOFDR{last_num:03d}" if last_num > 0 else "MOFDR000"
    
    system_date = datetime.date.today().strftime('%d/%m/%Y')
    
    return jsonify({
        'last_number': last_num,
        'last_number_formatted': last_num_formatted,
        'system_date': system_date
    })

@main_bp.route('/api/history', methods=['GET'])
def history():
    """API endpoint returning a filtered history of receipts."""
    db_path = current_app.config['DATABASE']
    search_term = request.args.get('search', '')
    records = search_receipts(db_path, search_term)
    return jsonify(records)

@main_bp.route('/generate', methods=['POST'])
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
                rendered_html = render_template(
                    'receipt.html',
                    payer_name=payer_name,
                    receipt_number=receipt_number,
                    payment_date=payment_date,
                    receipt_date=today_str,
                    amount=f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}",
                    amount_words=amount_words,
                    reference_number=ref_number,
                    event_name=event_name
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
                pdf_file=pdf_filename
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
        
    return jsonify({
        'message': summary_msg,
        'count': generated_count,
        'batch_id': batch_id,
        'skipped_duplicates': skipped_duplicates,
        'pdf_urls': pdf_details
    })

@main_bp.route('/preview/<receipt_number>', methods=['GET'])
def preview(receipt_number):
    """Renders receipt in HTML format inside browser for previewing."""
    db_path = current_app.config['DATABASE']
    item = get_receipt_by_number(db_path, receipt_number)
    if not item:
        return "Receipt not found.", 404
        
    # Standardize float display
    amount_float = float(item['amount'])
    amount_str = f"{int(amount_float)}" if amount_float.is_integer() else f"{amount_float:.2f}"
    
    return render_template(
        'receipt.html',
        payer_name=item['payer_name'],
        receipt_number=item['receipt_number'],
        payment_date=item['payment_date'],
        receipt_date=item['receipt_date'],
        amount=amount_str,
        amount_words=item['amount_words'],
        reference_number=item['reference_number'],
        event_name=item['event_name']
    )

@main_bp.route('/download/pdf/<receipt_number>', methods=['GET'])
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
        formatted_val = f"MOFDR{start_val:03d}" if start_val > 0 else "MOFDR000"
        return jsonify({
            'message': f"Receipt counter successfully reset. The next generated receipt will be formatted as number after {formatted_val}."
        })
    except ValueError:
        return jsonify({'error': 'Invalid integer input for counter value.'}), 400

@main_bp.route('/api/delete-receipt/<receipt_number>', methods=['POST'])
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
    
    return jsonify({
        'message': f"Receipt {receipt_number} has been deleted successfully."
    })

@main_bp.route('/admin/clear-history', methods=['POST'])
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
    
    return jsonify({
        'message': f"All history logs cleared successfully. Deleted {deleted_files_count} PDF file(s) from storage."
    })
