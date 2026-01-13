"""Resume attachment management and checksum validation."""

import hashlib
from pathlib import Path
from typing import Any

from cold_emailer.utils import get_logger

logger = get_logger(__name__)


def compute_sha256(file_path: Path) -> str:
    """
    Compute SHA256 checksum of a file.

    Args:
        file_path: Path to file

    Returns:
        SHA256 hex digest string

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError as e:
        raise IOError(f"Failed to read file {file_path}: {e}") from e


def validate_resume_file(
    file_path: Path, expected_sha256: str | None = None
) -> tuple[bool, str | None]:
    """
    Validate resume file exists and optionally verify checksum.

    Args:
        file_path: Path to resume file
        expected_sha256: Expected SHA256 checksum (optional)

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if file exists and checksum matches (if provided)
        - error_message: Error description if validation fails, None if valid
    """
    if not file_path.exists():
        return False, f"Resume file not found: {file_path}"

    if not file_path.is_file():
        return False, f"Path is not a file: {file_path}"

    # Check file size (safety check)
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 10:  # 10MB limit
        return False, f"Resume file too large: {file_size_mb:.2f}MB (max 10MB)"

    # Verify checksum if provided
    if expected_sha256:
        try:
            actual_sha256 = compute_sha256(file_path)
            if actual_sha256.lower() != expected_sha256.lower():
                return (
                    False,
                    f"Checksum mismatch: expected {expected_sha256}, got {actual_sha256}",
                )
        except Exception as e:
            return False, f"Failed to compute checksum: {e}"

    return True, None


class ResumeManifest:
    """Manages resume manifest and validation."""

    def __init__(self, manifest_path: Path, base_path: Path | None = None) -> None:
        """
        Initialize resume manifest.

        Args:
            manifest_path: Path to resume manifest CSV file
            base_path: Base path for resolving relative paths (defaults to manifest parent)
        """
        self.manifest_path = manifest_path
        self.base_path = base_path or manifest_path.parent
        self.manifest: dict[str, dict[str, Any]] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load manifest from CSV file."""
        import csv

        if not self.manifest_path.exists():
            logger.warning("Resume manifest not found", path=str(self.manifest_path))
            return

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                resume_id = row.get("resume_id", "").strip()
                if not resume_id:
                    continue

                relative_path = row.get("relative_path", "").strip()
                sha256 = row.get("sha256", "").strip() or None
                version = row.get("version", "").strip() or None

                # Resolve absolute path
                if relative_path:
                    abs_path = (self.base_path / relative_path).resolve()
                else:
                    abs_path = None

                # Compute checksum if missing
                if abs_path and abs_path.exists() and not sha256:
                    try:
                        sha256 = compute_sha256(abs_path)
                        logger.info(
                            "Computed checksum for resume",
                            resume_id=resume_id,
                            sha256=sha256,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to compute checksum",
                            resume_id=resume_id,
                            error=str(e),
                        )

                self.manifest[resume_id] = {
                    "resume_id": resume_id,
                    "relative_path": relative_path,
                    "absolute_path": abs_path,
                    "sha256": sha256,
                    "version": version,
                }

        logger.info("Loaded resume manifest", count=len(self.manifest))

    def get_resume_info(self, resume_id: str) -> dict[str, Any] | None:
        """
        Get resume information by ID.

        Args:
            resume_id: Resume identifier

        Returns:
            Dictionary with resume info or None if not found
        """
        return self.manifest.get(resume_id)

    def validate_resume(self, resume_id: str) -> tuple[bool, str | None, dict[str, Any] | None]:
        """
        Validate resume file exists and checksum matches.

        Args:
            resume_id: Resume identifier

        Returns:
            Tuple of (is_valid, error_message, resume_info)
            - is_valid: True if resume is valid
            - error_message: Error description if invalid, None if valid
            - resume_info: Resume information dictionary if found
        """
        resume_info = self.get_resume_info(resume_id)
        if not resume_info:
            return False, f"Resume ID not found in manifest: {resume_id}", None

        abs_path = resume_info.get("absolute_path")
        if not abs_path:
            return False, f"No path specified for resume: {resume_id}", resume_info

        is_valid, error_msg = validate_resume_file(abs_path, resume_info.get("sha256"))
        return is_valid, error_msg, resume_info

    def update_checksum(self, resume_id: str, sha256: str) -> None:
        """
        Update checksum for a resume in memory (does not persist to file).

        Args:
            resume_id: Resume identifier
            sha256: SHA256 checksum
        """
        if resume_id in self.manifest:
            self.manifest[resume_id]["sha256"] = sha256
