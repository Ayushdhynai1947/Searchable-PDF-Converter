# # app.py - Flask API for Searchable PDF Conversion
# # Run with: python app.py
# # API endpoint: http://localhost:5008/api/convert

# import os
# import logging
# from pathlib import Path
# from flask import Flask, request, send_file, jsonify
# from werkzeug.utils import secure_filename
# import io
# from PIL import Image
# import fitz  # PyMuPDF - No Poppler needed!
# from reportlab.pdfgen import canvas
# from reportlab.lib.utils import ImageReader
# from reportlab.pdfbase import pdfmetrics
# from PyPDF2 import PdfReader, PdfWriter

# # Surya imports
# from surya.foundation import FoundationPredictor
# from surya.recognition import RecognitionPredictor
# from surya.detection import DetectionPredictor

# # Setup logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger(__name__)

# # Flask app setup
# app = Flask(__name__)
# app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
# app.config['UPLOAD_FOLDER'] = 'uploads'
# app.config['OUTPUT_FOLDER'] = 'outputs'

# # Create necessary folders
# Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
# Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)
# Path('temp_images').mkdir(exist_ok=True)

# ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'tif', 'bmp'}


# # ===================================================================
# # SEARCHABLE DOCUMENT CONVERTER CLASS
# # ===================================================================

# class SearchableDocumentConverter:
#     """
#     Universal converter for making documents searchable
#     Supports: PDF, PNG, JPG, JPEG, TIFF
#     """

#     def __init__(self):
#         """Initialize Surya OCR models"""
#         logger.info("🔄 Loading Surya OCR models...")
#         self.foundation_predictor = FoundationPredictor()
#         self.recognition_predictor = RecognitionPredictor(self.foundation_predictor)
#         self.detection_predictor = DetectionPredictor()
#         logger.info("✅ Models loaded successfully")

#         self.image_formats = {'.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp'}
#         self.pdf_format = {'.pdf'}

#     def extract_text_with_coordinates(self, image_path: str) -> dict:
#         """Extract text and exact coordinates using Surya OCR"""
#         logger.info(f"🔍 Extracting text from: {Path(image_path).name}")

#         image = Image.open(image_path)
#         if image.mode != 'RGB':
#             image = image.convert('RGB')

#         img_width, img_height = image.size

#         predictions = self.recognition_predictor([image], det_predictor=self.detection_predictor)

#         text_elements = []

#         if predictions and len(predictions) > 0:
#             page_pred = predictions[0]

#             if hasattr(page_pred, 'text_lines'):
#                 for line in page_pred.text_lines:
#                     if hasattr(line, 'bbox') and line.bbox:
#                         text_elements.append({
#                             'text': line.text.strip(),
#                             'bbox': line.bbox,
#                             'confidence': getattr(line, 'confidence', 1.0)
#                         })

#         result = {
#             'image_size': (img_width, img_height),
#             'text_elements': text_elements,
#             'total_elements': len(text_elements)
#         }

#         logger.info(f"   ✅ Extracted {len(text_elements)} text elements")
#         return result

#     def create_searchable_pdf_page(self, image_path: str, ocr_data: dict, output_buffer: io.BytesIO) -> io.BytesIO:
#         """Create a single PDF page with invisible text overlay"""
#         image = Image.open(image_path)
#         img_width, img_height = image.size

#         pdf_canvas = canvas.Canvas(output_buffer, pagesize=(img_width, img_height))

#         pdf_canvas.drawImage(
#             ImageReader(image),
#             0, 0,
#             width=img_width,
#             height=img_height,
#             preserveAspectRatio=True
#         )

#         text_count = 0
#         for element in ocr_data['text_elements']:
#             text = element['text']

#             if not text or not text.strip():
#                 continue

#             bbox = element['bbox']

#             try:
#                 x1, y1, x2, y2 = bbox

#                 bbox_width = x2 - x1
#                 bbox_height = y2 - y1

#                 if bbox_width <= 0 or bbox_height <= 0:
#                     continue

#                 pdf_x = x1
#                 pdf_y = img_height - y2

#                 font_size = max(1, bbox_height * 0.8)

#                 pdf_canvas.saveState()

#                 text_obj = pdf_canvas.beginText(pdf_x, pdf_y)
#                 text_obj.setTextRenderMode(3)
#                 text_obj.setFont("Helvetica", font_size)

