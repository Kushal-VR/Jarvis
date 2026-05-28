import os
import json
import logging
import numpy as np
from typing import List, Dict, Any

class SimpleVectorStore:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.logger = logging.getLogger("Jarvis.VectorStore")
        self.db_file = os.path.join(storage_path, "vector_db.json")
        self.items: List[Dict[str, Any]] = []
        
        # Ensure directory exists
        os.makedirs(self.storage_path, exist_ok=True)
        self.load()

    def load(self):
        """Loads vector database from JSON file."""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r") as f:
                    self.items = json.load(f)
                self.logger.info(f"Loaded {len(self.items)} memories from vector database.")
            except Exception as e:
                self.logger.error(f"Failed to load vector database: {e}")
                self.items = []
        else:
            self.items = []

    def save(self):
        """Saves vector database to JSON file."""
        try:
            with open(self.db_file, "w") as f:
                json.dump(self.items, f, indent=2)
            self.logger.debug("Vector database saved successfully.")
        except Exception as e:
            self.logger.error(f"Failed to save vector database: {e}")

    def add_item(self, text: str, embedding: List[float], metadata: dict = None):
        """Adds a memory item to the vector store."""
        if not embedding:
            self.logger.warning("Attempted to add memory item with empty embedding.")
            return
            
        self.items.append({
            "text": text,
            "embedding": embedding,
            "metadata": metadata or {}
        })
        self.save()

    def search(self, query_embedding: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Computes cosine similarity between query_embedding and all stored vectors.
        Returns the top_k most similar items.
        """
        if not self.items or not query_embedding:
            return []

        try:
            q_vec = np.array(query_embedding, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            
            if q_norm == 0:
                return []

            similarities = []
            for item in self.items:
                i_vec = np.array(item["embedding"], dtype=np.float32)
                i_norm = np.linalg.norm(i_vec)
                
                if i_norm == 0:
                    sim = 0.0
                else:
                    sim = float(np.dot(q_vec, i_vec) / (q_norm * i_norm))
                    
                similarities.append((sim, item))

            # Sort by similarity descending
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            results = []
            for sim, item in similarities[:top_k]:
                # Copy item and append similarity score
                res_item = item.copy()
                # Exclude raw embedding vectors from results to save memory/payload size
                res_item.pop("embedding", None)
                res_item["similarity"] = sim
                results.append(res_item)
                
            return results
        except Exception as e:
            self.logger.error(f"Vector search failed: {e}")
            return []
