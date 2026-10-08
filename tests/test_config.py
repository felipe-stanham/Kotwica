"""cap-002 environment config."""
import pytest

from kotwica import config as cfg


def write_env(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_env_prd_maps_to_prod():
    c = cfg.load(environ={"ENV": "prd"})
    assert (c.env, c.managed_record, c.tls_connect_host) == ("prod", "home", "127.0.0.1")


def test_env_default_dev():
    c = cfg.load(environ={})
    assert (c.env, c.managed_record) == ("dev", "kotwica-dev")


def test_process_env_wins_over_dotenv(tmp_path):
    c = cfg.load(environ={"ENV": "prd"}, dotenv_path=write_env(tmp_path, "ENV=dev\n"))
    assert c.env == "prod"


def test_dotenv_env_used_when_process_env_absent(tmp_path):
    assert cfg.load(environ={}, dotenv_path=write_env(tmp_path, "ENV=tst\n")).env == "tst"


def test_dotenv_overrides_default(tmp_path):
    path = write_env(tmp_path, "DEV_WATCHED_HOSTS=a.example.com:443\n")
    assert cfg.load(environ={"ENV": "dev"}, dotenv_path=path).watched_hosts == [("a.example.com", 443)]


def test_default_watched_hosts_share_hostname():
    c = cfg.load(environ={"ENV": "dev"})
    assert c.watched_hosts == [("home.stanham.com", 443), ("home.stanham.com", 8443)]


def test_token_from_secret_wins(tmp_path):
    path = write_env(tmp_path, "DEV_GODADDY_API_TOKEN=tokB\n")
    assert cfg.load(environ={"ENV": "dev", "GODADDY_API_TOKEN": "tokA"}, dotenv_path=path).godaddy_token == "tokA"


def test_token_from_dotenv_prefix(tmp_path):
    path = write_env(tmp_path, "DEV_GODADDY_API_TOKEN=tokB\n")
    assert cfg.load(environ={"ENV": "dev"}, dotenv_path=path).godaddy_token == "tokB"


def test_guard_home_outside_prod(tmp_path):
    path = write_env(tmp_path, "DEV_MANAGED_RECORD=home\n")
    with pytest.raises(cfg.ConfigError, match="single-writer guard"):
        cfg.load(environ={"ENV": "dev"}, dotenv_path=path)


def test_tst_is_watch_only():
    c = cfg.load(environ={"ENV": "tst"})
    assert c.managed_record is None and c.tls_connect_host == "127.0.0.1"


def test_unknown_env_rejected():
    with pytest.raises(cfg.ConfigError):
        cfg.load(environ={"ENV": "staging"})


def test_token_not_in_repr():
    c = cfg.load(environ={"ENV": "dev", "GODADDY_API_TOKEN": "gd_pat_SENTINEL123"})
    assert "SENTINEL123" not in repr(c) and "SENTINEL123" not in str(c)


def test_guard_is_case_and_whitespace_insensitive(tmp_path):
    path = write_env(tmp_path, "DEV_MANAGED_RECORD= Home \n")
    with pytest.raises(cfg.ConfigError, match="single-writer guard"):
        cfg.load(environ={"ENV": "dev"}, dotenv_path=path)


def test_invalid_log_level_and_hosts_rejected(tmp_path):
    with pytest.raises(cfg.ConfigError):
        cfg.load(environ={"ENV": "dev"}, dotenv_path=write_env(tmp_path, "DEV_LOG_LEVEL=VERBOSE\n"))
    with pytest.raises(cfg.ConfigError):
        cfg.load(environ={"ENV": "dev"}, dotenv_path=write_env(tmp_path, "DEV_WATCHED_HOSTS=a.example.com:99999\n"))
    with pytest.raises(cfg.ConfigError):
        cfg.load(environ={"ENV": "dev"}, dotenv_path=write_env(tmp_path, "DEV_WATCHED_HOSTS=\n"))


def test_token_is_stripped():
    assert cfg.load(environ={"ENV": "dev", "GODADDY_API_TOKEN": " tokA\n"}).godaddy_token == "tokA"
    assert cfg.load(environ={"ENV": "dev", "GODADDY_API_TOKEN": "\n"}).godaddy_token is None


def test_managed_record_must_be_a_single_label_and_two_echo_services_needed(tmp_path):
    for bad in ("@", "a/b", "a.b", "-x"):
        with pytest.raises(cfg.ConfigError):
            cfg.load(environ={"ENV": "dev"}, dotenv_path=write_env(tmp_path, "DEV_MANAGED_RECORD=%s\n" % bad))
    with pytest.raises(cfg.ConfigError):
        cfg.load(environ={"ENV": "dev"}, dotenv_path=write_env(tmp_path, "DEV_IP_ECHO_URLS=https://api.ipify.org\n"))
