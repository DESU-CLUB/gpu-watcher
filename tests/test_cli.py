from gpu_watcher.__main__ import main


def test_config_flag_before_subcommand(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('database_path = "test.sqlite3"\n', encoding="utf-8")

    called = {}

    def fake_run_service(app_config):
        called["database_path"] = app_config.database_path

    monkeypatch.setattr("gpu_watcher.__main__.run_service", fake_run_service)

    assert main(["--config", str(config), "run"]) == 0
    assert called["database_path"].name == "test.sqlite3"


def test_config_flag_after_subcommand(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('database_path = "test.sqlite3"\n', encoding="utf-8")

    called = {}

    def fake_run_service(app_config):
        called["database_path"] = app_config.database_path

    monkeypatch.setattr("gpu_watcher.__main__.run_service", fake_run_service)

    assert main(["run", "--config", str(config)]) == 0
    assert called["database_path"].name == "test.sqlite3"
