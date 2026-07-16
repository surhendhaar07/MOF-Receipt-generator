import subprocess
import os
import sys

def generate_pdf_from_html(html_path, pdf_path):
    """
    Generates a PDF from an HTML file.
    Uses headless Chromium (Edge/Chrome) for 100% layout fidelity if available on Windows.
    Falls back to xhtml2pdf (ReportLab wrapper) if browser execution fails.
    """
    edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    
    # Select available browser
    browser_exe = None
    if os.path.exists(edge_path):
        browser_exe = edge_path
    elif os.path.exists(chrome_path):
        browser_exe = chrome_path
        
    if browser_exe:
        try:
            # Prepare arguments for headless Chromium print
            # --print-to-pdf-no-header disables default page numbers/headers
            cmd = [
                browser_exe,
                '--headless',
                '--disable-gpu',
                '--print-to-pdf-no-header',
                '--no-pdf-header-footer',
                f'--print-to-pdf={os.path.abspath(pdf_path)}',
                os.path.abspath(html_path)
            ]
            
            # Run print command
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                return True
        except Exception as e:
            # Print error to stderr but proceed to fallback
            print(f"Browser PDF generation failed, falling back to xhtml2pdf: {e}", file=sys.stderr)
            
    # Fallback to xhtml2pdf
    try:
        from xhtml2pdf import pisa
        
        def link_callback(uri, rel):
            # Resolve static files to absolute local filesystem paths to avoid deadlocks from loopback HTTP requests
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            static_dir = os.path.join(project_root, 'static')
            
            if '/static/' in uri:
                relative_path = uri.split('/static/', 1)[1].split('?')[0]
                local_path = os.path.normpath(os.path.join(static_dir, relative_path))
                if os.path.exists(local_path):
                    return local_path
            return uri

        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        with open(pdf_path, 'wb') as f:
            pisa_status = pisa.CreatePDF(html_content, dest=f, link_callback=link_callback)
            
        return not pisa_status.err
    except Exception as e:
        print(f"xhtml2pdf PDF generation failed: {e}", file=sys.stderr)
        return False
