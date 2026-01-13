"""Tests for prospect ingestion."""

import csv
import tempfile
from pathlib import Path

import pytest

from cold_emailer.attachments import ResumeManifest, compute_sha256, validate_resume_file
from cold_emailer.ingestion import (
    generate_prospect_id,
    ingest_prospects,
    parse_csv,
    parse_excel,
    validate_email,
)
from cold_emailer.state_store.repo import ProspectRepository


def test_validate_email() -> None:
    """Test email validation."""
    assert validate_email("test@example.com") is True
    assert validate_email("user.name@domain.co.uk") is True
    assert validate_email("invalid") is False
    assert validate_email("invalid@") is False
    assert validate_email("") is False


def test_generate_prospect_id() -> None:
    """Test prospect ID generation."""
    id1 = generate_prospect_id("test@example.com", "Company")
    id2 = generate_prospect_id("test@example.com", "Company")
    id3 = generate_prospect_id("test@example.com", "Different")

    # Should be deterministic
    assert id1 == id2
    # Should be different for different inputs
    assert id1 != id3
    # Should be valid UUID format
    assert len(id1) == 36


def test_parse_csv_valid(tmp_path: Path) -> None:
    """Test parsing valid CSV file."""
    csv_file = tmp_path / "prospects.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "prospect_id",
                "email",
                "full_name",
                "company",
                "resume_id",
                "sequence_id",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "prospect_id": "",
                "email": "test@example.com",
                "full_name": "Test User",
                "company": "Test Corp",
                "resume_id": "RES-001",
                "sequence_id": "default",
            }
        )

    prospects = parse_csv(csv_file)
    assert len(prospects) == 1
    assert prospects[0]["email"] == "test@example.com"
    assert prospects[0]["full_name"] == "Test User"
    assert prospects[0]["company"] == "Test Corp"
    assert prospects[0]["resume_id"] == "RES-001"


def test_parse_csv_missing_columns(tmp_path: Path) -> None:
    """Test parsing CSV with missing required columns."""
    csv_file = tmp_path / "prospects.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "full_name"])
        writer.writeheader()

    with pytest.raises(ValueError, match="Missing required columns"):
        parse_csv(csv_file)


def test_parse_csv_invalid_email(tmp_path: Path) -> None:
    """Test parsing CSV with invalid email."""
    csv_file = tmp_path / "prospects.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["email", "full_name", "company", "resume_id"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "email": "invalid-email",
                "full_name": "Test User",
                "company": "Test Corp",
                "resume_id": "RES-001",
            }
        )

    prospects = parse_csv(csv_file)
    # Invalid email should be skipped
    assert len(prospects) == 0


def test_compute_sha256(tmp_path: Path) -> None:
    """Test SHA256 computation."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    sha256 = compute_sha256(test_file)
    assert len(sha256) == 64  # SHA256 hex is 64 chars
    assert isinstance(sha256, str)

    # Should be deterministic
    sha256_2 = compute_sha256(test_file)
    assert sha256 == sha256_2


def test_validate_resume_file(tmp_path: Path) -> None:
    """Test resume file validation."""
    test_file = tmp_path / "resume.pdf"
    test_file.write_text("test content")
    sha256 = compute_sha256(test_file)

    # Valid file
    is_valid, error = validate_resume_file(test_file, sha256)
    assert is_valid is True
    assert error is None

    # Wrong checksum
    is_valid, error = validate_resume_file(test_file, "wrong" * 16)
    assert is_valid is False
    assert error is not None

    # Missing file
    missing_file = tmp_path / "missing.pdf"
    is_valid, error = validate_resume_file(missing_file)
    assert is_valid is False
    assert error is not None


def test_resume_manifest(tmp_path: Path) -> None:
    """Test resume manifest loading."""
    # Create test resume
    resume_file = tmp_path / "resumes" / "RES-001.pdf"
    resume_file.parent.mkdir(parents=True)
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

    # Validate resume
    is_valid, error, info = manifest.validate_resume("RES-001")
    assert is_valid is True
    assert error is None
    assert info is not None


def test_resume_manifest_missing_resume(tmp_path: Path) -> None:
    """Test resume manifest with missing resume file."""
    manifest_file = tmp_path / "manifest.csv"
    with open(manifest_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["resume_id", "relative_path", "sha256", "version"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "resume_id": "RES-001",
                "relative_path": "nonexistent.pdf",
                "sha256": "",
                "version": "1.0",
            }
        )

    manifest = ResumeManifest(manifest_file, base_path=tmp_path)
    is_valid, error, info = manifest.validate_resume("RES-001")
    assert is_valid is False
    assert error is not None


@pytest.fixture
def sample_prospects_csv(tmp_path: Path) -> Path:
    """Create a sample prospects CSV file."""
    csv_file = tmp_path / "prospects.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["email", "full_name", "company", "resume_id", "sequence_id"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "email": "test1@example.com",
                "full_name": "Test User 1",
                "company": "Test Corp",
                "resume_id": "RES-001",
                "sequence_id": "default",
            }
        )
    return csv_file


@pytest.fixture
def sample_resume_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """Create a sample resume manifest and resume file."""
    # Create resume file
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

    return manifest_file, resume_file


def test_ingest_prospects(
    tmp_path: Path,
    sample_prospects_csv: Path,
    sample_resume_manifest: tuple[Path, Path],
    db_session,
) -> None:
    """Test full ingestion process."""
    manifest_file, _ = sample_resume_manifest
    manifest = ResumeManifest(manifest_file, base_path=tmp_path)
    repo = ProspectRepository(db_session)

    created, updated, errors = ingest_prospects(
        file_path=sample_prospects_csv,
        manifest=manifest,
        repo=repo,
        reset_state=False,
    )

    assert created == 1
    assert updated == 0
    assert len(errors) == 0

    # Verify prospect was created
    prospect = repo.get_by_email("test1@example.com")
    assert prospect is not None
    assert prospect.full_name == "Test User 1"
    assert prospect.resume_id == "RES-001"
    assert prospect.resume_sha256 is not None
