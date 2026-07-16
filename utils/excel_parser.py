import pandas as pd
import datetime
import os

def format_date(val):
    """Converts various date representations from Excel into standard DD/MM/YYYY format."""
    if pd.isna(val):
        return ""
        
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime('%d/%m/%Y')
        
    # Strip any string representation
    val_str = str(val).strip()
    
    # Try common formats
    for fmt in ('%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            dt = datetime.datetime.strptime(val_str, fmt)
            return dt.strftime('%d/%m/%Y')
        except ValueError:
            pass
            
    # Try generic pandas datetime conversion
    try:
        dt = pd.to_datetime(val)
        if not pd.isna(dt):
            return dt.strftime('%d/%m/%Y')
    except Exception:
        pass
        
    return val_str

def parse_receipt_excel(file_path):
    """
    Reads and validates an uploaded Excel file.
    Required columns: Payer Name, Payment Date, Amount, Payment Reference Number, Event Name.
    Returns a list of dicts.
    Raises ValueError for schema or validation failures.
    """
    if not os.path.exists(file_path):
        raise ValueError("Excel file does not exist.")
        
    try:
        # Read the Excel sheet (by default first sheet)
        df = pd.read_excel(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {str(e)}")
        
    if df.empty:
        raise ValueError("The uploaded Excel file contains no data.")
        
    # Standardize column headers: strip whitespace
    df.columns = [str(c).strip() for c in df.columns]
    
    required_cols = [
        'Payer Name', 
        'Payment Date', 
        'Amount', 
        'Payment Reference Number', 
        'Event Name'
    ]
    
    # Check for missing columns
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")
        
    records = []
    
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row numbers start at 2 (accounting for header)
        
        payer_name = str(row['Payer Name']).strip() if not pd.isna(row['Payer Name']) else ''
        payment_date = row['Payment Date']
        amount_val = row['Amount']
        ref_num = str(row['Payment Reference Number']).strip() if not pd.isna(row['Payment Reference Number']) else ''
        event_name = str(row['Event Name']).strip() if not pd.isna(row['Event Name']) else ''
        
        # Optional fields from Canva Receipt Template
        donor_address = str(row['Address']).strip() if 'Address' in df.columns and not pd.isna(row['Address']) else ''
        donor_email = str(row['Email']).strip() if 'Email' in df.columns and not pd.isna(row['Email']) else ''
        donor_mobile = str(row['Mobile No']).strip() if 'Mobile No' in df.columns and not pd.isna(row['Mobile No']) else ''
        donor_pan = str(row["Donor's PAN No"]).strip() if "Donor's PAN No" in df.columns and not pd.isna(row["Donor's PAN No"]) else ''
        donor_aadhaar = str(row['Aadhaar No']).strip() if 'Aadhaar No' in df.columns and not pd.isna(row['Aadhaar No']) else ''
        payment_mode = str(row['Payment Mode']).strip() if 'Payment Mode' in df.columns and not pd.isna(row['Payment Mode']) else 'Online'
        
        # Row-level validations
        if not payer_name:
            raise ValueError(f"Row {row_num}: 'Payer Name' cannot be empty.")
            
        if pd.isna(payment_date) or str(payment_date).strip() == '':
            raise ValueError(f"Row {row_num}: 'Payment Date' cannot be empty.")
            
        formatted_pay_date = format_date(payment_date)
        if not formatted_pay_date:
            raise ValueError(f"Row {row_num}: Invalid date format for 'Payment Date'.")
            
        if pd.isna(amount_val):
            raise ValueError(f"Row {row_num}: 'Amount' cannot be empty.")
            
        try:
            amount = float(amount_val)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            raise ValueError(f"Row {row_num}: 'Amount' must be a valid positive number.")
            
        if not ref_num:
            raise ValueError(f"Row {row_num}: 'Payment Reference Number' cannot be empty.")
            
        records.append({
            'payer_name': payer_name,
            'payment_date': formatted_pay_date,
            'amount': amount,
            'reference_number': ref_num,
            'event_name': event_name if event_name else 'Donation',
            'donor_address': donor_address,
            'donor_email': donor_email,
            'donor_mobile': donor_mobile,
            'donor_pan': donor_pan,
            'donor_aadhaar': donor_aadhaar,
            'payment_mode': payment_mode
        })
        
    return records
