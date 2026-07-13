#import libraries
from pathlib import Path
from dotenv import load_dotenv

#import methods
from chunking import get_chunks
from get_embeddings import get_qwen_embed, get_snowfl_embed
from extract_pdf import load_pdf_pages
from store_utils import build_vector_store

load_dotenv()

print("pdf extraction in place....")

#parse pdf
pdf_path = Path(__file__).parent / "data" / "nke-10k-2023.pdf"
parsed_pdf = load_pdf_pages(str(pdf_path))
print(len(parsed_pdf))

#get chunks
print("-------------------------")
print("Chunking called")
chunks = get_chunks(parsed_pdf)
print(len(chunks))

#build one vector store per embedding model
models = {
    "qwen3-embedding:0.6b": get_qwen_embed(),
    "snowflake-arctic-embed:latest": get_snowfl_embed(),
}
stores = {}
for name, embeddings in models.items():
    print("-------------------------")
    print(f"Embedding chunks with {name}...")
    stores[name] = build_vector_store(embeddings, chunks)

#run the same test query against each store to compare results
query = "How were Nike's revenues in fiscal 2023?"
for name, store in stores.items():
    print("=========================")
    print(f"Top results from {name} for: {query!r}")
    results = store.similarity_search_with_score(query, k=3)
    for doc, score in results:
        snippet = " ".join(doc.page_content.split())[:200]
        print(f"  [page {doc.metadata['page']}, score {score:.4f}] {snippet}")



