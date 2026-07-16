import zipfile
import os
import sys

def create_receipts_zip(pdf_paths, zip_out_path):
    """
    Compresses a list of PDF file paths into a single ZIP archive.
    Saves the ZIP file at zip_out_path.
    Returns True if successful, False otherwise.
    """
    try:
        # Resolve absolute paths and remove duplicates
        unique_paths = list(set([os.path.abspath(p) for p in pdf_paths]))
        
        with zipfile.ZipFile(zip_out_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for pdf_path in unique_paths:
                if os.path.exists(pdf_path):
                    # Add file to zip using only its filename to avoid directory nesting inside the zip
                    arcname = os.path.basename(pdf_path)
                    zipf.write(pdf_path, arcname=arcname)
                    
        return os.path.exists(zip_out_path) and os.path.getsize(zip_out_path) > 0
    except Exception as e:
        print(f"Failed to create ZIP file {zip_out_path}: {e}", file=sys.stderr)
        return False
