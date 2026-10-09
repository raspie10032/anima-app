"""Batch seed regressions with a clock that advances between job creation."""

import threading
from types import SimpleNamespace

import pytest

from anima_app import server
from anima_app.config import AppPaths


@pytest.fixture
def seed_queue(tmp_path, monkeypatch):
    # Drive completion directly: no worker, renderer, models or NAI transport.
    monkeypatch.setattr(server.JobQueue, "_worker_loop", lambda self: None)
    monkeypatch.setattr(server, "handle_generate", lambda *a, **k: pytest.fail("generation called"))
    clock = SimpleNamespace(now=10000.0)

    def advancing_time():
        now = clock.now
        clock.now += .125
        return now

    # Replacing this module binding avoids changing pytest's real clock.
    monkeypatch.setattr(server, "time", SimpleNamespace(time=advancing_time))
    queue = server.JobQueue(
        paths=AppPaths(tmp_path), renderer=None, default_dry_run=True,
        progress_store=server.ProgressStore(), generation_lock=threading.Lock(),
    )
    queue._worker.join(5)
    assert not queue._worker.is_alive()
    try:
        yield queue, clock
    finally:
        queue.close()


def batch_jobs(queue, request, *, seed_mode="increment", infinite=False):
    status, batch = queue.enqueue({
        "request": request, "count": 4, "infinite": infinite, "seed_mode": seed_mode,
    })
    assert status == 202, batch
    if infinite:
        job = batch["jobs"][0]
        for _ in range(3):
            # Completion arrives much later than the preceding job's creation.
            server.time.time()
            queue._finish_job(job["id"], 200, {"status": "generated"})
            job = queue.list()["items"][-1]
    return queue.list()["items"]


def request_for(provider, seed_fields):
    return {"provider": provider, "prompt": "seed regression", "width": 64,
            "height": 64, "dry_run": True, **seed_fields}


@pytest.mark.parametrize("provider", ["local", "novelai"])
@pytest.mark.parametrize("seed_fields", [{}, {"seed": None}, {"seed": ""}],
                         ids=["omitted", "null", "empty"])
@pytest.mark.parametrize("infinite", [False, True], ids=["finite", "infinite"])
def test_increment_freezes_omitted_seed_despite_clock_advancement(seed_queue, provider, seed_fields, infinite):
    queue, clock = seed_queue
    request = request_for(provider, seed_fields)
    original = request.copy()
    expected = int(clock.now * 1000) % 2147483647
    jobs = batch_jobs(queue, request, infinite=infinite)
    assert [job["request"]["seed"] for job in jobs] == [expected + i for i in range(4)]
    assert request == original
    batch = queue._batches[jobs[0]["batch_id"]]
    assert batch["base_seed"] == expected
    assert batch["base_seed_provided"] is False
    assert batch["base_request"].get("seed") in (None, "")


@pytest.mark.parametrize("provider,maximum", [("local", server.MAX_SEED), ("novelai", server.MAX_NAI_SEED)])
@pytest.mark.parametrize("seed_at_max", [False, True], ids=["zero", "maximum"])
@pytest.mark.parametrize("infinite", [False, True], ids=["finite", "infinite"])
def test_increment_preserves_zero_and_provider_wraparound(seed_queue, provider, maximum, seed_at_max, infinite):
    queue, _ = seed_queue
    seed = maximum if seed_at_max else 0
    jobs = batch_jobs(queue, request_for(provider, {"seed": seed}), infinite=infinite)
    assert [job["request"]["seed"] for job in jobs] == [(seed + i) % (maximum + 1) for i in range(4)]
    assert queue._batches[jobs[0]["batch_id"]]["base_seed_provided"] is True


@pytest.mark.parametrize("provider", ["local", "novelai"])
@pytest.mark.parametrize("seed_fields", [{}, {"seed": None}, {"seed": ""}, {"seed": 0}, {"seed": 123}])
@pytest.mark.parametrize("infinite", [False, True], ids=["finite", "infinite"])
def test_fixed_mode_does_not_invent_a_batch_seed(seed_queue, provider, seed_fields, infinite):
    queue, _ = seed_queue
    jobs = batch_jobs(queue, request_for(provider, seed_fields), seed_mode="fixed", infinite=infinite)
    if seed_fields.get("seed") in (None, ""):
        assert all("seed" not in job["request"] for job in jobs)
    else:
        assert [job["request"]["seed"] for job in jobs] == [seed_fields["seed"]] * 4


@pytest.mark.parametrize("provider", ["local", "novelai"])
@pytest.mark.parametrize("seed_fields", [{}, {"seed": 0}, {"seed": 123}])
@pytest.mark.parametrize("infinite", [False, True], ids=["finite", "infinite"])
def test_random_mode_draws_each_job_independently(seed_queue, monkeypatch, provider, seed_fields, infinite):
    queue, _ = seed_queue
    draws = iter([17, 31, 2, 999])

    def randint(low, high):
        assert (low, high) == (0, 2147483646)
        return next(draws)

    monkeypatch.setattr(server, "_QUEUE_RANDOM", SimpleNamespace(randint=randint))
    jobs = batch_jobs(queue, request_for(provider, seed_fields), seed_mode="random", infinite=infinite)
    assert [job["request"]["seed"] for job in jobs] == [17, 31, 2, 999]


def test_independent_batches_get_independent_start_seeds(seed_queue):
    queue, clock = seed_queue
    request = request_for("novelai", {})
    first_expected = int(clock.now * 1000) % 2147483647
    status, first = queue.enqueue({"request": request, "count": 2})
    assert status == 202
    clock.now += 60
    second_expected = int(clock.now * 1000) % 2147483647
    status, second = queue.enqueue({"request": request, "count": 2})
    assert status == 202
    assert [job["request"]["seed"] for job in first["jobs"]] == [first_expected, first_expected + 1]
    assert [job["request"]["seed"] for job in second["jobs"]] == [second_expected, second_expected + 1]
    assert first_expected != second_expected
