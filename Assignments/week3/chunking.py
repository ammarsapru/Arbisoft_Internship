
from langchain_text_splitters import RecursiveCharacterTextSplitter

def get_chunks(docs):
    print("chunking methodoly called")
    text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=200, add_start_index=True
    )
    all_splits = text_splitter.split_documents(docs)
    return all_splits
