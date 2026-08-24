from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


CHUNK_SIZE = 1024 * 1024


class FileTooLargeError(Exception):
    """Raised when an upload exceeds the configured size limit."""


class EmptyFileError(Exception):
    """Raised when an upload contains no bytes."""


@dataclass(frozen=True)
class StoredFile:
    stored_filename: str
    storage_path: str
    file_size: int


class LocalFileStorage:
    def __init__(self, upload_dir: Path, max_size_bytes: int) -> None:
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes

    def save(self, upload: UploadFile, extension: str) -> StoredFile:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4().hex}{extension}"
        destination = self.upload_dir / stored_filename
        file_size = 0
        destination_created = False

        try:
            with destination.open("xb") as output:
                destination_created = True
                while chunk := upload.file.read(CHUNK_SIZE):
                    file_size += len(chunk)
                    if file_size > self.max_size_bytes:
                        raise FileTooLargeError
                    output.write(chunk)
        except Exception:
            if destination_created:
                destination.unlink(missing_ok=True)
            raise

        if file_size == 0:
            destination.unlink(missing_ok=True)
            raise EmptyFileError

        return StoredFile(
            stored_filename=stored_filename,
            storage_path=str(destination),
            file_size=file_size,
        )

    @staticmethod
    def remove(storage_path: str) -> None:
        Path(storage_path).unlink(missing_ok=True)
