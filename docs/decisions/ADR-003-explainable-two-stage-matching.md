# ADR-003: Two-Stage, Explainable Matching for Recommendations and Applicant Ranking

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Candidates need relevant job recommendations; recruiters need applicants ranked by fit. Hiring is a sensitive domain:
rankings must be explainable, reviewable for bias, and robust before enough behavioural data exists to train models.

## Decision

Use **candidate generation** from the search index (the candidate's skills as the query, up to a few hundred jobs),
then **score** with a transparent weighted function over required skills, nice-to-have skills, experience, location and
salary fit. Return the component scores and missing skills with every result. The same function ranks applicants.

## Alternatives Considered

- **Learned ranking model from day one** — better accuracy at scale; needs labelled data, training infrastructure and
  fairness evaluation; opaque without additional tooling.
- **Embedding similarity of resume and job text** — handles vocabulary mismatch well; harder to explain and can encode
  proxies for protected attributes.
- **Collaborative filtering** — strong with interaction data; cold-start problems for new jobs and candidates.

## Trade-offs

Weights are hand-tuned and ignore behaviour signals; accuracy is limited.

## Consequences

The features become inputs to a learned ranker later; explanations remain a product requirement for any model.
