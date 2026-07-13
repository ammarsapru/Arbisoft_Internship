from langchain_ollama import OllamaEmbeddings


def get_qwen_embed():
    qwen_embeddings = OllamaEmbeddings(
        model = "qwen3-embedding:0.6b",
        dimensions= 1024
    )
    return qwen_embeddings

def get_snowfl_embed():
    snowflake_embeddings = OllamaEmbeddings(
        model = "snowflake-arctic-embed:latest"
    )
    return snowflake_embeddings

# models = ["snowflake-arctic-embed:latest","qwen3-embedding:0.6b" ]