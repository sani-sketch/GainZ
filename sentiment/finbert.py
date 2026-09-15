from __future__ import annotations

from functools import lru_cache

from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch


MODEL_NAME = "ProsusAI/finbert"


@lru_cache(maxsize=1)
def _load_model():
    """
    Load FinBERT once and reuse it.
    """
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME
    )

    model.eval()

    return tokenizer, model


def score_text(text: str) -> dict:
    """
    Score financial sentiment.

    Returns approximately:

    {
        "positive": 0.82,
        "negative": 0.06,
        "neutral": 0.12,
        "score": 0.76,
        "label": "POSITIVE"
    }

    score ranges from -1 to +1.
    """

    text = str(text or "").strip()

    if not text:
        return {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 1.0,
            "score": 0.0,
            "label": "NEUTRAL",
        }

    tokenizer, model = _load_model()

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    )

    with torch.no_grad():
        outputs = model(**inputs)

    probabilities = torch.softmax(
        outputs.logits,
        dim=-1,
    )[0]

    labels = model.config.id2label

    results = {}

    for index, probability in enumerate(probabilities):
        label = labels[index].lower()

        results[label] = float(
            probability.item()
        )

    positive = results.get("positive", 0.0)
    negative = results.get("negative", 0.0)
    neutral = results.get("neutral", 0.0)

    score = positive - negative

    if score >= 0.25:
        label = "POSITIVE"
    elif score <= -0.25:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"

    return {
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "score": score,
        "label": label,
    }