#                 try:
#                     text_width = pdfmetrics.stringWidth(text, "Helvetica", font_size)
#                     if text_width > 0:
#                         h_scale = (bbox_width / text_width) * 100
#                         h_scale = max(10, min(500, h_scale))
#                         text_obj.setHorizScale(h_scale)
#                 except:
#                     pass

#                 text_obj.textLine(text)
#                 pdf_canvas.drawText(text_obj)
#                 pdf_canvas.restoreState()

#                 text_count += 1

#             except Exception as e:
#                 logger.debug(f"Could not add text '{text[:30]}...': {e}")
#                 continue

#         logger.info(f"   ✅ Added {text_count} text elements to PDF layer")

#         pdf_canvas.showPage()
#         pdf_canvas.save()

#         output_buffer.seek(0)
#         return output_buffer

#     def convert_image_to_searchable_pdf(self, image_path: str, output_path: str) -> str:
#         """Convert a single image to searchable PDF"""
#         logger.info("📄 Converting image to searchable PDF")

#         ocr_data = self.extract_text_with_coordinates(image_path)

#         if ocr_data['total_elements'] == 0:
#             logger.warning("⚠️  No text detected in image!")

#         pdf_buffer = io.BytesIO()
#         self.create_searchable_pdf_page(image_path, ocr_data, pdf_buffer)

#         with open(output_path, 'wb') as f:
#             f.write(pdf_buffer.getvalue())

#         logger.info(f"✅ Conversion complete: {ocr_data['total_elements']} text elements")
#         return str(output_path)

#     def convert_pdf_to_searchable_pdf(self, input_pdf_path: str, output_pdf_path: str, dpi: int = 300) -> str:
#         """Convert a scanned PDF to searchable PDF using PyMuPDF"""
#         logger.info("📚 Converting PDF to searchable PDF")

#         temp_folder = Path("temp_images")
#         temp_folder.mkdir(exist_ok=True)

#         # Open PDF with PyMuPDF
#         pdf_document = fitz.open(input_pdf_path)
#         image_paths = []
        
#         # Convert zoom level based on DPI (default 72 DPI = zoom 1.0)
#         zoom = dpi / 72.0

#         for page_num, page in enumerate(pdf_document, start=1):
#             logger.info(f"📄 Converting page {page_num}/{len(pdf_document)} to image...")
            
#             # Render page to image
#             mat = fitz.Matrix(zoom, zoom)
#             pix = page.get_pixmap(matrix=mat, alpha=False)
            
#             # Save as PNG
#             img_path = temp_folder / f"page_{page_num}.png"
#             pix.save(str(img_path))
#             image_paths.append(str(img_path))

#         pdf_document.close()
#         logger.info(f"✅ Converted {len(image_paths)} pages to images")

#         pdf_writer = PdfWriter()

#         for page_num, img_path in enumerate(image_paths, start=1):
#             logger.info(f"📄 Processing page {page_num}/{len(image_paths)} for OCR...")

#             ocr_data = self.extract_text_with_coordinates(img_path)

#             page_buffer = io.BytesIO()
#             self.create_searchable_pdf_page(img_path, ocr_data, page_buffer)

#             page_reader = PdfReader(page_buffer)
#             pdf_writer.add_page(page_reader.pages[0])

#         with open(output_pdf_path, 'wb') as output_file:
#             pdf_writer.write(output_file)

#         # Cleanup
#         for img_path in image_paths:
#             try:
#                 os.remove(img_path)
#             except:
#                 pass

#         try:
#             temp_folder.rmdir()
#         except:
#             pass

#         logger.info(f"✅ PDF conversion complete: {len(image_paths)} pages")
#         return str(output_pdf_path)

#     def convert_to_searchable(self, input_path: str, output_path: str, dpi: int = 300) -> str:
#         """Universal converter - auto-detects input type"""
#         input_file = Path(input_path)

#         if not input_file.exists():
#             raise FileNotFoundError(f"Input file not found: {input_path}")

#         file_ext = input_file.suffix.lower()

#         if file_ext in self.image_formats:
#             return self.convert_image_to_searchable_pdf(input_path, output_path)
#         elif file_ext in self.pdf_format:
#             return self.convert_pdf_to_searchable_pdf(input_path, output_path, dpi)
#         else:
#             raise ValueError(f"Unsupported file format: {file_ext}")


