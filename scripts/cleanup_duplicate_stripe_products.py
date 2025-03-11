import os
import stripe
import sys
from collections import defaultdict

# Read API key directly from .env file
with open('.env', 'r') as env_file:
    for line in env_file:
        if line.startswith('STRIPE_API_KEY='):
            stripe.api_key = line.split('=', 1)[1].strip()
            break

if not stripe.api_key:
    print("Error: STRIPE_API_KEY environment variable not set.")
    sys.exit(1)

print("Checking for duplicate Stripe products for WorthIt! subscription tiers...")

try:
    # Get all products
    products = stripe.Product.list(limit=100)
    
    # Group products by name
    product_groups = defaultdict(list)
    for product in products:
        product_groups[product.name].append(product)
    
    # Find duplicates
    duplicates_found = False
    for name, products_list in product_groups.items():
        if len(products_list) > 1:
            duplicates_found = True
            print(f"\nFound {len(products_list)} duplicate products for '{name}':")
            
            # Sort by creation date (newest first)
            products_list.sort(key=lambda p: p.created, reverse=True)
            
            # Keep the newest one
            keep_product = products_list[0]
            print(f"  Keeping newest product: {keep_product.id} (created {keep_product.created})")
            
            # Archive the rest
            for product in products_list[1:]:
                print(f"  Archiving duplicate: {product.id} (created {product.created})")
                stripe.Product.modify(
                    product.id,
                    active=False,
                )
                print(f"    ✅ Product {product.id} archived successfully")
                
                # Get associated prices
                prices = stripe.Price.list(product=product.id)
                for price in prices:
                    print(f"    Deactivating price: {price.id}")
                    stripe.Price.modify(
                        price.id,
                        active=False,
                    )
                    print(f"      ✅ Price {price.id} deactivated successfully")
    
    if not duplicates_found:
        print("\n✅ No duplicate products found!")
    else:
        print("\n✅ Duplicate products have been archived successfully.")
        print("\nPlease update your payment_config.py file with the correct product and price IDs:")
        print("\nSTRIPE_PRODUCTS = {")
        
        # Get the active products for Basic and Premium tiers
        basic_products = [p for p in stripe.Product.list(active=True) if p.name == "Basic Tier"]
        premium_products = [p for p in stripe.Product.list(active=True) if p.name == "Premium Tier"]
        
        if basic_products:
            basic_product = basic_products[0]
            basic_prices = stripe.Price.list(product=basic_product.id, active=True)
            if basic_prices and len(basic_prices.data) > 0:
                basic_price = basic_prices.data[0]
                print(f"    SubscriptionTier.BASIC: {{")
                print(f"        \"product_id\": \"{basic_product.id}\",")
                print(f"        \"price_id\": \"{basic_price.id}\"")
                print(f"    }},")
        
        if premium_products:
            premium_product = premium_products[0]
            premium_prices = stripe.Price.list(product=premium_product.id, active=True)
            if premium_prices and len(premium_prices.data) > 0:
                premium_price = premium_prices.data[0]
                print(f"    SubscriptionTier.PREMIUM: {{")
                print(f"        \"product_id\": \"{premium_product.id}\",")
                print(f"        \"price_id\": \"{premium_price.id}\"")
                print(f"    }}")
        
        print("}")
    
except stripe.error.StripeError as e:
    print(f"Error checking Stripe products: {e}")
    sys.exit(1)