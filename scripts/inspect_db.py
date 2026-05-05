import chromadb
import json
import argparse
import sys

def main():
    # Initialize ChromaDB client
    try:
        client = chromadb.PersistentClient(path="./chroma_db")
        collection = client.get_collection("recipes")
    except Exception as e:
        print(f"Error: Could not connect to ChromaDB at ./chroma_db. {e}")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Inspect the NourishAI recipe database")
    parser.add_argument("--list", type=int, help="Number of recipes to list (default: 10)", default=10)
    parser.add_argument("--search", type=str, help="Search recipes by title (partial match)")
    parser.add_argument("--category", type=str, help="Filter by category (e.g., 'Beef', 'Dessert')")
    parser.add_argument("--full", action="store_true", help="Show full ingredients and instructions")
    parser.add_argument("--stats", action="store_true", help="Show category and area distribution")

    args = parser.parse_args()

    total_count = collection.count()
    print(f"\n{'='*50}")
    print(f"🌿 NourishAI Database Status")
    print(f"Total recipes: {total_count}")
    print(f"{'='*50}\n")

    if args.stats:
        show_stats(collection)
        return

    if args.search:
        # Fetch all to do partial matching in Python (easiest for small-medium DBs)
        all_data = collection.get()
        matches = [i for i, m in enumerate(all_data['metadatas']) if args.search.lower() in m.get('title', '').lower()]
        print(f"Found {len(matches)} matches for '{args.search}':\n")
        for i in matches[:args.list]:
            print_recipe(all_data['metadatas'][i], args.full)
    
    elif args.category:
        results = collection.get(where={"category": args.category}, limit=args.list)
        print(f"Showing up to {args.list} recipes in category '{args.category}':\n")
        for meta in results['metadatas']:
            print_recipe(meta, args.full)
            
    else:
        results = collection.get(limit=args.list)
        print(f"Showing the last {len(results['ids'])} recipes added:\n")
        for meta in results['metadatas']:
            print_recipe(meta, args.full)

def show_stats(collection):
    all_data = collection.get()
    categories = {}
    areas = {}
    for meta in all_data['metadatas']:
        cat = meta.get('category', 'Unknown')
        area = meta.get('area', 'Unknown')
        categories[cat] = categories.get(cat, 0) + 1
        areas[area] = areas.get(area, 0) + 1
    
    print("Categories:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {cat}: {count}")
    
    print("\nAreas/Cuisines:")
    for area, count in sorted(areas.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {area}: {count}")

def print_recipe(meta, full=False):
    title = meta.get('title', 'Unknown')
    cat = meta.get('category', 'N/A')
    
    print(f" ● [{cat}] {title}")
    
    if full:
        # Define fields we want to format specially or exclude from the generic loop
        formatted_fields = ['ingredients', 'instructions', 'title', 'category']
        
        # 1. Print simple metadata fields first
        for key, value in sorted(meta.items()):
            if key not in formatted_fields:
                print(f"   {key.capitalize()}: {value}")
        
        # 2. Print Ingredients with formatting
        print(f"   Ingredients:")
        try:
            ings = json.loads(meta.get('ingredients', '[]'))
            for ing in ings:
                if isinstance(ing, dict):
                    print(f"     - {ing.get('qty')} {ing.get('item')}")
                else:
                    print(f"     - {ing}")
        except:
            print(f"     - {meta.get('ingredients')}")
            
        # 3. Print Instructions with formatting
        print(f"   Instructions:")
        instructions = meta.get('instructions', '')
        # Truncate for readability but show a good chunk
        print(f"     {instructions[:1000]}..." if len(instructions) > 1000 else f"     {instructions}")
    else:
        area = meta.get('area', 'Unknown')
        print(f"   Origin: {area}")
    
    print("-" * 50)

if __name__ == "__main__":
    main()
