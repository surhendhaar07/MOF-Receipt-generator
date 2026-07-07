# Makkalil Oruvan Foundation Donation Receipt Generator

An automated web application designed to generate official donation receipts from an Excel spreadsheet. This app replicates the official receipt template exactly, fills in dynamic fields, prevents duplicate receipt generation for the same transaction reference, and maintains a persistent receipt serial counter.

## Key Features

1. **Exact Receipt Design Replication**: Replaces only the dynamic fields in the receipt layout. Replicates borders, alignments, logos, official text details, and the founder's signature.
2. **Automated Counter Management**: Stores and increments receipt serial numbers (e.g. `MOFDR011`, `MOFDR012`) permanently using SQLite.
3. **Duplicate Prevention**: Scans each row's payment reference number before generating a PDF. If it exists in the database logs, it skips generation and alerts the user.
4. **Number-to-Words Translation**: Automatic conversion of donation amounts into Indian English format (e.g. Lakhs, Thousands) without commas or hyphens (e.g. `150000` -> `One Lakh Fifty Thousand`).
5. **Interactive Logs**: Search past receipts by Payer Name, Receipt Number, Reference Number, or Date, with options to preview in-browser or download individually.
6. **Batch Downloading**: Download all generated PDFs in a single click using sequential downloading or packaged inside a `.zip` archive.
7. **Admin Settings**: Reset the starting serial number to 0 or any custom starting value via a confirmation dialog.

---

## Installation & Setup

### 1. Prerequisites
- **Python 3.10+** (Python 3.10.8 is confirmed on this system)
- **Web Browser** (Microsoft Edge or Google Chrome are used headlessly on Windows for 100% pixel-perfect PDF rendering)

### 2. Install Dependencies
Open your command terminal in this project folder and run:
```bash
pip install -r requirements.txt
```

---

## Running the Application

Start the local Flask development server:
```bash
python app.py
```

The application will run locally at:
**[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## Input Excel Format

The uploaded Excel sheet must contain a sheet with at least the following 5 columns:
1. **`Payer Name`** (e.g., `Sam F`)
2. **`Payment Date`** (e.g., `19/12/2024`)
3. **`Amount`** (e.g., `1000`)
4. **`Payment Reference Number`** (e.g., `T2412191307576125055498`)
5. **`Event Name`** (e.g., `New Year Dress For Orphan Childrens`)

---

## Code Architecture

- [app.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/app.py): App initialization and Flask dev server start.
- [models/database.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/models/database.py): SQLite helper routines for receipt counter, logging, search, and duplicate check.
- [routes/main.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/routes/main.py): Controller endpoints for page rendering, file upload processing, batch zipping, and API data.
- [utils/excel_parser.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/utils/excel_parser.py): Parsing and structure validation of Excel rows.
- [utils/num_to_words.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/utils/num_to_words.py): Numeric translation to Indian numbering system formatting.
- [utils/pdf_generator.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/utils/pdf_generator.py): High-fidelity PDF generation engine calling headless local browser printing, with standard Python fallbacks.
- [utils/zip_creator.py](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/utils/zip_creator.py): Utility to compress PDF batches.
- [templates/](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/templates/):
  - [index.html](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/templates/index.html): Glassmorphic dark theme dashboard.
  - [receipt.html](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/templates/receipt.html): Precise visual replication of the foundation donation receipt.
- [static/style.css](file:///c:/Users/surhe/OneDrive/Documents/MOF-Receipt-generator/static/style.css): Shared styling for receipt layouts and dashboard panels.
