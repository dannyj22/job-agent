from datetime import datetime, timezone

from jobagent.models import Job
from jobagent.storage import Storage


def make_job(**overrides):
    data = {
        "title": "Next.js Developer",
        "company": "Acme",
        "url": "https://example.com/jobs/1?utm_source=x",
        "source": "test",
        "location": "Remote",
        "description": "Build things",
        "posted_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return Job(**data)


def test_save_if_new_dedupes(tmp_path):
    storage = Storage(tmp_path / "jobs.db")
    job = make_job()
    assert storage.save_if_new(job) is True
    assert storage.save_if_new(job) is False
    assert storage.stats()["total"] == 1
    storage.close()


def test_tracking_params_do_not_create_duplicates(tmp_path):
    storage = Storage(tmp_path / "jobs.db")
    first = make_job(url="https://example.com/jobs/1?utm_source=a")
    second = make_job(url="https://example.com/jobs/1?utm_source=b")
    assert first.fingerprint == second.fingerprint
    assert storage.save_if_new(first)
    assert not storage.save_if_new(second)
    storage.close()


def test_mark_notified(tmp_path):
    storage = Storage(tmp_path / "jobs.db")
    job = make_job()
    storage.save_if_new(job)
    storage.mark_notified([job.fingerprint])
    assert storage.stats()["notified"] == 1
    assert storage.stats()["pending"] == 0
    storage.close()


def test_pending_drains_best_first(tmp_path):
    storage = Storage(tmp_path / "jobs.db")
    low = make_job(title="Low", url="https://example.com/1")
    low.score = 5
    high = make_job(title="High", url="https://example.com/2")
    high.score = 20
    storage.save_if_new(low)
    storage.save_if_new(high)

    first = storage.pending(1)
    assert [job.title for job in first] == ["High"]

    storage.mark_notified([job.fingerprint for job in first])
    assert [job.title for job in storage.pending(5)] == ["Low"]
    storage.close()
