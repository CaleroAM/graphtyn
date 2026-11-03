"""Bundled sample project the dashboard can register to be explored without user code."""
import shutil
from pathlib import Path

from fastapi import APIRouter

from ..core.storage import data_home

router = APIRouter()
SOURCE = Path(__file__).resolve().parent.parent / "demo_project"


def demo_path() -> Path:
    return data_home() / "demo-projects" / "tienda-demo"


@router.post("/api/demo")
def prepare_demo():
    """Copy the sample into the Graphtyn home; files the user already has there are kept."""
    target = demo_path()
    for source in sorted(SOURCE.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts:
            destination = target / source.relative_to(SOURCE)
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    return {"ok": True, "path": str(target), "name": target.name}
