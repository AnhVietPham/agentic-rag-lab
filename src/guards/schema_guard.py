"""Schema Guard — input/output validation layer.

Provides:
- Prompt injection detection
- Input length enforcement
- Disclaimer enforcement for sensitive topics (financial, medical, legal)
"""

import logging
import re 
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Prompt injection / jailbreak patterns (regex)
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?",
    r"forget\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?",
    r"you\s+are\s+now\s+(?:a\s+)?(?:different|new|another|evil|uncensored)",
    r"act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:a\s+)?(?:different|evil|unrestricted|DAN)",
    r"\bDAN\s+mode\b",
    r"\bjailbreak\b",
    r"pretend\s+(?:you\s+are|to\s+be)\s+(?:an?\s+)?(?:evil|unrestricted|unfiltered)",
    r"<\s*script\s*>",
    r"\bsystem\s*:\s*you\s+are\b",
    r"disregard\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?",
]

# Keywords that indicate financial/sensitive content requiring disclaimer
FINANCIAL_KEYWORDS = [
    r"\bbuy\s+stock\b",
    r"\bsell\s+stock\b",
    r"\binvest(?:ment)?\s+advice\b",
    r"\bportfolio\s+(?:advice|management|recommendation)\b",
    r"\btrading\s+strategy\b",
    r"\bfinancial\s+advice\b",
    r"\bshould\s+i\s+(?:buy|sell|invest)\b",
    r"\bstock\s+recommendation\b",
    r"\bcrypto(?:currency)?\s+(?:advice|investment|trading)\b",
    r"\bforex\s+trading\b",
    r"\bget\s+rich\b",
]

DISCLAIMER_TEXT = (
    "\n\n---\n"
    "⚠️ **Disclaimer**: This information is sourced from academic research papers "
    "and is provided for educational purposes only. It does not constitute financial, "
    "legal, or medical advice. Always consult qualified professionals for specific guidance."
)

@dataclass
class ValidationResult: 
    is_valid: bool 
    reason: Optional[str] = None
    cleaned_value: Optional[str] = None

class SchemaGuard:
    """Input/output validation and disclaimer enforcement.

    :param max_input_length: Maximum allowed query length in characters
    :param enable_injection_check: Whether to scan for prompt injection patterns
    :param enable_disclaimer: Whether to auto-append disclaimer for sensitive topics
    """

    def __init__(
        self, 
        max_input_length: int = 1000, 
        enable_injection_check: bool = True,
        enable_disclaimer: bool = True
    ) -> None: 
        self.max_input_length = max_input_length
        self.enable_injection_check = enable_injection_check
        self.enable_disclaimer = enable_disclaimer

        self._injection_re = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
        self._financial_re = [re.compile(p, re.IGNORECASE) for p in FINANCIAL_KEYWORDS]

        # ------------------------------------------------------------------
        # Input validation methods
        # ------------------------------------------------------------------
        def validate_input(self, query: str) -> ValidationResult: 
            """Validate user query before processing.

            :param query: Raw user input
            :returns: ValidationResult — is_valid=False blocks the request
            """
            if not query or not query.strip(): 
                return ValidationResult(is_valid=False, reason="Query cannot be empty")

            if len(query) > self.max_input_length:
                return ValidationResult(
                    is_valid=False,
                    reason=f"Query exceeds maximum length of {self.max_input_length} characters (got {len(query)})",
                )
            
            if self.enable_injection_check:
                for pattern in self._injection_re:
                    if pattern.search(query):
                        logger.warning("Injection pattern detected: %s", pattern.pattern)
                        return ValidationResult(
                            is_valid=False,
                            reason="Query contains potentially harmful content and cannot be processed",
                        )

            return ValidationResult(is_valid=True, cleaned_value=query.strip())

        # ------------------------------------------------------------------
        # Output validation / disclaimer enforcement
        # ------------------------------------------------------------------
        def enforce_disclaimer(self, answer: str, query: str = "") -> str:
            """Append disclaimer if query or answer touches sensitive topics.

            :param answer: LLM-generated answer
            :param query: Original user query (used for topic detection)
            :returns: Answer with disclaimer appended if needed
            """
            if not self.enable_disclaimer:
                return answer

            combined = (query + " " + answer).lower()
            for pattern in self._financial_re:
                if pattern.search(combined):
                    if DISCLAIMER_TEXT not in answer:
                        logger.debug("Appending disclaimer for sensitive content")
                        answer = answer + DISCLAIMER_TEXT
                    break

            return answer

        def requires_disclaimer(self, query: str, answer: str = "") -> bool:
            """Check whether the query/answer combination needs a disclaimer.

            :returns: True if disclaimer should be added
            """
            combined = (query + " " + answer).lower()
            return any(p.search(combined) for p in self._financial_re) 


