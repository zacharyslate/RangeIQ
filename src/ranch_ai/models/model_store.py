from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import pickle
from typing import Any

import pandas as pd

from ranch_ai.models.forage_model import ForageModelArtifacts
from ranch_ai.models.stress_model import StressModelArtifacts


MODEL_STORE_VERSION = 1


@dataclass(frozen=True)
class StoredModelBundle:
    forage_artifacts: ForageModelArtifacts
    stress_artifacts: StressModelArtifacts
    metadata: dict[str, Any]


class WorkspaceModelStore:
    def __init__(self, model_dir: str | Path | None, *, workspace_id: str | None, enabled: bool = True) -> None:
        self.workspace_id = (workspace_id or "").strip()
        self.enabled = bool(enabled and self.workspace_id and model_dir is not None)
        self.model_dir = Path(model_dir) if model_dir is not None else None

    @property
    def metadata_path(self) -> Path | None:
        if self.model_dir is None:
            return None
        return self.model_dir / "metadata.json"

    @property
    def forage_artifacts_path(self) -> Path | None:
        if self.model_dir is None:
            return None
        return self.model_dir / "forage_model.pkl"

    @property
    def stress_artifacts_path(self) -> Path | None:
        if self.model_dir is None:
            return None
        return self.model_dir / "stress_model.pkl"

    @staticmethod
    def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()
        sort_columns = [column for column in ["pasture_id", "week_start"] if column in frame.columns]
        if sort_columns:
            frame = frame.sort_values(sort_columns).reset_index(drop=True)
        else:
            frame = frame.reset_index(drop=True)
        frame = frame.reindex(sorted(frame.columns), axis=1)

        for column in frame.columns:
            if pd.api.types.is_datetime64_any_dtype(frame[column]):
                frame[column] = pd.to_datetime(frame[column], utc=False).dt.strftime("%Y-%m-%dT%H:%M:%S")
            elif pd.api.types.is_object_dtype(frame[column]) or pd.api.types.is_string_dtype(frame[column]):
                frame[column] = frame[column].fillna("").astype(str)

        return frame

    @classmethod
    def dataset_signature(cls, df: pd.DataFrame, *, random_state: int) -> str:
        frame = cls._normalize_frame(df)
        payload = json.dumps(
            {
                "version": MODEL_STORE_VERSION,
                "random_state": int(random_state),
                "columns": list(frame.columns),
                "rows": int(len(frame)),
            },
            sort_keys=True,
        ).encode("utf-8")
        digest = hashlib.sha256(payload)
        row_hashes = pd.util.hash_pandas_object(frame, index=False, categorize=False).to_numpy(dtype="uint64", copy=False)
        digest.update(row_hashes.tobytes())
        return digest.hexdigest()

    def load_matching(self, df: pd.DataFrame, *, random_state: int) -> StoredModelBundle | None:
        if not self.enabled or self.metadata_path is None or self.forage_artifacts_path is None or self.stress_artifacts_path is None:
            return None
        if not self.metadata_path.exists() or not self.forage_artifacts_path.exists() or not self.stress_artifacts_path.exists():
            return None

        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        expected_signature = self.dataset_signature(df, random_state=random_state)
        if metadata.get("dataset_signature") != expected_signature:
            return None

        with self.forage_artifacts_path.open("rb") as forage_file:
            forage_artifacts = pickle.load(forage_file)
        with self.stress_artifacts_path.open("rb") as stress_file:
            stress_artifacts = pickle.load(stress_file)

        return StoredModelBundle(
            forage_artifacts=forage_artifacts,
            stress_artifacts=stress_artifacts,
            metadata=metadata,
        )

    def save(
        self,
        df: pd.DataFrame,
        *,
        random_state: int,
        forage_artifacts: ForageModelArtifacts,
        stress_artifacts: StressModelArtifacts,
    ) -> dict[str, Any]:
        if not self.enabled or self.model_dir is None or self.metadata_path is None or self.forage_artifacts_path is None or self.stress_artifacts_path is None:
            return {
                "enabled": False,
                "status": "disabled",
                "workspace_id": self.workspace_id or None,
            }

        self.model_dir.mkdir(parents=True, exist_ok=True)
        dataset_signature = self.dataset_signature(df, random_state=random_state)

        with self.forage_artifacts_path.open("wb") as forage_file:
            pickle.dump(forage_artifacts, forage_file)
        with self.stress_artifacts_path.open("wb") as stress_file:
            pickle.dump(stress_artifacts, stress_file)

        metadata = {
            "version": MODEL_STORE_VERSION,
            "workspace_id": self.workspace_id,
            "dataset_signature": dataset_signature,
            "random_state": int(random_state),
            "saved_at": pd.Timestamp.utcnow().isoformat(),
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "selected_forage_model": forage_artifacts.selected_model_name,
            "forage_metrics": forage_artifacts.metrics,
            "stress_metrics": stress_artifacts.metrics,
        }
        self.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def summary(self, *, status: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "status": status,
            "workspace_id": self.workspace_id or None,
            "model_dir": str(self.model_dir) if self.model_dir is not None else None,
            "metadata": metadata or {},
        }
