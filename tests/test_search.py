from jobs.domain import EmploymentType, Job, JobStatus
from jobs.search import Filters, JobIndex, analyze

from .conftest import job_by_title


def titles(result) -> list[str]:  # type: ignore[no-untyped-def]
    return [j.title for j, _ in result.hits]


def test_analyzer_applies_stopwords_synonyms_and_plural_folding():
    assert analyze("Engineers for K8s and Postgres") == ["engineer", "kubernetes", "postgresql"]
    assert analyze("Kubernetes developers") == ["kubernetes", "developer"]  # same term as the k8s synonym
    assert analyze("C# and C++ with Node.js") == ["c#", "c++", "node.js"]


def test_title_matches_outrank_description_matches(portal):
    r = portal.search("python", Filters())
    # "Junior Python Developer" has python in the title (boost 3) as well as in skills
    assert titles(r)[0] == "Junior Python Developer"
    assert set(titles(r)) == {
        "Junior Python Developer",
        "Senior Backend Engineer",
        "Data Engineer (Contract)",
        "Platform Engineer",
    }


def test_synonyms_find_jobs_written_with_the_canonical_term(portal):
    assert titles(portal.search("k8s", Filters())) == ["Platform Engineer", "Senior Backend Engineer"]


def test_structured_filters(portal):
    assert titles(portal.search("", Filters(employment_type="contract"))) == ["Data Engineer (Contract)"]
    assert all(j.remote for j, _ in portal.search("", Filters(remote=True)).hits)
    assert titles(portal.search("python", Filters(min_salary=95_000))) == ["Senior Backend Engineer"]
    juniors = portal.search("python", Filters(max_years=1))
    assert titles(juniors) == ["Junior Python Developer"]


def test_location_filter_includes_remote_jobs_unless_remote_is_specified(portal):
    berlin = set(titles(portal.search("", Filters(location="berlin"))))
    assert {"Senior Backend Engineer", "Frontend Engineer", "Platform Engineer"} <= berlin
    onsite_berlin = titles(portal.search("", Filters(location="Berlin", remote=False)))
    assert onsite_berlin == ["Senior Backend Engineer"]


def test_facets_and_pagination(portal):
    r = portal.search("", Filters(), offset=0, limit=2)
    assert r.total == 5 and len(r.hits) == 2
    assert r.facets["employment_type"] == {"full_time": 4, "contract": 1}
    page2 = portal.search("", Filters(), offset=2, limit=2)
    assert not {j.id for j, _ in r.hits} & {j.id for j, _ in page2.hits}


def test_closed_jobs_leave_the_index_and_reindexing_replaces_terms(portal):
    job = job_by_title(portal, "Platform Engineer")
    portal.close_job("recruiter-1", job.id)
    assert "Platform Engineer" not in titles(portal.search("terraform", Filters()))
    index = JobIndex()
    j = Job("job_x", "co", "Rust Developer", "Systems work", "Pune", False, EmploymentType.FULL_TIME, ["rust"])
    index.upsert(j)
    j.title, j.required_skills = "Go Developer", ["go"]
    index.upsert(j)
    assert index.search("rust").total == 0 and index.search("go").total == 1
    j.status = JobStatus.CLOSED
    index.upsert(j)
    assert len(index) == 0
