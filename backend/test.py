from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client.http import models
from dotenv import load_dotenv

load_dotenv()

def test_retrieve_with_filters(query: str, top_k: int = 3, filters: dict = None):
    """
    query   -> user query string
    top_k   -> number of results to fetch
    filters -> metadata filters, e.g. {"company_name": "Samsung"}
    """
    try:
        embedding_model = OpenAIEmbeddings(model="text-embedding-3-large")

        # Connect to Qdrant collection
        vectorstore = QdrantVectorStore.from_existing_collection(
            url="http://localhost:6333",
            collection_name="learn_vector2",
            embedding=embedding_model,
        )

        # Build filter if provided
        qdrant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.company_name",
                    match=models.MatchValue(value="Samsung")
                ),
                models.FieldCondition(
                    key="metadata.product_code",
                    match=models.MatchValue(value="Refrigerator ‒ RF27T5201 / RF27T5241")
                )
            ]
        )
        # Run similarity search
        results = vectorstore.similarity_search(
            query=query,
            k=top_k,
            filter=qdrant_filter
        )

        print(f"\n🔍 Query: {query}")
      

        print(results)
    except Exception as e:
        print(f"❌ Retrieval Error: {e}")

test_retrieve_with_filters("how to start refregerator?", )