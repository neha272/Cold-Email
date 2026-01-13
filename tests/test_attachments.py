"""Tests for attachment validation."""

import tempfile
from pathlib import Path

import pytest

from cold_emailer.attachments import (
    ResumeManifest,
    compute_sha256,
    validate_resume_file,
)


def test_compute_sha256() -> None:
    """Test SHA256 computation."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test resume content")
        temp_path = Path(f.name)

    try:
        sha256 = compute_sha256(temp_path)
        assert len(sha256) == 64
        assert isinstance(sha256, str)

        # Should be deterministic
        sha256_2 = compute_sha256(temp_path)
        assert sha256 == sha256_2
    finally:
        temp_path.unlink()


def test_compute_sha256_missing_file() -> None:
    """Test SHA256 computation with missing file."""
    missing_path = Path("/nonexistent/file.pdf")
    with pytest.raises(FileNotFoundError):
        compute_sha256(missing_path)


def test_validate_resume_file_exists() -> None:
    """Test validation of existing file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test content")
        temp_path = Path(f.name)

    try:
        is_valid, error = validate_resume_file(temp_path)
        assert is_valid is True
        assert error is None
    finally:
        temp_path.unlink()


def test_validate_resume_file_missing() -> None:
    """Test validation of missing file."""
    missing_path = Path("/nonexistent/file.pdf")
    is_valid, error = validate_resume_file(missing_path)
    assert is_valid is False
    assert error is not None
    assert "not found" in error.lower()


def test_validate_resume_file_checksum_match() -> None:
    """Test validation with matching checksum."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test content")
        temp_path = Path(f.name)

    try:
        sha256 = compute_sha256(temp_path)
        is_valid, error = validate_resume_file(temp_path, sha256)
        assert is_valid is True
        assert error is None
    finally:
        temp_path.unlink()


def test_validate_resume_file_checksum_mismatch() -> None:
    """Test validation with mismatched checksum."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test content")
        temp_path = Path(f.name)

    try:
        wrong_sha256 = "a" * 64  # Wrong checksum
        is_valid, error = validate_resume_file(temp_path, wrong_sha256)
        assert is_valid is False
        assert error is not None
        assert "mismatch" in error.lower()
    finally:
        temp_path.unlink()


def test_validate_resume_file_too_large(tmp_path: Path) -> None:
    """Test validation of file that's too large."""
    # Create a file larger than 10MB
    large_file = tmp_path / "large.pdf"
    # Write 11MB of data
    with open(large_file, "wb") as f:
        f.write(b"x" * (11 * 1024 * 1024))

    is_valid, error = validate_resume_file(large_file)
    assert is_valid is False
    assert error is not None
    assert "too large" in error.lower()


def test_resume_manifest_load(tmp_path: Path) -> None:
    """Test loading resume manifest."""
    import csv

    # Create test resume
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    resume_file = resume_dir / "RES-001.pdf"
    resume_file.write_text("resume content")
    sha256 = compute_sha256(resume_file)

    # Create manifest
    manifest_file = tmp_path / "manifest.csv"
    with open(manifest_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["resume_id", "relative_path", "sha256", "version"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "resume_id": "RES-001",
                "relative_path": str(resume_file.relative_to(tmp_path)),
                "sha256": sha256,
                "version": "1.0",
            }
        )

    manifest = ResumeManifest(manifest_file, base_path=tmp_path)
    resume_info = manifest.get_resume_info("RES-001")

    assert resume_info is not None
    assert resume_info["resume_id"] == "RES-001"
    assert resume_info["sha256"] == sha256
    assert resume_info["absolute_path"] == resume_file.resolve()


def test_resume_manifest_validate(tmp_path: Path) -> None:
    """Test resume validation through manifest."""
    import csv

    # Create test resume
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    resume_file = resume_dir / "RES-001.pdf"
    resume_file.write_text("resume content")
    sha256 = compute_sha256(resume_file)

    # Create manifest
    manifest_file = tmp_path / "manifest.csv"
    with open(manifest_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["resume_id", "relative_path", "sha256", "version"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "resume_id": "RES-001",
                "relative_path": str(resume_file.relative_to(tmp_path)),
                "sha256": sha256,
                "version": "1.0",
            }
        )

    manifest = ResumeManifest(manifest_file, base_path=tmp_path)

    # Validate existing resume
    is_valid, error, info = manifest.validate_resume("RES-001")
    assert is_valid is True
    assert error is None
    assert info is not None

    # Validate missing resume ID
    is_valid, error, info = manifest.validate_resume("RES-999")
    assert is_valid is False
    assert error is not None
    assert "not found" in error.lower()


def test_resume_manifest_compute_checksum_if_missing(tmp_path: Path) -> None:
    """Test that manifest computes checksum if missing."""
    import csv

    # Create test resume
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    resume_file = resume_dir / "RES-001.pdf"
    resume_file.write_text("resume content")
    expected_sha256 = compute_sha256(resume_file)

    # Create manifest without checksum
    manifest_file = tmp_path / "manifest.csv"
    with open(manifest_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["resume_id", "relative_path", "sha256", "version"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "resume_id": "RES-001",
                "relative_path": str(resume_file.relative_to(tmp_path)),
                "sha256": "",  # Missing checksum
                "version": "1.0",
            }
        )

    manifest = ResumeManifest(manifest_file, base_path=tmp_path)
    resume_info = manifest.get_resume_info("RES-001")

    # Checksum should be computed automatically
    assert resume_info is not None
    assert resume_info["sha256"] == expected_sha256
