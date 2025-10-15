"""
Visual Product Matcher - Flask Backend Application

This module provides a REST API for AI-powered visual product similarity search
using Google's Gemini 2.0 Flash Experimental vision model. The system analyzes
uploaded images and returns ranked similar products from a curated database.

Features:
    - Image upload (file or URL)
    - AI-powered visual analysis
    - Similarity matching with semantic understanding
    - Category-aware ranking
    - RESTful API endpoints

Author: Visual Product Matcher Team
Version: 1.0.0
License: MIT
"""

import os
import json
from io import BytesIO
from typing import Dict, List, Tuple, Optional, Union
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

# Initialize Flask application
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)  # Enable Cross-Origin Resource Sharing

# Configure Gemini API (graceful if missing)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_ENABLED = bool(GEMINI_API_KEY)
if GEMINI_ENABLED:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("\n⚠️  GEMINI_API_KEY not set. Running in limited mode. /api/search requires the key for AI analysis.\n")

# Configuration constants
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
TOP_RESULTS_LIMIT = 20

# Initialize upload directory
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Load product database
try:
    with open('products.json', 'r', encoding='utf-8') as f:
        PRODUCTS = json.load(f)
    print(f"✅ Loaded {len(PRODUCTS)} products from database")
except FileNotFoundError:
    raise FileNotFoundError(
        "products.json not found. Ensure the product database exists."
    )
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON in products.json: {e}")

# Cache for product embeddings (in-memory storage)
product_embeddings_cache: Dict[int, str] = {}


def analyze_image(image_data: Union[Image.Image, str], is_url: bool = False) -> Dict:
    """Analyze image and return structured attributes for better UX and matching.

    Returns a dict with keys: summary, category, colors, materials, style, objects, suggested_tags.
    Falls back gracefully if AI is unavailable.
    """
    if not GEMINI_ENABLED:
        # Minimal offline fallback
        return {
            'summary': 'Image uploaded. AI analysis is unavailable in offline mode.',
            'category': 'Unknown',
            'colors': [],
            'materials': [],
            'style': [],
            'objects': [],
            'suggested_tags': []
        }

    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = (
            "You are an expert visual merchandiser. Analyze the image and return STRICT JSON only with keys: "
            "summary (2-3 sentences), category (single word or short phrase), colors (array of simple color names), "
            "materials (array), style (array), objects (array), suggested_tags (array of 5-12 short tags). "
            "No markdown, no extra text — JSON only."
        )

        if is_url:
            response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": image_data}])
        else:
            response = model.generate_content([prompt, image_data])

        text = (response.text or '').strip()
        
        # Strip markdown code fences if present (```json ... ```)
        if text.startswith('```'):
            lines = text.split('\n')
            # Remove first line if it's a fence (```json or ```)
            if lines[0].startswith('```'):
                lines = lines[1:]
            # Remove last line if it's a closing fence
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines).strip()
        
        # Try to extract JSON object from text
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_text = text[start:end+1]
        else:
            json_text = text
        
        try:
            analysis = json.loads(json_text)
        except Exception as parse_err:
            print(f"JSON parse error: {parse_err}")
            print(f"Raw text from model: {text[:500]}")
            # If the model returned non-JSON, do a best-effort wrap
            analysis = {
                'summary': text[:600] if text else 'Unable to analyze image.',
                'category': 'Unknown',
                'colors': [],
                'materials': [],
                'style': [],
                'objects': [],
                'suggested_tags': []
            }
        # Ensure required fields exist with correct types
        analysis.setdefault('summary', '')
        analysis.setdefault('category', 'Unknown')
        for k in ['colors', 'materials', 'style', 'objects', 'suggested_tags']:
            v = analysis.get(k, [])
            analysis[k] = v if isinstance(v, list) else []
        return analysis
    except Exception as e:
        print(f"Error in analyze_image: {e}")
        # Last-resort fallback
        return {
            'summary': 'Unable to analyze image at this time.',
            'category': 'Unknown',
            'colors': [],
            'materials': [],
            'style': [],
            'objects': [],
            'suggested_tags': []
        }


def build_query_embedding(analysis: Dict) -> str:
    """Concatenate analysis fields into a single string for similarity matching."""
    parts: List[str] = [
        analysis.get('summary', ''),
        analysis.get('category', ''),
        ' '.join(map(str, analysis.get('colors', []))),
        ' '.join(map(str, analysis.get('materials', []))),
        ' '.join(map(str, analysis.get('style', []))),
        ' '.join(map(str, analysis.get('objects', []))),
        ' '.join(map(str, analysis.get('suggested_tags', []))),
    ]
    return ' '.join([p for p in parts if p]).strip()


