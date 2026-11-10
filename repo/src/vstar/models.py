from dataclasses import asdict, dataclass, field
from pathlib import Path
import math
import tomllib


@dataclass(frozen=True)
class AnalysisConfig:
    min_period_days: float = 0.05
    max_period_days: float = 8.0
    bin_minutes: float = 10.0
    samples_per_peak: int = 8
    min_points: int = 500
    period_tolerance: float = 0.05

    def __post_init__(self):
        for value in asdict(self).values():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Analysis parameters must be finite positive numbers")
        if self.min_period_days >= self.max_period_days:
            raise ValueError("min_period_days must be below max_period_days")
        if self.bin_minutes / 1440 > self.min_period_days / 4:
            raise ValueError("Bin width must preserve at least four bins per shortest period")
        if self.min_points < 20 or self.samples_per_peak < 2 or self.period_tolerance >= 1:
            raise ValueError("Invalid sample count, frequency resolution or period tolerance")


@dataclass
class Config:
    workspace: Path
    source: str = "historical"
    historical_dir: str = "repo/experiments/2026-11-09-pilot"
    runs_dir: str = "repo/runs"
    cache_dir: str = "repo/data"
    seed: int = 20261110
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    selection: dict = field(default_factory=dict)

    def path(self, name: str) -> Path:
        return (self.workspace / getattr(self, name)).resolve()

    def snapshot(self):
        return {**asdict(self), "workspace": str(self.workspace)}

    @classmethod
    def from_snapshot(cls, data):
        data = dict(data)
        data["workspace"] = Path(data["workspace"])
        data["analysis"] = AnalysisConfig(**data.get("analysis", {}))
        return cls(**data)


def load_config(path: Path) -> Config:
    path = path.resolve()
    with path.open("rb") as f:
        data = tomllib.load(f)
    data["workspace"] = (path.parent / data.get("workspace", "../..")).resolve()
    data["analysis"] = AnalysisConfig(**data.get("analysis", {}))
    config = Config(**data)
    if config.source not in {"historical", "mast"}:
        raise ValueError("source must be historical or mast")
    return config


def empty_submission():
    # A screening period is not automatically a verified catalog ephemeris.
    return dict.fromkeys([
        "name", "ra_deg", "dec_deg", "coordinate_source", "coordinate_epoch",
        "variability_type", "period_days", "period_error_days", "epoch",
        "epoch_time_standard", "epoch_event", "max_magnitude", "min_magnitude",
        "passband", "magnitude_source", "mean_magnitude", "amplitude_magnitude",
        "amplitude_passband", "discoverers", "references",
    ])
