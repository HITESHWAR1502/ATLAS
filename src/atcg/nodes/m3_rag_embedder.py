"""
M3: RAG Embedder + Neon Semantic Search

Embeds function source code using Google Gemini embeddings and stores/queries
vectors in Neon with pgvector for semantic neighbor retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from atcg.config import ATCGConfig
from atcg.db.connection import NeonConnection
from atcg.state import ATCGState

logger = logging.getLogger(__name__)


class RAGEmbedder:
    """Handles embedding generation and semantic search via Neon + pgvector."""

    def __init__(self, config: ATCGConfig) -> None:
        self._config = config
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=config.llm.embedding_model,
            google_api_key=config.llm.api_key,
        )

    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a text string."""
        embedding = await self._embeddings.aembed_query(text)
        return embedding[:768]  # Force exact 768 dimensions for pgvector schema

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = await self._embeddings.aembed_documents(texts)
        return [emb[:768] for emb in embeddings]  # Force exact 768 dimensions

    async def store_embedding(
        self,
        db: NeonConnection,
        project_name: str,
        target_id: str,
        source_code: str,
        docstring: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a function embedding in Neon."""
        # Create embedding from source + docstring
        text_to_embed = source_code
        if docstring:
            text_to_embed = f"{docstring}\n\n{source_code}"

        embedding = await self.embed_text(text_to_embed)

        await db.execute(
            """
            INSERT INTO atcg_embeddings
                (project_name, target_id, source_code, docstring, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s::vector, %s::JSONB)
            ON CONFLICT (project_name, target_id)
            DO UPDATE SET
                source_code = EXCLUDED.source_code,
                docstring = EXCLUDED.docstring,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            (
                project_name,
                target_id,
                source_code,
                docstring,
                str(embedding),
                "{}",
            ),
        )

    async def find_semantic_neighbors(
        self,
        db: NeonConnection,
        project_name: str,
        query_text: str,
        limit: int = 5,
        exclude_target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find semantically similar functions using cosine similarity.

        Returns functions ordered by similarity (most similar first).
        """
        query_embedding = await self.embed_text(query_text)

        if exclude_target_id:
            results = await db.execute(
                """
                SELECT target_id, source_code, docstring, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM atcg_embeddings
                WHERE project_name = %s
                  AND target_id != %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    str(query_embedding),
                    project_name,
                    exclude_target_id,
                    str(query_embedding),
                    limit,
                ),
            )
        else:
            results = await db.execute(
                """
                SELECT target_id, source_code, docstring, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM atcg_embeddings
                WHERE project_name = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    str(query_embedding),
                    project_name,
                    str(query_embedding),
                    limit,
                ),
            )

        return results


async def m3_rag_embedder(
    state: ATCGState, config: ATCGConfig, db: NeonConnection
) -> ATCGState:
    """
    M3: RAG Embedder + Neon Semantic Search node.

    Embeds all extracted functions and finds semantic neighbors
    for context augmentation.

    Updates state with:
        - target_context.functions[].semantic_neighbors: Similar functions
    """
    project_context = state.get("project_context", {})
    project_name = project_context.get("project_name", "unknown")
    target_context = state.get("target_context", {})
    functions = target_context.get("functions", [])

    if not functions:
        logger.info("M3: No functions to embed")
        return state

    embedder = RAGEmbedder(config)

    import asyncio
    import json

    # ── Batch generate embeddings ─────────────────────────────────────────────
    texts_to_embed = [
        f"{func.get('name')}\n\n{func['source_code']}" for func in functions
    ]
    
    embeddings = []
    if texts_to_embed:
        try:
            embeddings = await embedder.embed_texts(texts_to_embed)
            logger.info(f"M3: Generated {len(embeddings)} embeddings in batch")
        except Exception as e:
            logger.warning(f"M3: Failed to generate batch embeddings: {e}")
            return state

    # ── Store embeddings and compute semantic neighbors in parallel ───────────
    async def process_function(func, embedding):
        # 1. Store
        try:
            await db.execute(
                """
                INSERT INTO atcg_embeddings
                    (project_name, target_id, source_code, docstring, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s::vector, %s::JSONB)
                ON CONFLICT (project_name, target_id)
                DO UPDATE SET
                    source_code = EXCLUDED.source_code,
                    docstring = EXCLUDED.docstring,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                (
                    project_name,
                    func["id"],
                    func["source_code"],
                    None,
                    str(embedding),
                    json.dumps({
                        "classification": func.get("classification"),
                        "complexity": func.get("cyclomatic_complexity"),
                        "dependencies": func.get("dependencies", []),
                    }),
                ),
            )
        except Exception as e:
            logger.warning(f"M3: Failed to store embedding for {func['id']}: {e}")

        # 2. Find neighbors
        try:
            neighbors = await db.execute(
                """
                SELECT target_id, source_code, docstring, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM atcg_embeddings
                WHERE project_name = %s
                  AND target_id != %s
                ORDER BY embedding <=> %s::vector
                LIMIT 3
                """,
                (
                    str(embedding),
                    project_name,
                    func["id"],
                    str(embedding),
                ),
            )
            func["semantic_neighbors"] = [
                {
                    "target_id": n["target_id"],
                    "similarity": float(n.get("similarity", 0)),
                    "source_snippet": n.get("source_code", "")[:200],
                }
                for n in neighbors
            ]
        except Exception as e:
            logger.warning(f"M3: Failed to find neighbors for {func['id']}: {e}")
            func["semantic_neighbors"] = []

    if embeddings:
        await asyncio.gather(
            *(process_function(f, emb) for f, emb in zip(functions, embeddings))
        )

    logger.info(f"M3: Embedded {len(functions)} functions, neighbors computed")

    return {
        **state,
        "target_context": {
            **target_context,
            "functions": functions,
        },
    }
