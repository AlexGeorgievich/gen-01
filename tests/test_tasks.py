from gpt01.tasks import Worker


def test_worker_forwards_progress_and_result():
    progress = []
    results = []
    worker = Worker(
        lambda _cancelled, report: (report(2, 5, "working"), "done")[1]
    )
    worker.signals.progress.connect(
        lambda current, total, message: progress.append((current, total, message))
    )
    worker.signals.result.connect(results.append)

    worker.run()

    assert progress == [(2, 5, "working")]
    assert results == ["done"]


def test_cancelled_worker_does_not_publish_result():
    results = []
    worker = Worker(lambda _cancelled, _report: "done")
    worker.signals.result.connect(results.append)
    worker.cancel()

    worker.run()

    assert results == []
