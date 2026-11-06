import logging
from typing import List, Dict, Any
from fastapi import FastAPI # type: ignore[import-untyped]
from transformers_interpret import SequenceClassificationExplainer # type: ignore[import]

logger = logging.getLogger(__name__)

def explain_tokens(app: FastAPI, text: str) -> list:
    """Generates token-level explainability for the BERT Phishing model using transformers-interpret."""
    try:
        model_pipeline = getattr(app.state, "phishing_model", None)
        if model_pipeline is None:
            return []
            
        # SequenceClassificationExplainer needs the underlying model and tokenizer
        explainer = SequenceClassificationExplainer(
            model=model_pipeline.model,
            tokenizer=model_pipeline.tokenizer
        )
        
        # Get word attributions
        # We limit the text length for performance
        safe_text = str(text)[:512] # type: ignore[index]
        word_attributions = explainer(safe_text)
        
        # Results format: [('word', score), ...]
        from typing import cast
        results: List[Dict[str, Any]] = []
        for item in word_attributions: # type: ignore[attr-defined]
            t_item = cast(tuple, item)
            word, score = t_item[0], t_item[1]
            if word not in ["[CLS]", "[SEP]"]:
                results.append({
                    "token": word,
                    "score": float(abs(score)) # Taking absolute as we want top contributing tokens
                })
                
        # Sort by score descending and take top 8
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:8]
    except Exception as e:
        logger.error(f"Token explanation failed: {e}")
        return []
