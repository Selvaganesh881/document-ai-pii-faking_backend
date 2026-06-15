from __future__ import annotations

import asyncio
import logging

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from pydantic import BaseModel, ConfigDict
from settings import get_settings
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    Pipeline,
    pipeline,
)

logger = logging.getLogger(__name__)


class PIIEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    entity_type: str
    start: int
    end: int


class PIIRecognizer:
    _instance: PIIRecognizer | None = None

    def __new__(cls) -> PIIRecognizer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False

        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            self._load_models()

    def _load_models(self) -> None:

        settings = get_settings()

        logger.info("Loading NER_01 Model From %s", settings.model_path)

        self._ner: Pipeline = pipeline(
            task="token-classification",
            model=AutoModelForTokenClassification.from_pretrained(
                str(settings.model_path)
            ),
            tokenizer=AutoTokenizer.from_pretrained(str(settings.model_path)),
            # model=AutoModelForTokenClassification.from_pretrained("FacebookAI/xlm-roberta-large-finetuned-conll03-english"),
            # tokenizer=AutoTokenizer.from_pretrained("FacebookAI/xlm-roberta-large-finetuned-conll03-english"),
            aggregation_strategy="simple",
            device=-1,
        )

        logger.info("Loading NER_02 Model From %s", settings.model_path_01)

        self._ner_01: Pipeline = pipeline(
            task="token-classification",
            model=AutoModelForTokenClassification.from_pretrained(
                str(settings.model_path_01)
            ),
            tokenizer=AutoTokenizer.from_pretrained(str(settings.model_path_01)),
            # model=AutoModelForTokenClassification.from_pretrained("FacebookAI/xlm-roberta-large-finetuned-conll03-english"),
            # tokenizer=AutoTokenizer.from_pretrained("FacebookAI/xlm-roberta-large-finetuned-conll03-english"),
            aggregation_strategy="simple",
            device=-1,
        )

        self._threshold: float = settings.model_threshold
        self._max_chunk: int = settings.max_chunk_size

        logger.info("NER Model Loaded")

        logger.info("Loading Presidio AnalyzerEngine")

        nlp_provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        )

        self._presidio: AnalyzerEngine = AnalyzerEngine(
            nlp_engine=nlp_provider.create_engine()
        )

        self._initialized = True

        logger.info("Presidio AnalyzerEngine Loaded")

    @staticmethod
    def _split_text_into_chunks(
        text: str, max_chunk_size: int
    ) -> list[tuple[str, int]]:

        if len(text) < max_chunk_size:
            return [(text, 0)]

        text_chunks: list[tuple[str, int]] = []

        start = 0

        while start < len(text):
            end = min(start + max_chunk_size, len(text))

            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            text_chunks.append((text[start:end], start))

            start = end + (1 if (end < len(text) and text[end] == " ") else 0)

        return text_chunks

    @staticmethod
    def _merge_entries(entities: list[PIIEntity]) -> list[PIIEntity]:
        if not entities:
            return []

        sorted_entities = sorted(entities, key=lambda e: (e.start, -(e.end - e.start)))

        merged: list[PIIEntity] = []
        last_end = -1

        for entity in sorted_entities:
            if entity.start >= last_end:
                merged.append(entity)
                last_end = entity.end
            elif entity.end > last_end:
                merged[-1] = entity
                last_end = entity.end

        return merged

    def _run_ner_pipeline(self, text: str, nlp_pipeline: Pipeline) -> list[PIIEntity]:
        """Generic processor that runs a given Hugging Face pipeline over text chunks."""
        chunks = self._split_text_into_chunks(text=text, max_chunk_size=self._max_chunk)
        entities: list[PIIEntity] = []

        ner_map: dict[str, str] = {
            # Standard CoNLL fallbacks
            "PER": "PERSON",
            "ORG": "ORGANIZATION",
            "LOC": "LOCATION",
        }

        for chunk_text, chunk_overlap in chunks:
            ner_result: list[dict] = nlp_pipeline(chunk_text)

            for entity in ner_result:
                score = float(entity["score"])
                if score < self._threshold:
                    continue

                raw_tag = str(entity["entity_group"]).upper()

                clean_tag = raw_tag.rstrip("0123456789")

                entities.append(
                    PIIEntity(
                        text=str(entity["word"]).strip(),
                        entity_type=ner_map.get(clean_tag, clean_tag),
                        start=entity["start"] + chunk_overlap,
                        end=entity["end"] + chunk_overlap,
                    )
                )

        return entities

    def _run_presidio(self, text: str) -> list[PIIEntity]:

        entities: list[PIIEntity] = []

        presidio_result: list[RecognizerResult] = self._presidio.analyze(
            text=text,
            entities=[
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                # "DATE_TIME",
                "IP_ADDRESS",
                "URL",
                "US_SSN",
                "IBAN_CODE",
                "CREDIT_CARD",
                "US_BANK_NUMBER",
            ],
            language="en",
        )

        entities = [
            PIIEntity(
                text=text[result.start : result.end],
                entity_type=result.entity_type,
                start=result.start,
                end=result.end,
            )
            for result in presidio_result
            if result.score >= self._threshold
        ]

        return entities

    def _analyze_sync(self, text: str) -> list[PIIEntity]:

        ner_entities = self._run_ner_pipeline(text=text, nlp_pipeline=self._ner)
        ner_01_entities = self._run_ner_pipeline(text=text, nlp_pipeline=self._ner_01)
        persidio_entities = self._run_presidio(text=text)

        merged_entities = self._merge_entries(
            ner_entities + ner_01_entities + persidio_entities
        )

        logger.info("No PII Entities Recognized is %d", len(merged_entities))

        return merged_entities

    async def analyze(self, text: str) -> list[PIIEntity]:

        if not text or not text.strip():
            return []

        return await asyncio.to_thread(self._analyze_sync, text)
