import importlib.util
from pathlib import Path


def test_cached_corpus_rejects_different_bytes(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/fetch_samples.py"
    spec = importlib.util.spec_from_file_location("fetch_samples", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dest = tmp_path / "editable-grid.msapp"
    dest.write_bytes(b"not the pinned export")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(AssertionError("must not overwrite local mismatch")))
    assert module.fetch(dest, module.SAMPLES[dest.name]) is False
    assert dest.read_bytes() == b"not the pinned export"
