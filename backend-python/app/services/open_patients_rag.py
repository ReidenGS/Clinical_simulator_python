from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RetrievedCase:
    case_id: str
    description: str
    summary: str


class OpenPatientsRagService:
    """Samples a real-world case description from local Open-Patients data and summarizes it."""

    def __init__(self, data_root: Path | None = None, seed: int | None = None) -> None:
        default_root = Path(__file__).resolve().parents[3] / 'data' / 'open_patients'
        self.data_root = data_root or default_root
        self._rng = random.Random(seed)
        self._dataset = None
        self._load_failed = False

    def sample_case(self) -> RetrievedCase | None:
        dataset = self._load_dataset()
        if dataset is None:
            return None

        total = len(dataset)
        if total <= 0:
            return None

        for _ in range(8):
            idx = self._rng.randrange(total)
            row = dataset[idx]
            description = str(row.get('description') or '').strip()
            if not description:
                continue
            case_id = str(row.get('_id') or idx)
            summary = self._summarize_description(description)
            if summary:
                return RetrievedCase(case_id=case_id, description=description, summary=summary)
        return None

    def _load_dataset(self):
        if self._dataset is not None:
            return self._dataset
        if self._load_failed:
            return None

        try:
            from datasets import load_from_disk
        except Exception:
            self._load_failed = True
            return None

        if not self.data_root.exists():
            self._load_failed = True
            return None

        try:
            loaded = load_from_disk(str(self.data_root))
            dataset = loaded['train'] if hasattr(loaded, 'keys') and 'train' in loaded else loaded
            self._dataset = dataset
            return dataset
        except Exception:
            self._load_failed = True
            return None

    def _summarize_description(self, description: str, max_sentences: int = 6, max_chars: int = 900) -> str:
        compact = re.sub(r'\s+', ' ', description).strip()
        if not compact:
            return ''

        # Keep sentence boundaries simple and robust.
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', compact) if s.strip()]
        if not sentences:
            return compact[:max_chars]

        keywords = {
            'age': 3,
            'year-old': 3,
            'male': 2,
            'female': 2,
            'complains': 4,
            'presents': 4,
            'reports': 4,
            'pain': 3,
            'fever': 3,
            'cough': 3,
            'shortness of breath': 4,
            'dyspnea': 4,
            'nausea': 3,
            'vomiting': 3,
            'onset': 3,
            'duration': 3,
            'history': 3,
            'medication': 2,
            'smoker': 2,
            'family': 2,
            'worse': 2,
            'better': 2,
            'denies': 2,
            'exam': 3,
            'vitals': 3,
        }

        scored: list[tuple[int, int, str]] = []
        for idx, sent in enumerate(sentences):
            lowered = sent.lower()
            score = 0
            for token, weight in keywords.items():
                if token in lowered:
                    score += weight
            # The first sentence in clinical notes nearly always contains the most
            # important demographic + chief complaint information, so give it a
            # strong positional boost. Subsequent sentences decay quickly.
            if idx == 0:
                score += 5
            elif idx == 1:
                score += 2
            elif idx == 2:
                score += 1
            scored.append((score, idx, sent))

        scored.sort(key=lambda item: (-item[0], item[1]))
        chosen = sorted(scored[:max_sentences], key=lambda item: item[1])

        summary = ' '.join(sent for _, _, sent in chosen)
        summary = re.sub(r'\s+', ' ', summary).strip()
        return summary[:max_chars]
