import time

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore


def build_vector_store(
    embeddings: Embeddings,
    docs: list[Document],
    batch_size: int = 32,
    max_retries: int = 3,
) -> InMemoryVectorStore:
    """Embed docs into an InMemoryVectorStore in batches, retrying failed batches.

    Batching means a transient Ollama failure (e.g. the model runner crashing
    while swapping models) only loses one batch instead of the whole corpus.
    """
    store = InMemoryVectorStore(embeddings)
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        for attempt in range(1, max_retries + 1):
            try:
                store.add_documents(documents=batch)
                break
            except Exception as exc:
                if attempt == max_retries:
                    raise
                wait = 2 * attempt
                print(
                    f"  batch {start}-{start + len(batch)} failed "
                    f"(attempt {attempt}/{max_retries}): {exc}; retrying in {wait}s"
                )
                time.sleep(wait)
    return store