# # Initialize converter globally (loads models once)
# logger.info("🚀 Initializing OCR models...")
# converter = SearchableDocumentConverter()
# logger.info("✅ OCR models ready!")


# # ===================================================================
# # HELPER FUNCTIONS
# # ===================================================================

# def allowed_file(filename):
#     """Check if file extension is allowed"""
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# def verify_pdf_searchable(pdf_path: str) -> dict:
#     """Verify if a PDF is searchable"""
#     try:
#         reader = PdfReader(pdf_path)
#         total_text = ""
#         for page in reader.pages:
#             total_text += page.extract_text()

#         char_count = len(total_text.strip())

#         return {
#             'is_searchable': char_count > 10,
#             'total_pages': len(reader.pages),
#             'total_characters': char_count,
#             'preview': total_text[:300].strip() if char_count > 10 else ""
#         }
#     except Exception as e:
#         return {
#             'is_searchable': False,
#             'error': str(e)
#         }


# # ===================================================================
# # API ROUTES
# # ===================================================================

# @app.route('/api/convert', methods=['POST'])
# def api_convert():
#     """
#     Convert uploaded file to searchable PDF
    
#     Parameters:
#         - file: The file to convert (PDF, PNG, JPG, TIFF)
#         - dpi: DPI for PDF conversion (optional, default: 300)
        
#     Returns:
#         - Searchable PDF file
#     """
#     if 'file' not in request.files:
#         return jsonify({'error': 'No file uploaded'}), 400
    
#     file = request.files['file']
    
#     if file.filename == '' or not allowed_file(file.filename):
#         return jsonify({'error': 'Invalid file type'}), 400
    
#     input_path = None
#     output_path = None
    
#     try:
#         # Save uploaded file
#         filename = secure_filename(file.filename)
#         input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#         file.save(input_path)
        
#         # Get DPI setting
#         dpi = int(request.form.get('dpi', 300))
        
#         # Generate output filename
#         output_filename = f"{Path(filename).stem}_searchable.pdf"
#         output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
#         # Convert to searchable PDF
#         logger.info(f"Converting: {filename} with DPI: {dpi}")
#         converter.convert_to_searchable(input_path, output_path, dpi=dpi)
        
#         logger.info(f"✅ Conversion successful, sending file to client")
        
#         # Return the searchable PDF file
#         return send_file(
#             output_path,
#             mimetype='application/pdf',
#             as_attachment=True,
#             download_name=output_filename
#         )
        
#     except Exception as e:
#         logger.error(f"Conversion error: {e}")
#         return jsonify({'error': str(e)}), 500
    
#     finally:
#         # Cleanup input file after processing
#         if input_path and os.path.exists(input_path):
#             try:
#                 os.remove(input_path)
#                 logger.info(f"Cleaned up input file: {input_path}")
#             except Exception as e:
#                 logger.warning(f"Could not delete input file: {e}")


# @app.route('/api/verify', methods=['POST'])
# def api_verify():
#     """
#     Verify if an uploaded PDF is searchable
    
#     Parameters:
#         - file: PDF file to verify
        
#     Returns:
#         - JSON with verification results
#     """
#     if 'file' not in request.files:
#         return jsonify({'error': 'No file uploaded'}), 400
    
#     file = request.files['file']
    
#     if file.filename == '' or not file.filename.lower().endswith('.pdf'):
#         return jsonify({'error': 'Invalid PDF file'}), 400
    
#     try:
#         filename = secure_filename(file.filename)
#         temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#         file.save(temp_path)
        
#         verification = verify_pdf_searchable(temp_path)
        
#         os.remove(temp_path)
        
#         return jsonify(verification)
        
#     except Exception as e:
#         logger.error(f"Verification error: {e}")
#         return jsonify({'error': str(e)}), 500


# @app.route('/health', methods=['GET'])
# def health():
#     """Health check endpoint"""
#     return jsonify({
#         'status': 'healthy',
#         'ocr_models_loaded': True,
#         'supported_formats': list(ALLOWED_EXTENSIONS),
#         'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024)
#     })


# # ===================================================================
# # MAIN
# # ===================================================================

