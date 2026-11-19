from datetime import datetime, timezone

from jobagent.filters import JobFilter
from jobagent.models import Job

BASE_CONFIG = {
    "min_score": 4,
    "title_bonus": 3,
    "include_keywords": {
        "core": ["react", "node", "next.js", "sql"],
        "adjacent": ["docker", "aws"],
        "general": ["developer", "engineer"],
    },
    "weights": {"core": 4, "adjacent": 2, "general": 1},
    "exclude_keywords": ["sales", "internship"],
    "locations": [],
}


def make_job(**overrides):
    data = {
        "title": "Frontend Developer",
        "company": "Acme",
        "url": "https://example.com/job/1",
        "source": "test",
        "location": "Remote",
        "description": "",
    }
    data.update(overrides)
    return Job(**data)


def test_core_keyword_is_accepted():
    job_filter = JobFilter(BASE_CONFIG)
    job = make_job(title="React Developer")
    result = job_filter.apply(job)
    assert result.accepted
    assert job.score >= BASE_CONFIG["min_score"]
    assert job.category in {"frontend", "fullstack"}


def test_excluded_keyword_is_rejected():
    job_filter = JobFilter(BASE_CONFIG)
    result = job_filter.evaluate(make_job(title="Sales Engineer"))
    assert not result.accepted
    assert "excluded" in result.reason


def test_low_score_is_rejected():
    job_filter = JobFilter(BASE_CONFIG)
    result = job_filter.evaluate(
        make_job(title="Office Manager", description="General admin work.")
    )
    assert not result.accepted


def test_fullstack_category_wins():
    job_filter = JobFilter(BASE_CONFIG)
    job = make_job(title="Full Stack Developer", description="React and Node.js")
    job_filter.apply(job)
    assert job.category == "fullstack"


def test_location_filter():
    config = dict(BASE_CONFIG, locations=["Canada"])
    job_filter = JobFilter(config)
    remote = make_job(title="React Developer", location="Remote")
    assert job_filter.evaluate(remote).accepted  # remote always passes
    onsite = Job(**{**remote.__dict__, "location": "Berlin", "remote": False})
    assert not job_filter.evaluate(onsite).accepted


def test_word_boundaries_do_not_match_substrings():
    job_filter = JobFilter(BASE_CONFIG)
    # "reactive" must not count as "react"
    result = job_filter.evaluate(make_job(title="Reactive Systems Engineer"))
    assert "react" not in result.matched
