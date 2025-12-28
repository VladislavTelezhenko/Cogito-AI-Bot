# Тесты валидаторов файлов

import pytest
from utils.bot_utils import FileValidator

pytestmark = pytest.mark.bot


def test_validator_accepts_txt_file():
    # Валидатор принимает .txt файл
    is_valid, error, mime = FileValidator.validate_file(
        "document.txt",
        1024,  # 1 KB
        "file"
    )

    assert is_valid is True
    assert error is None
    assert mime == "text/plain"


def test_validator_accepts_pdf_file():
    # Валидатор принимает .pdf файл
    is_valid, error, mime = FileValidator.validate_file(
        "document.pdf",
        5 * 1024 * 1024,  # 5 MB
        "file"
    )

    assert is_valid is True
    assert mime == "application/pdf"


def test_validator_accepts_docx_file():
    # Валидатор принимает .docx файл
    is_valid, error, mime = FileValidator.validate_file(
        "document.docx",
        10 * 1024 * 1024,  # 10 MB
        "file"
    )

    assert is_valid is True
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_validator_rejects_exe_file():
    # Валидатор отклоняет .exe файл
    is_valid, error, mime = FileValidator.validate_file(
        "virus.exe",
        1024,
        "file"
    )

    assert is_valid is False
    assert "Неподдерживаемый формат" in error
    assert mime is None


def test_validator_rejects_zip_file():
    # Валидатор отклоняет .zip файл
    is_valid, error, mime = FileValidator.validate_file(
        "archive.zip",
        1024,
        "file"
    )

    assert is_valid is False
    assert ".zip" in error.upper()


def test_validator_rejects_oversized_file():
    # Валидатор отклоняет слишком большой файл
    is_valid, error, mime = FileValidator.validate_file(
        "huge.pdf",
        50 * 1024 * 1024,  # 50 MB (лимит 20 MB)
        "file"
    )

    assert is_valid is False
    assert "слишком большой" in error
    assert "50" in error


def test_validator_accepts_jpg_photo():
    # Валидатор принимает .jpg фото
    is_valid, error, mime = FileValidator.validate_file(
        "photo.jpg",
        2 * 1024 * 1024,
        "photo"
    )

    assert is_valid is True
    assert mime == "image/jpeg"


def test_validator_accepts_png_photo():
    # Валидатор принимает .png фото
    is_valid, error, mime = FileValidator.validate_file(
        "screenshot.png",
        3 * 1024 * 1024,
        "photo"
    )

    assert is_valid is True
    assert mime == "image/png"


def test_validator_rejects_gif_as_photo():
    # Валидатор отклоняет .gif как фото
    is_valid, error, mime = FileValidator.validate_file(
        "animation.gif",
        1024,
        "photo"
    )

    assert is_valid is False


def test_validator_case_insensitive():
    # Валидатор не чувствителен к регистру расширений
    is_valid1, _, mime1 = FileValidator.validate_file("file.PDF", 1024, "file")
    is_valid2, _, mime2 = FileValidator.validate_file("file.pdf", 1024, "file")

    assert is_valid1 is True
    assert is_valid2 is True
    assert mime1 == mime2