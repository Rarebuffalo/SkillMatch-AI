import json
import math
import os
import re
from pathlib import Path


# Resolve catalog path relative to project root at data/shl_product_catalog.json
BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = str(BASE_DIR / "data" / "shl_product_catalog.json")
if not os.path.exists(CATALOG_PATH):
    # Search root folder fallback
    CATALOG_PATH = "shl_product_catalog.json"
    if not os.path.exists(CATALOG_PATH):
        CATALOG_PATH = "/home/Krishna-Singh/Downloads/shl_product_catalog.json"



class BM25Search:
    def __init__(self, corpus_docs, b=0.75, k1=1.5):
        self.b = b
        self.k1 = k1
        self.corpus_size = len(corpus_docs)
        self.avg_doc_len = 0
        self.doc_lengths = []
        self.doc_term_freqs = []
        self.df = {}
        self.idf = {}
        self.corpus_docs = corpus_docs
        
        self._initialize()

    def _tokenize(self, text):
        if not text:
            return []
        text = text.lower()
        # Keep alphanumeric characters
        tokens = re.findall(r'\b[a-z0-9\+\#\-\_]+\b', text)
        return tokens

    def _initialize(self):
        total_len = 0
        for doc in self.corpus_docs:
            # We index name, description, and keys
            content_parts = [
                doc.get("name", "") * 3,  # Boost name matches
                doc.get("description", ""),
                " ".join(doc.get("keys", [])) * 2  # Boost key matches
            ]
            tokens = self._tokenize(" ".join(content_parts))
            self.doc_lengths.append(len(tokens))
            total_len += len(tokens)
            
            # Compute term frequencies for this document
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self.doc_term_freqs.append(tf)
            
            # Document frequency
            for token in tf.keys():
                self.df[token] = self.df.get(token, 0) + 1
                
        self.avg_doc_len = total_len / self.corpus_size if self.corpus_size > 0 else 1
        
        # Calculate IDF
        for token, freq in self.df.items():
            # BM25 IDF formula
            self.idf[token] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def score(self, query, doc_idx):
        query_tokens = self._tokenize(query)
        score = 0.0
        doc_len = self.doc_lengths[doc_idx]
        tf = self.doc_term_freqs[doc_idx]
        
        for token in query_tokens:
            if token not in self.idf:
                continue
            token_tf = tf.get(token, 0)
            idf = self.idf[token]
            
            numerator = token_tf * (self.k1 + 1)
            denominator = token_tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))
            score += idf * (numerator / denominator)
            
        return score


