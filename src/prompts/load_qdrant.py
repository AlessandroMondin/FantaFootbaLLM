import glob
import json

from qdrant_client import models, QdrantClient
from sentence_transformers import SentenceTransformer

encoder = SentenceTransformer('all-MiniLM-L6-v2')

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

qdrant = QdrantClient(":memory:") # Create in-memory Qdrant instance

documents = []
for document in glob.glob("src/prompts/fantasy_footaball/rag_queries/*.json"):
    with open(document, "r") as f:
        document = json.load(f)
        documents.append(document)

# Create collection to store books
qdrant.recreate_collection(
    collection_name="fantasy_football_queries_embeds",
    vectors_config=models.VectorParams(
        size=encoder.get_sentence_embedding_dimension(), # Vector size is defined by used model
        distance=models.Distance.COSINE
    )
)

# Let's vectorize descriptions and upload to qdrant

qdrant.upload_records(
    collection_name="fantasy_football_queries_embeds",
    records=[
        models.Record(
            id=idx,
            vector=encoder.encode(doc["question"]).tolist(),
            payload=doc
        ) for idx, doc in enumerate(documents)
    ]
)

hits = qdrant.search(
    collection_name="fantasy_football_queries_embeds",
    query_vector=encoder.encode("Which is the fantasy grade average of leao in the first part of the season vs in the second part of the season?").tolist(),
    limit=5
)
for hit in hits:
    print(hit.payload["question"], "score:", hit.score)