from unittest.mock import MagicMock, patch

import pytest

from agentzero.google import calendar, drive, gmail


def test_send_message_builds_gmail_request():
    service = MagicMock()
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg1"
    }
    result = gmail.send_message(service, to="a@b.com", subject="Hi", body="Hello")
    assert result["id"] == "msg1"


def test_create_calendar_event():
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}
    result = calendar.create_event(
        service,
        summary="Interview",
        start_iso="2026-05-10T10:00:00Z",
        end_iso="2026-05-10T11:00:00Z",
    )
    assert result["id"] == "evt1"


def test_upload_drive_file(tmp_path):
    path = tmp_path / "letter.md"
    path.write_text("hello", encoding="utf-8")
    service = MagicMock()
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "file1",
        "name": "letter.md",
    }
    fake_http = MagicMock()
    fake_http.MediaFileUpload.return_value = MagicMock()
    modules = {"googleapiclient": MagicMock(), "googleapiclient.http": fake_http}
    with patch.dict("sys.modules", modules):
        result = drive.upload_file(service, path=path)
    assert result["id"] == "file1"


def test_load_credentials_import_error(tmp_path):
    from agentzero.google.auth import load_credentials

    with pytest.raises(ImportError, match="google-auth"):
        load_credentials(
            client_secret_path=tmp_path / "secret.json",
            token_path=tmp_path / "token.json",
        )
