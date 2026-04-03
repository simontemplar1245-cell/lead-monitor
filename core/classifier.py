"""
Lead Classifier
================
Uses Claude Haiku to classify leads as HOT/WARM/COLD.
Two-stage filtering:
  1. Fast keyword pre-filter (free, instant)
  2. Claude Haiku AI classification (cheap, accurate)
"""

import json
import re
import logging
from typing import Optional
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from config import (
    ANTHROPIC_API_KEY,
    PAIN_KEYWORDS,
    ALL_KEYWORDS,
    CLASSIFIER_SYSTEM_PROMPT,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
)

logger = logging.getLogger(__name__)


class LeadClassifier:
    """Two-stage lead classification: keyword pre-filter + Claude Haiku AI."""

    def __init__(self):
        if ANTHROPIC_API_KEY and Anthropic is not None:
            self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        else:
            self.client = None
            if Anthropic is None:
                logger.warning("anthropic package not installed - classifier will use keyword-only mode")
            else:
                logger.warning("No Anthropic API key set - classifier will use keyword-only mode")

    def keyword_prefilter(self, text: str) -> Optional[dict]:
        """
        Stage 1: Fast keyword matching.
        Returns matched keyword info or None if no match.
        This runs first to avoid sending irrelevant posts to Claude (saves money).
        """
        text_lower = text.lower()

        for category, keywords in PAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return {
                        "keyword_matched": keyword,
                        "keyword_category": category,
                    }
        return None

    def classify_with_ai(self, post_text: str, platform: str = "",
                         community: str = "") -> dict:
        """
        Stage 2: Send to Claude Haiku for intelligent classification.
        Returns classification dict with score, category, reasoning, suggested_reply.
        """
        if not self.client:
            # Fallback: keyword-only classification
            return self._keyword_only_classify(post_text)

        try:
            prompt = f"""Classify this social media post/comment as a potential lead for an AI chatbot and AI phone receptionist business.

Platform: {platform}
Community: {community}
Post content:
---
{post_text[:2000]}
---

Return ONLY a valid JSON object (no markdown, no code fences) with these fields:
- score: float 0.0-1.0
- category: "HOT", "WARM", or "COLD"
- reasoning: string (1-2 sentences)
- suggested_reply: string (helpful reply if HOT/WARM, empty string if COLD)
"""

            response = self.client.messages.create(
                model="claude-haiku-4-20250414",
                max_tokens=500,
                system=CLASSIFIER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text.strip()

            # Parse JSON from response (handle potential markdown code fences)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response_text)

            # Validate and normalize
            result["score"] = max(0.0, min(1.0, float(result.get("score", 0.0))))
            if result["score"] >= HOT_THRESHOLD:
                result["category"] = "HOT"
            elif result["score"] >= WARM_THRESHOLD:
                result["category"] = "WARM"
            else:
                result["category"] = "COLD"

            result.setdefault("reasoning", "")
            result.setdefault("suggested_reply", "")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse classifier response: {e}")
            return self._keyword_only_classify(post_text)
        except Exception as e:
            logger.error(f"Classifier API error: {e}")
            return self._keyword_only_classify(post_text)

    def _keyword_only_classify(self, text: str) -> dict:
        """Fallback classification using keywords only (no AI)."""
        match = self.keyword_prefilter(text)
        if not match:
            return {
                "score": 0.1,
                "category": "COLD",
                "reasoning": "No keyword match found",
                "suggested_reply": "",
            }

        category = match["keyword_category"]

        # Direct searches and receptionist problems score higher
        if category in ("direct_searches", "receptionist_problems"):
            return {
                "score": 0.7,
                "category": "WARM",
                "reasoning": f"Keyword match: '{match['keyword_matched']}' in category '{category}'",
                "suggested_reply": "",
                **match,
            }
        elif category in ("missed_calls", "lead_problems"):
            return {
                "score": 0.6,
                "category": "WARM",
                "reasoning": f"Keyword match: '{match['keyword_matched']}' in category '{category}'",
                "suggested_reply": "",
                **match,
            }
        else:
            return {
                "score": 0.4,
                "category": "COLD",
                "reasoning": f"Weak keyword match: '{match['keyword_matched']}' in category '{category}'",
                "suggested_reply": "",
                **match,
            }

    def classify(self, post_text: str, platform: str = "",
                 community: str = "") -> dict:
        """
        Full classification pipeline:
        1. Keyword pre-filter (fast, free)
        2. If keyword match found, send to Claude Haiku for scoring
        3. Return full classification result
        """
        # Stage 1: Keyword pre-filter
        keyword_match = self.keyword_prefilter(post_text)

        if not keyword_match:
            # No keyword match = definitely cold, skip AI call (saves money)
            return {
                "score": 0.0,
                "category": "COLD",
                "reasoning": "No relevant keywords detected",
                "suggested_reply": "",
                "keyword_matched": "",
                "keyword_category": "",
            }

        # Stage 2: AI classification (only for posts that passed keyword filter)
        result = self.classify_with_ai(post_text, platform, community)

        # Merge keyword data into result
        result["keyword_matched"] = keyword_match["keyword_matched"]
        result["keyword_category"] = keyword_match["keyword_category"]

        return result
