from jobs.domain import CandidateProfile
from jobs.matching import WEIGHTS, match, recommend

from .conftest import job_by_title


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_full_match_is_explainable(portal, backend_dev):
    m = match(backend_dev, job_by_title(portal, "Senior Backend Engineer"))
    assert m.components == {
        "required_skills": 1.0,
        "nice_skills": 0.0,
        "experience": 1.0,
        "location": 1.0,
        "salary": 1.0,
    }
    assert m.score == 0.9 and m.missing_skills == []


def test_partial_match_reports_missing_skills_and_scales_experience(portal):
    junior = CandidateProfile("c2", "", ["python"], 2, "Pune", remote_ok=False)
    m = match(junior, job_by_title(portal, "Senior Backend Engineer"))
    assert m.missing_skills == ["postgresql", "kafka"]
    assert m.components["experience"] == 2 / 5
    assert m.components["location"] == 0.0


def test_salary_expectation_above_the_range_lowers_the_score(portal, backend_dev):
    greedy = CandidateProfile(**{**backend_dev.__dict__, "desired_salary": 150_000})
    job = job_by_title(portal, "Senior Backend Engineer")
    assert match(greedy, job).score < match(backend_dev, job).score


def test_recommendations_via_the_portal(portal, backend_dev):
    portal.save_profile(backend_dev)
    recs = portal.recommendations("cand-1")
    assert portal.jobs[recs[0].job_id].title == "Senior Backend Engineer"
    assert all(r.score >= 0.4 for r in recs)
    assert [r.score for r in recs] == sorted((r.score for r in recs), reverse=True)
    assert recommend(backend_dev, [], 5) == []