def calculate_similarity(embedding1: str, embedding2: str) -> float:
    """
    Calculate semantic similarity score between two text embeddings.
    
    Uses Jaccard similarity coefficient with category-aware boosting to compare
    two natural language descriptions. The algorithm favors matches where product
    category keywords overlap, providing better search results.
    
    Algorithm:
        1. Convert embeddings to lowercase word sets
        2. Calculate Jaccard similarity: |intersection| / |union|
        3. Apply 30% boost if category keywords match
        4. Cap final score at 1.0
    
    Args:
        embedding1: First text embedding (query image description)
        embedding2: Second text embedding (product description)
    
    Returns:
        float: Similarity score between 0.0 and 1.0 (higher = more similar)
    
    Example:
        >>> emb1 = "blue running shoes with white sole"
        >>> emb2 = "athletic footwear in blue and white colors"
        >>> score = calculate_similarity(emb1, emb2)
        >>> print(f"{score:.2f}")  # Output: ~0.65
    """
    # Tokenize and normalize to lowercase
    words1 = set(embedding1.lower().split())
    words2 = set(embedding2.lower().split())
    
    # Calculate Jaccard similarity coefficient
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    if len(union) == 0:
        return 0.0
    
    base_similarity = len(intersection) / len(union)
    
    # Category keywords for semantic boosting
    category_keywords = [
        'phone', 'laptop', 'camera', 'shoes', 'watch', 'headphones',
        'tablet', 'monitor', 'keyboard', 'mouse', 'speaker', 'jacket',
        'jeans', 'sunglasses', 'chair', 'desk', 'bottle', 'vacuum',
        'smartphone', 'computer', 'footwear', 'clothing', 'furniture',
        'electronics', 'accessory', 'home', 'device'
    ]
    
    # Check if category keywords match in both embeddings
    category_match = any(
        keyword in embedding1.lower() and keyword in embedding2.lower()
        for keyword in category_keywords
    )
    
    # Apply category boost (30% increase)
    similarity = base_similarity * 1.3 if category_match else base_similarity
    
    # Ensure score doesn't exceed 1.0
    return min(similarity, 1.0)


def get_product_embedding(product: Dict) -> str:
    """
    Retrieve or generate text embedding for a product.
    
    Products are embedded as concatenated text from their metadata fields.
    Results are cached in memory to avoid redundant processing.
    
    Args:
        product: Dictionary containing product data with keys:
                 id, name, category, description
    
    Returns:
        str: Lowercase text representation of the product
    
    Example:
        >>> product = {
        ...     "id": 1,
        ...     "name": "iPhone 15",
        ...     "category": "Electronics",
        ...     "description": "Latest smartphone"
        ... }
        >>> embedding = get_product_embedding(product)
        >>> print(embedding)
        'iphone 15 electronics latest smartphone'
    """
    product_id = product['id']
    
    # Return cached embedding if available
    if product_id in product_embeddings_cache:
        return product_embeddings_cache[product_id]
    
    # Generate embedding from product metadata
    description = f"{product['name']} {product['category']} {product['description']}"
    
    # Cache the embedding for future requests
    embedding = description.lower()
    product_embeddings_cache[product_id] = embedding
    
    return embedding


@app.route('/')
def index():
    """
    Serve the main application page.
    
    Returns:
        HTML: The main index.html file from the static folder
    """
    return send_from_directory('static', 'index.html')


