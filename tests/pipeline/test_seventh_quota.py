import json

from tools.quota_report import _git_object_stats, capacity_snapshot


def test_capacity_counts_external_universe_raw_files_and_git_objects(tmp_path):
    repo = tmp_path / "stock-research"
    repo.mkdir()
    data = tmp_path / "data"
    raw = data / "price_raw"
    raw.mkdir(parents=True)
    (data / "research_symbols.json").write_text(json.dumps({
        "symbols": [{"symbol": f"X{i}", "name": "X", "market": "US", "group": "us"}
                    for i in range(201)]
    }), encoding="utf-8")
    for i in range(751):
        (raw / f"{i}.jsonl.gz").write_bytes(b"x")
    got = capacity_snapshot(repo, data, git_stats=lambda _repo: (100001, 501 * 1024 * 1024))
    assert got.symbols == 201
    assert got.raw_files == 751
    assert got.git_objects == 100001
    assert len(got.alerts) == 4


def test_capacity_missing_inputs_are_unknown_not_zero(tmp_path):
    got = capacity_snapshot(tmp_path / "missing", tmp_path / "missing-data",
                            git_stats=lambda _repo: None)
    assert got.symbols is None
    assert got.raw_files is None
    assert got.git_objects is None


def test_git_object_count_uses_repo_scoped_safe_directory(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        class Result:
            stdout = "count: 2\nsize: 3\nin-pack: 4\nsize-pack: 5\n"
        return Result()

    monkeypatch.setattr("tools.quota_report.subprocess.run", fake_run)
    assert _git_object_stats(repo) == (6, 8 * 1024)
    assert commands[0][1:3] == ["-c", f"safe.directory={repo.resolve().as_posix()}"]