class CatalogManager:
    def __init__(self):
        self.catalog = []
        self.search_engine = None
        self.load_catalog()

    def map_test_type(self, keys):
        if not keys:
            return "K"
        keys_str = " ".join(keys).lower()
        # Priority order: most specific first
        if "personality & behavior" in keys_str or "personality & behaviour" in keys_str:
            return "P"
        if "ability & aptitude" in keys_str:
            return "A"
        if "simulation" in keys_str:
            return "S"
        if "biodata" in keys_str or "situational judgment" in keys_str:
            return "B"
        if "competenc" in keys_str:
            return "C"
        if "development" in keys_str or "360" in keys_str:
            return "D"
        if "knowledge & skills" in keys_str:
            return "K"

        # String-content fallbacks
        if "personality" in keys_str or "behavior" in keys_str:
            return "P"
        if "ability" in keys_str or "aptitude" in keys_str or "reasoning" in keys_str:
            return "A"

        return "K"

    def load_catalog(self):
        if not os.path.exists(CATALOG_PATH):
            raise FileNotFoundError(f"Catalog file not found at {CATALOG_PATH}")
            
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            raw_catalog = json.load(f, strict=False)
            
        self.catalog = []
        for item in raw_catalog:
            # Map basic fields
            entity_id = item.get("entity_id", "")
            name = item.get("name", "")
            link = item.get("link", "")
            description = item.get("description", "")
            duration = item.get("duration", "")
            languages = item.get("languages", [])
            keys = item.get("keys", [])
            job_levels = item.get("job_levels", [])
            
            test_type = self.map_test_type(keys)
            
            self.catalog.append({
                "entity_id": entity_id,
                "name": name,
                "url": link,
                "description": description,
                "duration": duration,
                "languages": languages,
                "keys": keys,
                "job_levels": job_levels,
                "test_type": test_type
            })
            
        # Initialize search engine
        self.search_engine = BM25Search(self.catalog)

    def retrieve(self, state, query_str=None, top_k=20):
        """
        Retrieves top_k candidates based on state constraints and optional query string.
        """
        # 1. State extraction
        role = state.role_title
        skills = " ".join(state.technical_skills)
        seniority = state.seniority
        needs_personality = state.needs_personality
        needs_cognitive = state.needs_cognitive
        
        # Construct search query from state
        search_terms = []
        if query_str:
            search_terms.append(query_str)
        if role:
            search_terms.append(role)
        if skills:
            search_terms.append(skills)
        if seniority:
            search_terms.append(seniority)
            
        search_query = " ".join(search_terms)
        
        scored_candidates = []
        for idx, doc in enumerate(self.catalog):
            # Apply pre-filtering based on category triggers
            # If user explicitly requested only personality but product is not personality, we don't block entirely but we can penalize/filter if strict.
            # Let's filter strictly if state needs specific categories
            doc_type = doc["test_type"]
            
            # Let's compute BM25 score
            bm25_score = self.search_engine.score(search_query, idx)
            
            # Compute metadata matching score
            metadata_score = 0.0
            
            # Boost matches based on target assessment type requests
            if needs_personality and doc_type == "P":
                metadata_score += 3.0
            if needs_cognitive and doc_type == "A":
                metadata_score += 3.0
                
            # Boost if skills overlaps with name/keys/description
            for skill in state.technical_skills:
                if skill.lower() in doc["name"].lower():
                    metadata_score += 2.0
                elif skill.lower() in doc["description"].lower():
                    metadata_score += 0.5
            
            # Boost if seniority matches job_levels
            if seniority:
                for lvl in doc["job_levels"]:
                    if seniority.lower() in lvl.lower():
                        metadata_score += 1.0
                        break

            # Boost when domain-specific terms appear in the search query and match the document.
            # This prevents language-preference tokens (e.g. "spanish") from overshadowing
            # role-domain tokens (e.g. "hipaa", "medical", "healthcare") in retrieval.
            DOMAIN_BOOST_TERMS = [
                "hipaa", "medical", "healthcare", "health care", "clinical", "patient",
                "admin", "administrative", "office", "word", "excel",
                "manufacturing", "industrial", "plant", "safety", "dependability",
                "sales", "retail", "contact center", "customer service",
                "finance", "financial", "banking", "accounting",
                "engineering", "software", "developer", "coding",
            ]
            for term in DOMAIN_BOOST_TERMS:
                if term in search_query.lower():
                    doc_text = (doc["name"] + " " + doc["description"] + " " + " ".join(doc["keys"])).lower()
                    if term in doc_text:
                        metadata_score += 2.5
                        break  # one domain boost per document max

            # Final score
            final_score = bm25_score + metadata_score

            
            scored_candidates.append((doc, final_score))
            
        # Sort by score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Get top-k
        results = [item[0] for item in scored_candidates[:top_k]]
        return results

    def get_by_name(self, name):
        """
        Finds exact or closest name match in the catalog.
        """
        name_clean = name.strip().lower()
        
        # Exact check
        for item in self.catalog:
            if item["name"].lower() == name_clean:
                return item
                
        # Acronym check (e.g. OPQ32r matches "Occupational Personality Questionnaire OPQ32r")
        for item in self.catalog:
            if name_clean in item["name"].lower() or item["name"].lower() in name_clean:
                return item
                
        return None

    def match_and_populate(self, proposed_recommendations):
        """
        Cross-references list of proposed recommendations (just names) with the catalog.
        Populates complete correct fields and returns unique list.
        """
        valid_recs = []
        seen_urls = set()
        
        for rec in proposed_recommendations:
            if isinstance(rec, dict):
                rec_name = rec.get("name", "")
            else:
                rec_name = str(rec)
            catalog_item = self.get_by_name(rec_name)
            
            if catalog_item:
                url = catalog_item["url"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    valid_recs.append({
                        "name": catalog_item["name"],
                        "url": url,
                        "test_type": catalog_item["test_type"]
                    })
                    
        return valid_recs
