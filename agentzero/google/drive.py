"""Google Drive helpers for storing application artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def upload_file(
    service: Any,
    *,
    path: Path,
    folder_id: str | None = None,
) -> dict:
    metadata: dict[str, str] = {"name": path.name}
    if folder_id:
        metadata["parents"] = [folder_id]
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise ImportError(
            "Drive upload requires google-api-python-client. "
            "Install with: pip install -e '.[google]'"
        ) from exc
    media = MediaFileUpload(str(path))
    return (
        service.files()
        .create(body=metadata, media_body=media, fields="id,name")
        .execute()
    )
