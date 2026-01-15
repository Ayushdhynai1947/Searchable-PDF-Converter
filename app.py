# app.py - Flask API for Searchable PDF Conversion (OPTIMIZED)
# Run with: python app.py
# API endpoint: http://localhost:5008/api/convert

import os
import logging
from pathlib import Path
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
import io
from PIL import Image
import fitz  # PyMuPDF - No Poppler needed!
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from PyPDF2 import PdfReader, PdfWriter

# Surya imports
from surya.foundation import FoundationPredictor
from surya.recognition import RecognitionPredictor
from surya.detection import DetectionPredictor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create necessary folders
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)
Path('temp_images').mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'tif', 'bmp'}


# ===================================================================
# SEARCHABLE DOCUMENT CONVERTER CLASS
# ===================================================================

class SearchableDocumentConverter:
    """
    Universal converter for making documents searchable
    Supports: PDF, PNG, JPG, JPEG, TIFF
    """

    def __init__(self):
        """Initialize Surya OCR models"""
        logger.info("🔄 Loading Surya OCR models...")
        self.foundation_predictor = FoundationPredictor()
        self.recognition_predictor = RecognitionPredictor(self.foundation_predictor)
        self.detection_predictor = DetectionPredictor()
        logger.info("✅ Models loaded successfully")

        self.image_formats = {'.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp'}
        self.pdf_format = {'.pdf'}

    def extract_text_with_coordinates(self, image_path: str) -> dict:
        """Extract text and exact coordinates using Surya OCR"""
        logger.info(f"🔍 Extracting text from: {Path(image_path).name}")

        image = Image.open(image_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        img_width, img_height = image.size

        predictions = self.recognition_predictor([image], det_predictor=self.detection_predictor)

        text_elements = []

        if predictions and len(predictions) > 0:
            page_pred = predictions[0]

            if hasattr(page_pred, 'text_lines'):
                for line in page_pred.text_lines:
                    if hasattr(line, 'bbox') and line.bbox:
                        text_elements.append({
                            'text': line.text.strip(),
                            'bbox': line.bbox,
                            'confidence': getattr(line, 'confidence', 1.0)
                        })

        result = {
            'image_size': (img_width, img_height),
            'text_elements': text_elements,
            'total_elements': len(text_elements)
        }

        logger.info(f"   ✅ Extracted {len(text_elements)} text elements")
        return result

    def create_searchable_pdf_page(self, image_path: str, ocr_data: dict, output_buffer: io.BytesIO, quality: int = 85) -> io.BytesIO:
        """Create a single PDF page with invisible text overlay and COMPRESSED image"""
        image = Image.open(image_path)
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        img_width, img_height = image.size

        # CRITICAL FIX: Compress image to JPEG in memory
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='JPEG', quality=quality, optimize=True)
        img_buffer.seek(0)
        
        # Use compressed image
        compressed_image = Image.open(img_buffer)

        pdf_canvas = canvas.Canvas(output_buffer, pagesize=(img_width, img_height))

        # Draw compressed image instead of original
        pdf_canvas.drawImage(
            ImageReader(compressed_image),
            0, 0,
            width=img_width,
            height=img_height,
            preserveAspectRatio=True
        )

        text_count = 0
        for element in ocr_data['text_elements']:
            text = element['text']

            if not text or not text.strip():
                continue

            bbox = element['bbox']

            try:
                x1, y1, x2, y2 = bbox

                bbox_width = x2 - x1
                bbox_height = y2 - y1

                if bbox_width <= 0 or bbox_height <= 0:
                    continue

                pdf_x = x1
                pdf_y = img_height - y2

                font_size = max(1, bbox_height * 0.8)

                pdf_canvas.saveState()

                text_obj = pdf_canvas.beginText(pdf_x, pdf_y)
                text_obj.setTextRenderMode(3)
                text_obj.setFont("Helvetica", font_size)

                try:
                    text_width = pdfmetrics.stringWidth(text, "Helvetica", font_size)
                    if text_width > 0:
                        h_scale = (bbox_width / text_width) * 100
                        h_scale = max(10, min(500, h_scale))
                        text_obj.setHorizScale(h_scale)
                except:
                    pass

                text_obj.textLine(text)
                pdf_canvas.drawText(text_obj)
                pdf_canvas.restoreState()

                text_count += 1

            except Exception as e:
                logger.debug(f"Could not add text '{text[:30]}...': {e}")
                continue

        logger.info(f"   ✅ Added {text_count} text elements to PDF layer")

        pdf_canvas.showPage()
        pdf_canvas.save()

        output_buffer.seek(0)
        return output_buffer

    def convert_image_to_searchable_pdf(self, image_path: str, output_path: str, quality: int = 85) -> str:
        """Convert a single image to searchable PDF"""
        logger.info("📄 Converting image to searchable PDF")

        ocr_data = self.extract_text_with_coordinates(image_path)

        if ocr_data['total_elements'] == 0:
            logger.warning("⚠️  No text detected in image!")

        pdf_buffer = io.BytesIO()
        self.create_searchable_pdf_page(image_path, ocr_data, pdf_buffer, quality=quality)

        with open(output_path, 'wb') as f:
            f.write(pdf_buffer.getvalue())

        logger.info(f"✅ Conversion complete: {ocr_data['total_elements']} text elements")
        return str(output_path)

    def convert_pdf_to_searchable_pdf(self, input_pdf_path: str, output_pdf_path: str, dpi: int = 200, quality: int = 85) -> str:
        """Convert a scanned PDF to searchable PDF using PyMuPDF with compression"""
        logger.info("📚 Converting PDF to searchable PDF")

        temp_folder = Path("temp_images")
        temp_folder.mkdir(exist_ok=True)

        # Open PDF with PyMuPDF
        pdf_document = fitz.open(input_pdf_path)
        image_paths = []
        
        # REDUCED DPI for smaller file size (200 instead of 300)
        zoom = dpi / 72.0

        for page_num, page in enumerate(pdf_document, start=1):
            logger.info(f"📄 Converting page {page_num}/{len(pdf_document)} to image...")
            
            # Render page to image
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Save as JPEG instead of PNG for smaller size
            img_path = temp_folder / f"page_{page_num}.jpg"
            pix.save(str(img_path), jpg_quality=quality)
            image_paths.append(str(img_path))

        pdf_document.close()
        logger.info(f"✅ Converted {len(image_paths)} pages to images")

        pdf_writer = PdfWriter()

        for page_num, img_path in enumerate(image_paths, start=1):
            logger.info(f"📄 Processing page {page_num}/{len(image_paths)} for OCR...")

            ocr_data = self.extract_text_with_coordinates(img_path)

            page_buffer = io.BytesIO()
            self.create_searchable_pdf_page(img_path, ocr_data, page_buffer, quality=quality)

            page_reader = PdfReader(page_buffer)
            pdf_writer.add_page(page_reader.pages[0])

        with open(output_pdf_path, 'wb') as output_file:
            pdf_writer.write(output_file)

        # Cleanup
        for img_path in image_paths:
            try:
                os.remove(img_path)
            except:
                pass

        try:
            temp_folder.rmdir()
        except:
            pass

        logger.info(f"✅ PDF conversion complete: {len(image_paths)} pages")
        return str(output_pdf_path)

    def convert_to_searchable(self, input_path: str, output_path: str, dpi: int = 200, quality: int = 85) -> str:
        """Universal converter - auto-detects input type"""
        input_file = Path(input_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        file_ext = input_file.suffix.lower()

        if file_ext in self.image_formats:
            return self.convert_image_to_searchable_pdf(input_path, output_path, quality=quality)
        elif file_ext in self.pdf_format:
            return self.convert_pdf_to_searchable_pdf(input_path, output_path, dpi=dpi, quality=quality)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")


# Initialize converter globally (loads models once)
logger.info("🚀 Initializing OCR models...")
converter = SearchableDocumentConverter()
logger.info("✅ OCR models ready!")


# ===================================================================
# HELPER FUNCTIONS
# ===================================================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def verify_pdf_searchable(pdf_path: str) -> dict:
    """Verify if a PDF is searchable"""
    try:
        reader = PdfReader(pdf_path)
        total_text = ""
        for page in reader.pages:
            total_text += page.extract_text()

        char_count = len(total_text.strip())

        return {
            'is_searchable': char_count > 10,
            'total_pages': len(reader.pages),
            'total_characters': char_count,
            'preview': total_text[:300].strip() if char_count > 10 else ""
        }
    except Exception as e:
        return {
            'is_searchable': False,
            'error': str(e)
        }


# ===================================================================
# API ROUTES
# ===================================================================

@app.route('/api/convert', methods=['POST'])
def api_convert():
    """
    Convert uploaded file to searchable PDF
    
    Parameters:
        - file: The file to convert (PDF, PNG, JPG, TIFF)
        - dpi: DPI for PDF conversion (optional, default: 200)
        - quality: JPEG quality 1-100 (optional, default: 85)
        
    Returns:
        - Searchable PDF file
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    input_path = None
    output_path = None
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        # Get settings (REDUCED defaults for smaller files)
        dpi = int(request.form.get('dpi', 200))  # Changed from 300 to 200
        quality = int(request.form.get('quality', 85))  # JPEG quality
        
        # Validate quality
        quality = max(50, min(100, quality))
        
        # Generate output filename
        output_filename = f"{Path(filename).stem}_searchable.pdf"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        # Convert to searchable PDF
        logger.info(f"Converting: {filename} with DPI: {dpi}, Quality: {quality}")
        converter.convert_to_searchable(input_path, output_path, dpi=dpi, quality=quality)
        
        # Get file sizes for logging
        input_size = os.path.getsize(input_path) / (1024 * 1024)
        output_size = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ Size: {input_size:.2f}MB → {output_size:.2f}MB")
        
        # Return the searchable PDF file
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=output_filename
        )
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Cleanup input file after processing
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
                logger.info(f"Cleaned up input file: {input_path}")
            except Exception as e:
                logger.warning(f"Could not delete input file: {e}")


@app.route('/api/verify', methods=['POST'])
def api_verify():
    """
    Verify if an uploaded PDF is searchable
    
    Parameters:
        - file: PDF file to verify
        
    Returns:
        - JSON with verification results
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Invalid PDF file'}), 400
    
    try:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        
        verification = verify_pdf_searchable(temp_path)
        
        # Add file size info
        file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        verification['file_size_mb'] = round(file_size_mb, 2)
        
        os.remove(temp_path)
        
        return jsonify(verification)
        
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'ocr_models_loaded': True,
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024),
        'default_dpi': 200,
        'default_quality': 85
    })


# ===================================================================
# MAIN
# ===================================================================

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 SEARCHABLE PDF CONVERTER - API SERVER (OPTIMIZED)")
    print("="*70)
    print(f"📍 Server: http://localhost:5008")
    print(f"📍 Convert: POST http://localhost:5008/api/convert")
    print(f"📍 Verify:  POST http://localhost:5008/api/verify")
    print(f"📍 Health:  GET  http://localhost:5008/health")
    print("="*70)
    print(f"📝 Max file size: {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024):.0f} MB")
    print(f"📁 Formats: {', '.join(ALLOWED_EXTENSIONS)}")
    print(f"⚙️  Default DPI: 200 (was 300)")
    print(f"⚙️  Default Quality: 85% JPEG")
    print("="*70)
    print("\nPress CTRL+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=5008, debug=True)