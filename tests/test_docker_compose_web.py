from pathlib import Path


def test_compose_defines_web_service():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "\n  web:" in text or "  web:\n" in text


def test_web_service_port_8080():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "8080:8080" in text


def test_web_service_mounts_data_volume():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "./data:/app/data" in text


def test_web_command_runs_uvicorn():
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "uvicorn" in text
    assert "agentzero.web.app" in text