# if __name__ == '__main__':
#     print("\n" + "="*70)
#     print("🚀 SEARCHABLE PDF CONVERTER - API SERVER")
#     print("="*70)
#     print(f"📍 Server: http://localhost:5008")
#     print(f"📍 Convert: POST http://localhost:5008/api/convert")
#     print(f"📍 Verify:  POST http://localhost:5008/api/verify")
#     print(f"📍 Health:  GET  http://localhost:5008/health")
#     print("="*70)
#     print(f"📝 Max file size: {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024):.0f} MB")
#     print(f"📁 Formats: {', '.join(ALLOWED_EXTENSIONS)}")
#     print("="*70)
#     print("\nPress CTRL+C to stop the server\n")
    
#     app.run(host='0.0.0.0', port=5008, debug=True)

# app.py - Flask API for Searchable PDF Conversion (FIXED v2)
# Run with: python app.py
# API endpoint: http://localhost:5008/api/convert

import os
import logging
from pathlib import Path
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
import io
from PIL import Image
import fitz  # PyMuPDF
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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)
Path('temp_images').mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'tif', 'bmp'}


class SearchableDocumentConverter:
    """Universal converter for making documents searchable"""

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
        """Extract text and coordinates using Surya OCR"""
        logger.info(f"🔍 Extracting text from: {Path(image_path).name}")

        image = Image.open(image_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        img_width, img_height = image.size
        logger.info(f"   Image size: {img_width}x{img_height}")

        # Run OCR
        predictions = self.recognition_predictor([image], det_predictor=self.detection_predictor)

        text_elements = []

        if predictions and len(predictions) > 0:
            page_pred = predictions[0]
            logger.info(f"   OCR returned prediction object: {type(page_pred)}")

            if hasattr(page_pred, 'text_lines') and page_pred.text_lines:
                logger.info(f"   Found {len(page_pred.text_lines)} text lines")
                
                for idx, line in enumerate(page_pred.text_lines):
                    if not hasattr(line, 'bbox') or not line.bbox:
                        logger.debug(f"   Line {idx}: No bbox")
                        continue
                    
                    text = line.text.strip() if hasattr(line, 'text') else ""
                    
                    if not text:
                        logger.debug(f"   Line {idx}: Empty text")
                        continue

                    bbox = line.bbox
                    
                    # Validate bbox format and values
                    if len(bbox) != 4:
                        logger.debug(f"   Line {idx}: Invalid bbox length: {bbox}")
                        continue
                    
                    x1, y1, x2, y2 = bbox
                    
                    # Clamp coordinates to bounds
                    x1 = max(0, min(x1, img_width))
                    y1 = max(0, min(y1, img_height))
                    x2 = max(x1 + 1, min(x2, img_width))
                    y2 = max(y1 + 1, min(y2, img_height))
                    
                    bbox_width = x2 - x1
                    bbox_height = y2 - y1
                    
                    if bbox_width <= 0 or bbox_height <= 0:
                        logger.debug(f"   Line {idx}: Invalid dimensions {bbox_width}x{bbox_height}")
                        continue

                    confidence = getattr(line, 'confidence', 1.0)
                    
                    text_elements.append({
                        'text': text,
                        'bbox': (x1, y1, x2, y2),
                        'confidence': confidence
                    })

            else:
                logger.warning("   No text_lines found in prediction")
        else:
            logger.warning("   Empty predictions returned from OCR")

        result = {
            'image_size': (img_width, img_height),
            'text_elements': text_elements,
            'total_elements': len(text_elements)
        }

        logger.info(f"   ✅ Extracted {len(text_elements)} valid text elements")
        return result

    def create_searchable_pdf_page(self, image_path: str, ocr_data: dict, output_buffer: io.BytesIO) -> io.BytesIO:
        """Create a single PDF page with invisible text overlay - FIXED v2"""
        image = Image.open(image_path)
        
        # Ensure image is RGB (no transparency)
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        img_width, img_height = image.size

        pdf_canvas = canvas.Canvas(output_buffer, pagesize=(img_width, img_height))

        # Draw the image as background
        try:
            pdf_canvas.drawImage(
                ImageReader(image),
                0, 0,
                width=img_width,
                height=img_height,
                preserveAspectRatio=False
            )
            logger.debug("   ✅ Background image drawn successfully")
        except Exception as e:
            logger.error(f"   ❌ Failed to draw background image: {e}")
            return output_buffer

        text_count = 0
        skip_count = 0

        for element in ocr_data['text_elements']:
            text = element['text'].strip()

            if not text:
                skip_count += 1
                continue

            x1, y1, x2, y2 = element['bbox']
            bbox_width = x2 - x1
            bbox_height = y2 - y1

            if bbox_width <= 0 or bbox_height <= 0:
                skip_count += 1
                continue

            try:
                # CRITICAL FIX: Better coordinate conversion
                # Surya uses: top-left = (0,0), Y increases downward
                # ReportLab uses: bottom-left = (0,0), Y increases upward
                
                # Position text at the top-left of bbox
                pdf_x = x1
                pdf_y = img_height - y2  # Convert Y coordinate properly
                
                # Ensure position is valid
                if pdf_x < 0 or pdf_y < 0 or pdf_x >= img_width or pdf_y >= img_height:
                    logger.debug(f"Text position invalid: ({pdf_x}, {pdf_y}) vs img({img_width}, {img_height})")
                    skip_count += 1
                    continue

                # CRITICAL: Calculate font size that fits in bbox
                font_size = max(8, min(bbox_height * 0.9, 72))

                pdf_canvas.saveState()

                # Create text object
                text_obj = pdf_canvas.beginText(pdf_x, pdf_y)
                
                # CRITICAL FIX: Use text render mode 3 (invisible but searchable)
                text_obj.setTextRenderMode(3)
                text_obj.setFont("Helvetica", font_size)

                # Calculate and apply horizontal scaling
                try:
                    text_width = pdfmetrics.stringWidth(text, "Helvetica", font_size)
                    if text_width > 0 and bbox_width > 0:
                        h_scale = (bbox_width / text_width) * 100
                        # Clamp scaling to reasonable range
                        h_scale = max(25, min(250, h_scale))
                        text_obj.setHorizScale(h_scale)
                        logger.debug(f"Text scaling: {h_scale:.1f}%")
                except Exception as e:
                    logger.debug(f"Font width calculation failed: {e}")
                    pass

                # Add text - use textLine to ensure it's added
                text_obj.textLine(text)
                pdf_canvas.drawText(text_obj)
                pdf_canvas.restoreState()

                text_count += 1

            except Exception as e:
                logger.warning(f"Failed to add text '{text[:40]}...': {e}")
                skip_count += 1
                continue

        logger.info(f"   ✅ Added {text_count} text elements to overlay, skipped {skip_count}")

        pdf_canvas.showPage()
        pdf_canvas.save()

        output_buffer.seek(0)
        return output_buffer

    def convert_image_to_searchable_pdf(self, image_path: str, output_path: str) -> str:
        """Convert a single image to searchable PDF"""
        logger.info("📄 Converting image to searchable PDF")

        ocr_data = self.extract_text_with_coordinates(image_path)

        if ocr_data['total_elements'] == 0:
            logger.warning("⚠️  No text detected in image! PDF will be image-only.")

        pdf_buffer = io.BytesIO()
        self.create_searchable_pdf_page(image_path, ocr_data, pdf_buffer)

        with open(output_path, 'wb') as f:
            f.write(pdf_buffer.getvalue())

        logger.info(f"✅ Image conversion complete: {ocr_data['total_elements']} text elements added")
        return str(output_path)

    def convert_pdf_to_searchable_pdf(self, input_pdf_path: str, output_pdf_path: str, dpi: int = 300) -> str:
        """Convert a scanned PDF to searchable PDF"""
        logger.info("📚 Converting PDF to searchable PDF")

        temp_folder = Path("temp_images")
        temp_folder.mkdir(exist_ok=True)

        # Open PDF with PyMuPDF
        pdf_document = fitz.open(input_pdf_path)
        image_paths = []
        
        zoom = dpi / 72.0
        total_pages = len(pdf_document)

        logger.info(f"   Total pages: {total_pages}, DPI: {dpi}, Zoom: {zoom}")

        # Convert all pages to images
        for page_num, page in enumerate(pdf_document, start=1):
            try:
                logger.info(f"📄 Rendering page {page_num}/{total_pages}...")
                
                mat = fitz.Matrix(zoom, zoom)
                # Use alpha=False to ensure opaque image
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                img_path = temp_folder / f"page_{page_num}.png"
                pix.save(str(img_path))
                image_paths.append(str(img_path))
                logger.info(f"   ✅ Page {page_num} rendered ({pix.width}x{pix.height})")
                
            except Exception as e:
                logger.error(f"   ❌ Failed to render page {page_num}: {e}")
                continue

        pdf_document.close()
        
        if not image_paths:
            raise ValueError(f"Failed to extract any pages from PDF")
            
        logger.info(f"✅ Extracted {len(image_paths)}/{total_pages} pages as images")

        pdf_writer = PdfWriter()

        # Process each page for OCR
        for page_num, img_path in enumerate(image_paths, start=1):
            try:
                logger.info(f"📄 Processing page {page_num}/{len(image_paths)} with OCR...")

                ocr_data = self.extract_text_with_coordinates(img_path)

                if ocr_data['total_elements'] == 0:
                    logger.warning(f"   ⚠️  No text detected on page {page_num}")
                else:
                    logger.info(f"   📝 Found {ocr_data['total_elements']} text elements")

                page_buffer = io.BytesIO()
                self.create_searchable_pdf_page(img_path, ocr_data, page_buffer)

                page_reader = PdfReader(page_buffer)
                if page_reader.pages:
                    pdf_writer.add_page(page_reader.pages[0])
                    logger.info(f"   ✅ Page {page_num} added to output")
                else:
                    logger.error(f"   ❌ Failed to add page {page_num}")

            except Exception as e:
                logger.error(f"   ❌ Error processing page {page_num}: {e}", exc_info=True)
                continue

        if not pdf_writer.pages:
            raise ValueError("Failed to process any pages successfully")

        # Write final PDF
        with open(output_pdf_path, 'wb') as output_file:
            pdf_writer.write(output_file)
            logger.info(f"   ✅ PDF file written with {len(pdf_writer.pages)} pages")

        # Cleanup temp images
        for img_path in image_paths:
            try:
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"Could not delete {img_path}: {e}")

        try:
            temp_folder.rmdir()
        except Exception as e:
            logger.debug(f"Could not remove temp folder: {e}")

        logger.info(f"✅ PDF conversion complete: {len(image_paths)} pages processed")
        return str(output_pdf_path)

    def convert_to_searchable(self, input_path: str, output_path: str, dpi: int = 300) -> str:
        """Universal converter - auto-detects input type"""
        input_file = Path(input_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        file_ext = input_file.suffix.lower()

        if file_ext in self.image_formats:
            return self.convert_image_to_searchable_pdf(input_path, output_path)
        elif file_ext in self.pdf_format:
            return self.convert_pdf_to_searchable_pdf(input_path, output_path, dpi)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")


# Initialize converter globally
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
    """Convert uploaded file to searchable PDF"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    input_path = None
    output_path = None
    
    try:
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        dpi = int(request.form.get('dpi', 300))
        
        output_filename = f"{Path(filename).stem}_searchable.pdf"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        logger.info(f"🚀 Converting: {filename} with DPI: {dpi}")
        converter.convert_to_searchable(input_path, output_path, dpi=dpi)
        
        logger.info(f"✅ Conversion successful")
        
        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=output_filename
        )
        
    except Exception as e:
        logger.error(f"❌ Conversion error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    
    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception as e:
                logger.warning(f"Could not delete input file: {e}")


@app.route('/api/verify', methods=['POST'])
def api_verify():
    """Verify if an uploaded PDF is searchable"""
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
        'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024)
    })


# ===================================================================
# MAIN
# ===================================================================

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 SEARCHABLE PDF CONVERTER - API SERVER (FIXED v2)")
    print("="*70)
    print(f"📍 Server: http://localhost:5008")
    print(f"📍 Convert: POST http://localhost:5008/api/convert")
    print(f"📍 Verify:  POST http://localhost:5008/api/verify")
    print(f"📍 Health:  GET  http://localhost:5008/health")
    print("="*70)
    print(f"📝 Max file size: {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024):.0f} MB")
    print(f"📁 Formats: {', '.join(ALLOWED_EXTENSIONS)}")
    print("="*70)
    print("\nPress CTRL+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=5008, debug=True)