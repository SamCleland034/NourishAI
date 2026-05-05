import os
import json
import chromadb
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv

# Aggressive env loading
load_dotenv()
load_dotenv("../.env")

# --- CONFIG ---
CHROMA_PATH = "./chroma_db"
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "recipes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
DIMENSION = 1536 # OpenAI text-embedding-3-small dimension

if OPENAI_API_KEY:
    print(f"OpenAI Key found: {OPENAI_API_KEY[:5]}...{OPENAI_API_KEY[-5:]}")
    oa_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    print("FATAL ERROR: No OPENAI_API_KEY found in ../.env or current .env")
    exit(1)

def get_embedding(text):
    try:
        res = oa_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        return res.data[0].embedding
    except Exception as e:
        print(f"Error embedding chunk: {e}")
        return None

def migrate():
    # 1. Initialize Clients
    print("\nConnecting to ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        collection = chroma_client.get_collection("recipes")
    except:
        print("Error: recipes collection not found in ChromaDB.")
        return

    print("Connecting to Pinecone...")
    if not PINECONE_API_KEY:
        print("Error: PINECONE_API_KEY not found in environment.")
        return
    
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    # Check if index exists and has correct dimensions
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    index_exists = PINECONE_INDEX_NAME in existing_indexes
    
    if index_exists:
        try:
            idx_info = pc.describe_index(PINECONE_INDEX_NAME)
            if idx_info.dimension != DIMENSION:
                print(f"Index {PINECONE_INDEX_NAME} has wrong dimension ({idx_info.dimension}). Deleting and recreating for {DIMENSION}...")
                pc.delete_index(PINECONE_INDEX_NAME)
                index_exists = False
        except Exception as e:
            print(f"Error checking index: {e}. Recreating...")
            pc.delete_index(PINECONE_INDEX_NAME)
            index_exists = False

    if not index_exists:
        print(f"Creating Pinecone index: {PINECONE_INDEX_NAME} (dimension {DIMENSION})...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
    
    index = pc.Index(PINECONE_INDEX_NAME)

    # 2. Fetch all data from Chroma
    print("Fetching data from ChromaDB...")
    all_data = collection.get()
    ids = all_data['ids']
    metadatas = all_data['metadatas']
    documents = all_data['documents']

    print(f"Found {len(ids)} recipes to migrate.")

    # 3. Migrate in batches
    batch_size = 50
    for i in tqdm(range(0, len(ids), batch_size)):
        batch_ids = ids[i:i+batch_size]
        batch_metas = metadatas[i:i+batch_size]
        batch_docs = documents[i:i+batch_size]
        
        vectors_to_upsert = []
        for j in range(len(batch_ids)):
            content = f"{batch_metas[j].get('title', '')}\n{batch_docs[j]}"
            embedding = get_embedding(content)
            
            if embedding:
                clean_meta = {}
                for k, v in batch_metas[j].items():
                    if isinstance(v, (str, int, float, bool)):
                        clean_meta[k] = v
                    elif isinstance(v, list):
                        clean_meta[k] = [str(item) for item in v]
                    else:
                        clean_meta[k] = str(v)
                
                vectors_to_upsert.append({
                    "id": batch_ids[j],
                    "values": embedding,
                    "metadata": clean_meta
                })
        
        if vectors_to_upsert:
            index.upsert(vectors=vectors_to_upsert)

    print("\n✅ Migration complete!")
    print(f"Status: {index.describe_index_stats()}")

if __name__ == "__main__":
    migrate()
