"""上一次 Pages 部署結果（2026-09-23）。

9/23 21:50 那次部署在 GitHub 端回 500 失敗，本機的 publish_push.log 卻照樣寫
「Actions will deploy Pages」—— push 成功不等於上線成功，而且沒有任何地方標出來。
"""
from tools.quota_report import PagesRun, github_slug, latest_pages_run, pages_alert

RUN_URL = "https://github.com/o/r/actions/runs/1"


def _payload(status: str, conclusion: str | None) -> dict:
    return {"workflow_runs": [{
        "status": status, "conclusion": conclusion,
        "head_sha": "0be1986ddf89644d1ea3889bd22a6066ed157d5d",
        "created_at": "2026-09-23T13:50:09Z", "html_url": RUN_URL,
    }]}


def _run(status: str, conclusion: str | None) -> PagesRun | None:
    return latest_pages_run("o/r", get_json=lambda url: _payload(status, conclusion))


def test_reads_the_latest_run_of_the_pages_workflow():
    seen = []

    def fake(url):
        seen.append(url)
        return _payload("completed", "failure")

    run = latest_pages_run("o/r", get_json=fake)
    assert seen == ["https://api.github.com/repos/o/r/actions/workflows/pages.yml/runs?per_page=1"]
    assert run == PagesRun("completed", "failure", "0be1986", "2026-09-23T13:50:09Z", RUN_URL)


def test_failed_deploy_is_flagged_with_taipei_time_and_the_rerun_link():
    alert = pages_alert("market-barometer", _run("completed", "failure"))
    assert alert is not None
    assert "0be1986" in alert
    assert "2026-09-23 21:50" in alert      # 台北時間，不是 UTC 的 13:50
    assert RUN_URL in alert


def test_any_finished_run_that_did_not_succeed_is_flagged():
    for conclusion in ("cancelled", "timed_out", "startup_failure"):
        assert pages_alert("x", _run("completed", conclusion)) is not None, conclusion


def test_success_and_still_running_are_not_flagged():
    assert pages_alert("x", _run("completed", "success")) is None
    assert pages_alert("x", _run("in_progress", None)) is None


def test_unreachable_api_is_unknown_not_success():
    def boom(url):
        raise OSError("timeout")

    assert latest_pages_run("o/r", get_json=boom) is None
    assert latest_pages_run("o/r", get_json=lambda url: {"workflow_runs": []}) is None
    assert latest_pages_run("o/r", get_json=lambda url: {"message": "API rate limit exceeded"}) is None
    assert pages_alert("x", None) is None   # 不知道 ≠ 告警；main 另外印「未取得」


def test_slug_comes_from_the_github_remote():
    assert github_slug("https://github.com/ycy1997alex/market-barometer.git") == "ycy1997alex/market-barometer"
    assert github_slug("git@github.com:ycy1997alex/stock-research.git") == "ycy1997alex/stock-research"
    assert github_slug("https://gitlab.com/a/b.git") is None
