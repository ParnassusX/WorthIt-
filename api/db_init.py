import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def init_db():
    """Initialize database tables in Supabase if they don't exist"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("Supabase URL and key must be set in environment variables")
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Create products table if it doesn't exist
    # Note: Using SQL queries with Supabase client requires proper permissions
    # This is a simplified version - in production, you might need to use Supabase migrations
    try:
        # Check if table exists first
        response = supabase.table("products").select("id").limit(1).execute()
        print("Products table exists")
    except Exception as e:
        print(f"Creating products table: {e}")
        # Create products table
        supabase.table("products").create({
            "id": "uuid primary key default uuid_generate_v4()",
            "url": "text not null unique",
            "title": "text",
            "price": "float",
            "prices": "jsonb",
            "reviews": "text[]",
            "value_score": "float",
            "pros": "text[]",
            "cons": "text[]",
            "created_at": "timestamptz default now()"
        })
    
    try:
        # Check if users table exists
        response = supabase.table("users").select("telegram_id").limit(1).execute()
        print("Users table exists")
    except Exception as e:
        print(f"Creating users table: {e}")
        # Create users table
        supabase.table("users").create({
            "telegram_id": "bigint primary key",
            "scan_count": "int default 0",
            "created_at": "timestamptz default now()"
        })
    
    print("Database initialization completed")

# Allow running this script directly
if __name__ == "__main__":
    init_db()
