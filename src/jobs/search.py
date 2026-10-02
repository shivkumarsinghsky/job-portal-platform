"""Inverted index with BM25 ranking, field boosts, structured filters and facets.

Production: Elasticsearch/OpenSearch with the same concepts (analyzers, multi_match with boosts, bool filters,
terms aggregations). This in-process version makes the behaviour testable without a cluster.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from jobs.domain import Job, JobStatus

STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "of",
        "for",
        "in",
        "on",
        "at",
        "to",
        "with",
        "or",
        "we",
        "you",
        "our",
        "is",
        "are",
        "be",
        "as",
        "by",
    }
)
TOKEN = re.compile(r"[a-z0-9+#]+(?:\.[a-z0-9]+)*")
FIELD_BOOST = {"title": 3.0, "skills": 2.0, "description": 1.0}
SYNONYMS = {"k8s": "kubernetes", "js": "javascript", "ts": "typescript", "golang": "go", "postgres": "postgresql"}
# Terms that end in "s" but are not plurals; synonym targets are never folded either.
NO_FOLD = frozenset({"kubernetes", "analytics", "devops", "aws", "graphics", "statistics"})


def analyze(text: str) -> list[str]:
    out = []
    for tok in TOKEN.findall(text.lower()):
        if tok in STOP:
            continue
        if tok in SYNONYMS:
            tok = SYNONYMS[tok]
        elif len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss") and "." not in tok and tok not in NO_FOLD:
            tok = tok[:-1]  # light plural folding: engineers → engineer
        out.append(tok)
    return out


@dataclass(frozen=True)
class Filters:
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    min_salary: int | None = None  # jobs whose max salary reaches this value
    max_years: int | None = None  # candidate experience: jobs requiring at most this many years


@dataclass
class SearchResult:
    total: int
    hits: list[tuple[Job, float]]
    facets: dict[str, dict[str, int]] = field(default_factory=dict)


class JobIndex:
    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self._docs: dict[str, Job] = {}
        self._tf: dict[str, dict[str, Counter[str]]] = {}  # job id → field → term counts
        self._len: dict[str, dict[str, int]] = {}
        self._postings: dict[str, set[str]] = defaultdict(set)  # term → job ids

    def __len__(self) -> int:
        return len(self._docs)

    def upsert(self, job: Job) -> None:
        """Index or re-index a job (event-driven in production: JobCreated / JobUpdated / JobClosed)."""
        self.delete(job.id)
        if job.status is not JobStatus.OPEN:
            return
        fields = {
            "title": analyze(job.title),
            "skills": analyze(" ".join(job.required_skills + job.nice_skills)),
            "description": analyze(job.description),
        }
        self._docs[job.id] = job
        self._tf[job.id] = {f: Counter(toks) for f, toks in fields.items()}
        self._len[job.id] = {f: len(toks) for f, toks in fields.items()}
        for toks in fields.values():
            for t in toks:
                self._postings[t].add(job.id)

    def delete(self, job_id: str) -> None:
        if job_id not in self._docs:
            return
        for counts in self._tf.pop(job_id).values():
            for t in counts:
                self._postings[t].discard(job_id)
        del self._docs[job_id], self._len[job_id]

    def _avg_len(self, f: str) -> float:
        return sum(lens[f] for lens in self._len.values()) / max(1, len(self._len))

    def _bm25(self, job_id: str, terms: list[str]) -> float:
        n = len(self._docs)
        score = 0.0
        for f, boost in FIELD_BOOST.items():
            avg = self._avg_len(f) or 1.0
            dl = self._len[job_id][f]
            for t in terms:
                tf = self._tf[job_id][f].get(t, 0)
                if not tf:
                    continue
                df = len(self._postings[t])
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                score += boost * idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / avg))
        return score

    @staticmethod
    def _matches(job: Job, f: Filters) -> bool:
        if f.location and job.location.lower() != f.location.lower() and not (f.remote is None and job.remote):
            return False
        if f.remote is not None and job.remote != f.remote:
            return False
        if f.employment_type and job.employment_type.value != f.employment_type:
            return False
        if f.min_salary is not None and (job.salary_max is None or job.salary_max < f.min_salary):
            return False
        return not (f.max_years is not None and job.min_years > f.max_years)

    def search(self, query: str, filters: Filters | None = None, offset: int = 0, limit: int = 10) -> SearchResult:
        f = filters or Filters()
        terms = analyze(query)
        if terms:  # OR semantics across terms; BM25 ranks documents matching more/rarer terms higher
            candidates: set[str] = set().union(*(self._postings.get(t, set()) for t in terms))
        else:
            candidates = set(self._docs)
        matched = [self._docs[i] for i in candidates if self._matches(self._docs[i], f)]
        scored = sorted(
            ((j, self._bm25(j.id, terms) if terms else 0.0) for j in matched),
            key=lambda x: (-x[1], x[0].id),
        )
        facets: dict[str, dict[str, int]] = {
            "location": dict(Counter(j.location for j in matched).most_common()),
            "employment_type": dict(Counter(j.employment_type.value for j in matched).most_common()),
            "remote": dict(Counter("remote" if j.remote else "onsite" for j in matched).most_common()),
        }
        return SearchResult(len(scored), scored[offset : offset + limit], facets)
