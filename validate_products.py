#!/usr/bin/env python3
"""
Product Database Validation Script
Used by CI/CD pipeline to validate products.json
"""

import json
import sys

def validate_products():
    """Validate the products database."""
    try:
        with open('products.json', 'r') as f:
            products = json.load(f)
        
        # Check minimum number of products
        if len(products) < 50:
            print(f'❌ Error: Expected >= 50 products, got {len(products)}')
            return False
        
        # Check required keys
        required_keys = ['id', 'name', 'category', 'price', 'image_url', 'description']
        
        for i, product in enumerate(products):
            for key in required_keys:
                if key not in product:
                    print(f'❌ Error: Product {i} missing key: {key}')
                    return False
        
        print(f'✅ Product database validated: {len(products)} products')
        return True
    
    except Exception as e:
        print(f'❌ Error validating products: {str(e)}')
        return False

if __name__ == '__main__':
    if validate_products():
        sys.exit(0)
    else:
        sys.exit(1)