@app.route('/api/search', methods=['POST'])
def search_products():
    """
    Search for visually similar products based on uploaded image or URL.
    
    Accepts either a multipart/form-data file upload or JSON with image URL.
    The image is analyzed by Gemini AI, and similarity scores are calculated
    against all products in the database.
    
    Request Methods:
        POST - Submit image for similarity search
    
    Request Formats:
        1. File Upload:
           Content-Type: multipart/form-data
           Body: image=<file>
           
        2. Image URL:
           Content-Type: application/json
           Body: {"image_url": "https://..."}
    
    Request Body (File Upload):
        image (file): Image file in PNG, JPG, JPEG, GIF, or WEBP format
                     Maximum size: 16MB
    
    Request Body (URL):
        image_url (string): Publicly accessible URL to an image
    
    Response (Success - 200 OK):
        {
            "success": true,
            "query_description": "AI-generated description of image...",
            "results": [
                {
                    "product": {
                        "id": 1,
                        "name": "Product Name",
                        "category": "Category",
                        "price": 99.99,
                        "image_url": "https://...",
                        "description": "Product description"
                    },
                    "similarity": 0.8542
                }
            ],
            "total_results": 20
        }
    
    Response (Error - 400/500):
        {
            "error": "Error message description"
        }
    
    Error Responses:
        400 Bad Request:
            - No file selected
            - Invalid file type
            - No image URL provided
            - Failed to fetch image from URL
        500 Internal Server Error:
            - Gemini API failure
            - Image processing error
    
    Example:
        >>> # Using cURL with file upload
        >>> curl -X POST http://localhost:5000/api/search \\
        ...      -F "image=@product.jpg"
        
        >>> # Using cURL with image URL
        >>> curl -X POST http://localhost:5000/api/search \\
        ...      -H "Content-Type: application/json" \\
        ...      -d '{"image_url": "https://example.com/image.jpg"}'
    """
    try:
        image_analysis: Optional[Dict] = None
        image_embedding: Optional[str] = None
        
        # Check if image file was uploaded
        if 'image' in request.files:
            file = request.files['image']
            
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            # Validate file type
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            
            if file_ext not in allowed_extensions:
                return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP'}), 400
            
            # Open and process image
            image = Image.open(file.stream)
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Analyze + build embedding
            image_analysis = analyze_image(image, is_url=False)
            image_embedding = build_query_embedding(image_analysis)
        
        # Check if image URL was provided
        elif request.is_json and 'image_url' in request.json:
            image_url = request.json['image_url']
            
            if not image_url:
                return jsonify({'error': 'No image URL provided'}), 400
            
            # For URL-based search, we'll use Gemini's URL support
            # Note: In production, you might want to download and validate the image
            try:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                
                # Open image from URL
                image = Image.open(BytesIO(response.content))
                
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Analyze + build embedding
                image_analysis = analyze_image(image, is_url=False)
                image_embedding = build_query_embedding(image_analysis)
            
            except Exception as e:
                return jsonify({'error': f'Failed to fetch image from URL: {str(e)}'}), 400
        
        else:
            return jsonify({'error': 'No image file or URL provided'}), 400
        
        # Calculate similarities with all products
        similarities = []
        
        for product in PRODUCTS:
            product_embedding = get_product_embedding(product)
            similarity = calculate_similarity(image_embedding, product_embedding)
            
            similarities.append({
                'product': product,
                'similarity': round(similarity, 4)
            })
        
        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Get top results
        top_results = similarities[:20]  # Return top 20 matches

        return jsonify({
            'success': True,
            'analysis': image_analysis,
            'results': top_results,
            'total_results': len(top_results)
        })
    
    except Exception as e:
        print(f"Error in search: {str(e)}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500


@app.route('/api/products', methods=['GET'])
def get_products():
    """
    Retrieve all products or filter by category.
    
    Returns the complete product catalog or a filtered subset based on
    the category query parameter.
    
    Request Methods:
        GET - Retrieve product list
    
    Query Parameters:
        category (optional): Filter products by category name (case-insensitive)
                           Example: "Electronics", "Footwear", "Clothing"
    
    Response (200 OK):
        {
            "products": [
                {
                    "id": 1,
                    "name": "Product Name",
                    "category": "Category",
                    "price": 99.99,
                    "image_url": "https://...",
                    "description": "Product description"
                }
            ],
            "count": 65
        }
    
    Example:
        >>> # Get all products
        >>> curl http://localhost:5000/api/products
        
        >>> # Filter by category
        >>> curl http://localhost:5000/api/products?category=Electronics
    """
    category = request.args.get('category', None)
    
    if category:
        # Case-insensitive category filtering
        filtered_products = [
            p for p in PRODUCTS 
            if p['category'].lower() == category.lower()
        ]
        return jsonify({
            'products': filtered_products,
            'count': len(filtered_products)
        })
    
    # Return all products
    return jsonify({
        'products': PRODUCTS,
        'count': len(PRODUCTS)
    })


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """
    Retrieve all unique product categories.
    
    Returns a sorted list of all category names present in the product database.
    Useful for populating category filters in the UI.
    
    Request Methods:
        GET - Retrieve category list
    
    Response (200 OK):
        {
            "categories": [
                "Accessories",
                "Clothing",
                "Electronics",
                "Footwear",
                "Furniture",
                "Home"
            ]
        }
    
    Example:
        >>> curl http://localhost:5000/api/categories
    """
    # Extract unique categories and sort alphabetically
    categories = list(set(p['category'] for p in PRODUCTS))
    categories.sort()
    
    return jsonify({'categories': categories})


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for monitoring and diagnostics.
    
    Provides information about the API's operational status, database state,
    and configuration. Useful for load balancers, monitoring tools, and debugging.
    
    Request Methods:
        GET - Check API health status
    
    Response (200 OK):
        {
            "status": "healthy",
            "products_count": 65,
            "gemini_configured": true
        }
    
    Response Fields:
        status (string): "healthy" if API is operational
        products_count (int): Number of products loaded in database
        gemini_configured (bool): Whether Gemini API key is configured
    
    Example:
        >>> curl http://localhost:5000/api/health
    >>> # Expected: {"status":"healthy","products_count":65,"gemini_configured":true}
    """
    return jsonify({
        'status': 'healthy',
        'products_count': len(PRODUCTS),
        'gemini_configured': bool(GEMINI_API_KEY)
    })


if __name__ == '__main__':
    """
    Application entry point.
    
    Starts the Flask development server. In production, use Gunicorn instead:
        gunicorn app:app
    
    Environment Variables:
        PORT: Server port (default: 5000)
    
    Configuration:
        - Host: 0.0.0.0 (accessible from network)
        - Debug: True (development only - disable in production)
    """
    port = int(os.environ.get('PORT', 5000))
    print(f"\n{'='*60}")
    print(f"🚀 Visual Product Matcher API Server")
    print(f"{'='*60}")
    print(f"📦 Products loaded: {len(PRODUCTS)}")
    print(f"🔑 Gemini API: {'✅ Configured' if GEMINI_API_KEY else '❌ Not configured'}")
    print(f"🌐 Server starting on: http://0.0.0.0:{port}")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=True)
