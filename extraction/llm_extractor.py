from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import APIConnectionError

# Import settings
from settings import get_settings

logger = logging.getLogger(__name__)


class LLMExtractor:
    def __init__(self, endpoint_url: Optional[str] = None) -> None:

        settings = get_settings()

        # Priority: 1. Passed argument (for local testing), 2. .env variable
        self.base_url = endpoint_url or settings.LLM_ENDPOINT
        self.model_id = settings.LLM_MODEL

        self.llm = ChatOpenAI(
            # base_url=self.base_url,
            api_key=settings.LLM_API_KEY,  # Pulled dynamically
            model=self.model_id,
            temperature=0.0,
            timeout=settings.LLM_TIMEOUT,
            # max_tokens=2048,
            max_retries=3,
            model_kwargs={"top_p": 0.1},
        )

        self._fixed_system_prompt = """
        You are an elite, deterministic data extraction engine. Your sole purpose is to analyze documents and output structured JSON data that strictly conforms to a provided schema.

        CRITICAL RULES:
        1. STRICT ADHERENCE: Your output must be a single, valid JSON object matching the exact structure, keys, and data types of the requested schema.
        2. NO HALLUCINATION: Extract only the data explicitly present in the document. Do not guess, infer, or calculate missing values.
        3. MISSING DATA: If a requested parameter is completely absent from the text, you must output `null` for that key (or "NOT_FOUND" if the schema strictly requires a string type). Do not omit the key from the JSON.
        4. NO CHATTER: Output ONLY the raw JSON object. Do not include markdown code blocks (e.g., ```json), preambles, explanations, or conversational text.
                
        """

    async def extract_structured_data(
        self, text_payload: str, user_instruction: str, json_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes the extraction pipeline. Converts the masked markdown and user instructions
        into a strict JSON object matching the requested schema.
        """
        if not text_payload.strip():
            logger.warning("Empty text string supplied to LangChain Extraction layer.")
            return {}

        # Dynamic template that sandwiches the user's instruction and the masked document
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self._fixed_system_prompt),
                (
                    "human",
                    "{user_instruction}\n\n--- START DOCUMENT ---\n{text_payload}\n--- END DOCUMENT ---",
                ),
            ]
        )

        try:
            # Bind the JSON schema directly to the LLM for grammar-guided decoding
            structured_llm = self.llm.with_structured_output(json_schema)
            chain = prompt | structured_llm

            logger.info("Invoking LangChain structured extraction chain...")
            result = await chain.ainvoke(
                {"user_instruction": user_instruction, "text_payload": text_payload}
            )

            logger.info("Structured parsing successfully handled by Qwen3-4B.")
            return result
        except APIConnectionError as api_err:
            logger.error(
                "API connection error during LLM extraction: %s. Check endpoint URL and network connectivity.",
                str(api_err),
            )
            return {"error": f"API connection failure: {str(api_err)}"}
        except Exception as e:
            logger.error(
                "Unhandled execution error in LangChain extraction wrapper: %s", str(e)
            )
            return {"error": f"Extraction failure: {str(e)}"}
