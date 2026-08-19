"""Data contracts that cross the private/public benchmark boundary."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import time
from typing import Any


QUARANTINE_SECONDS = 7 * 24 * 60 * 60
BACKUP_EXPIRY_SECONDS = 30 * 24 * 60 * 60
_PRIVATE_FIELDS = {
    "client_id",
    "contact",
    "email",
    "phone",
    "consent_document",
    "consent_document_path",
    "registry_path",
    "audit_notes",
    "raw_transcript",
}


@dataclass(frozen=True)
class EligibilityManifest:
    records: dict[str, dict[str, Any]]
    manifest_version: int = 1

    @property
    def checksum(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    def to_dict(self) -> dict[str, Any]:
        return {"manifest_version": self.manifest_version, "records": self.records}

    def withdraw(self, speaker_id: str) -> "EligibilityManifest":
        if speaker_id not in self.records:
            raise KeyError(f"unknown speaker: {speaker_id}")
        updated = {key: dict(value) for key, value in self.records.items()}
        updated[speaker_id]["consent_status"] = "withdrawn"
        updated[speaker_id]["eligibility"] = "ineligible"
        return EligibilityManifest(updated, self.manifest_version + 1)


def build_eligibility_manifest(records: list[dict[str, Any]]) -> EligibilityManifest:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        speaker_id = record.get("speaker_id")
        if not isinstance(speaker_id, str) or not speaker_id.startswith("spk-"):
            raise ValueError("speaker_id must be an opaque spk- identifier")
        if speaker_id in normalized:
            raise ValueError(f"duplicate speaker_id: {speaker_id}")
        consent_status = record.get("consent_status")
        usage_scope = record.get("usage_scope")
        if consent_status not in {"active", "withdrawn"}:
            raise ValueError("consent_status must be active or withdrawn")
        if not isinstance(usage_scope, str) or not usage_scope:
            raise ValueError("usage_scope must be non-empty")
        item = dict(record)
        item.setdefault("provenance", "private-human-recording")
        item.setdefault("qc_state", "pending")
        item["eligibility"] = "eligible" if consent_status == "active" else "ineligible"
        normalized[speaker_id] = item
    return EligibilityManifest(normalized)


def public_safe_export(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and copy the allowlisted public/worker record shape.

    This intentionally rejects rather than silently strips sensitive fields so
    an upstream schema change cannot leak registry-only data.
    """

    exported: list[dict[str, Any]] = []
    for record in records:
        private = _PRIVATE_FIELDS.intersection(record)
        if private:
            raise ValueError(f"private field present in public export: {sorted(private)[0]}")
        for key, value in record.items():
            lowered = key.casefold()
            if "path" in lowered and isinstance(value, str):
                candidate = Path(value)
                if candidate.is_absolute() or (len(value) >= 2 and value[1] == ":"):
                    raise ValueError("absolute path is not allowed in public export")
            if lowered in {"name", "address", "birth_date"}:
                raise ValueError(f"direct identifier field is not allowed: {key}")
        exported.append(dict(record))
    return exported


@dataclass(frozen=True)
class WithdrawalReceipt:
    manifest: EligibilityManifest
    quarantine_path: Path
    exclusion_token: str
    quarantine_until: float


class ParticipantPrivateStore:
    """Private per-speaker storage with bounded recovery quarantine."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.participants_dir = self.root / "participants"
        self.quarantine_dir = self.root / "quarantine"
        self.deletion_log = self.root / "deletion_verification.jsonl"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def withdraw(
        self,
        speaker_id: str,
        manifest: EligibilityManifest,
        *,
        requested_at: float | None = None,
    ) -> WithdrawalReceipt:
        if "/" in speaker_id or "\\" in speaker_id or speaker_id in {".", ".."}:
            raise ValueError("invalid speaker_id")
        timestamp = time.time() if requested_at is None else requested_at
        token = hashlib.sha256(f"{speaker_id}|{timestamp}|{manifest.checksum}".encode()).hexdigest()[:20]
        quarantine_path = self.quarantine_dir / f"{speaker_id}-{token}"
        source = self.participants_dir / speaker_id
        if source.exists():
            shutil.move(str(source), str(quarantine_path))
        else:
            quarantine_path.mkdir(parents=True)
        quarantine_until = timestamp + QUARANTINE_SECONDS
        metadata = {
            "exclusion_token": token,
            "quarantine_until": quarantine_until,
            "backup_expiry": timestamp + BACKUP_EXPIRY_SECONDS,
        }
        (quarantine_path / ".withdrawal.json").write_text(
            json.dumps(metadata, sort_keys=True), encoding="utf-8"
        )
        return WithdrawalReceipt(manifest.withdraw(speaker_id), quarantine_path, token, quarantine_until)

    def purge_expired(self, *, now: float | None = None) -> int:
        current = time.time() if now is None else now
        deleted = 0
        for quarantine_path in self.quarantine_dir.iterdir():
            metadata_path = quarantine_path / ".withdrawal.json"
            if not quarantine_path.is_dir() or not metadata_path.exists():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if current < float(metadata["quarantine_until"]):
                continue
            shutil.rmtree(quarantine_path)
            with self.deletion_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"exclusion_token": metadata["exclusion_token"], "deleted_at": current},
                        sort_keys=True,
                    )
                    + "\n"
                )
            deleted += 1
        return deleted
