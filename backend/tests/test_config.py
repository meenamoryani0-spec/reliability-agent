import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings


@pytest.fixture(autouse=True)
def clean_app_environment(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    for name in ("NEBIUS_API_KEY", "NEBIUS_MODEL", "NEBIUS_TIMEOUT_SECONDS", "NEBIUS_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_need_no_credentials():
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_env_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ENVIRONMENT=development\nLOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings(_env_file=env_file)
    assert settings.environment == "production"
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("values", [{"environment": "invalid"}, {"log_level": "verbose"}])
def test_invalid_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_invalid_dotenv_does_not_echo_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=sentinel-private-value\n", encoding="utf-8")
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=env_file)
    assert "sentinel-private-value" not in str(error.value)


def test_example_configuration_is_loadable():
    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")
    assert settings.environment == "development"


def test_default_dotenv_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Settings.model_config["env_file"] == PROJECT_ROOT / ".env"


def test_key_is_masked_and_blank_key_is_unconfigured():
    settings = Settings(_env_file=None, nebius_api_key="sentinel-private-value")
    assert "sentinel-private-value" not in repr(settings)
    assert "sentinel-private-value" not in settings.model_dump_json()
    assert Settings(_env_file=None, nebius_api_key=" ").nebius_api_key is None


@pytest.mark.parametrize(
    "values",
    [
        {"nebius_model": "other-provider/model"},
        {"nebius_max_tokens": 0},
        {"nebius_max_tokens": 100000},
        {"nebius_timeout_seconds": 0},
        {"nebius_timeout_seconds": 600},
        {"nebius_api_key": "key\nwith-whitespace"},
    ],
)
def test_unsafe_nebius_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
