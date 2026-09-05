from pathlib import Path

from runpod_worker.generation_runtime.runtime import GenerationRuntime


ROOT = Path(__file__).resolve().parents[1]


def test_transport_registry_deduplicates_identical_generation_file_content(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    unique = tmp_path / "unique.png"
    first.write_bytes(b"same-image-bytes")
    second.write_bytes(b"same-image-bytes")
    unique.write_bytes(b"different-image-bytes")

    runtime = GenerationRuntime.__new__(GenerationRuntime)
    payload, metrics = runtime._externalize_transport(
        {
            "steps": [
                {
                    "outputs": {
                        "a": {
                            "__generation_file__": True,
                            "local_path": str(first),
                            "filename": "first.png",
                            "content_type": "image/png",
                            "node_id": "1",
                        },
                        "b": {
                            "__generation_file__": True,
                            "local_path": str(second),
                            "filename": "second.png",
                            "content_type": "image/png",
                            "node_id": "2",
                        },
                    }
                }
            ],
            "outputs": {
                "final": {
                    "__generation_file__": True,
                    "local_path": str(first),
                    "filename": "final.png",
                    "content_type": "image/png",
                    "node_id": "3",
                },
                "unique": {
                    "__generation_file__": True,
                    "local_path": str(unique),
                    "filename": "unique.png",
                    "content_type": "image/png",
                    "node_id": "4",
                },
            },
            "context": {},
        }
    )

    assert metrics["transport_generation_file_occurrences"] == 4
    assert metrics["transport_unique_file_count"] == 2
    assert metrics["transport_duplicate_file_occurrences"] == 2
    assert len(payload["files"]) == 2

    a_ref = payload["steps"][0]["outputs"]["a"]
    b_ref = payload["steps"][0]["outputs"]["b"]
    final_ref = payload["outputs"]["final"]
    unique_ref = payload["outputs"]["unique"]

    assert a_ref["__generation_file_ref__"] == b_ref["__generation_file_ref__"]
    assert a_ref["__generation_file_ref__"] == final_ref["__generation_file_ref__"]
    assert unique_ref["__generation_file_ref__"] != a_ref["__generation_file_ref__"]
    assert a_ref["filename"] == "first.png"
    assert b_ref["filename"] == "second.png"
    assert final_ref["node_id"] == "3"

    registry_file = payload["files"][a_ref["__generation_file_ref__"]]
    assert registry_file["__generation_file__"] is True
    assert registry_file["encoding"] == "base64"
    assert registry_file["data"].startswith("data:image/png;base64,")
    assert "sha256" in registry_file

    diagnostics = metrics["transport_unique_files"]
    assert len(diagnostics) == 2
    repeated = next(item for item in diagnostics if item["file_id"] == a_ref["__generation_file_ref__"])
    assert repeated["occurrence_count"] == 3
    assert repeated["paths"] == [
        "steps[0].outputs.a",
        "steps[0].outputs.b",
        "outputs.final",
    ]
    assert repeated["filenames"] == ["first.png", "second.png", "final.png"]
    assert repeated["node_ids"] == ["1", "2", "3"]


def test_completed_runtime_response_uses_registry_and_backend_accepts_refs():
    runtime_source = (ROOT / "runpod_worker/generation_runtime/runtime.py").read_text(encoding="utf-8")
    backend_source = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")

    assert '"files": transport_payload["files"]' in runtime_source
    assert '"__generation_file_ref__": file_id' in runtime_source
    assert "hashlib.sha256(content).hexdigest()" in runtime_source
    assert "transport_unique_file_count" in runtime_source
    assert "transport_saved_declared_file_bytes" in runtime_source

    assert 'value.get("__generation_file_ref__")' in backend_source
    assert "file_registry.get(file_id)" in backend_source
    assert "materialized_ref_cache" in backend_source
    assert "Legacy runtimes that inline ``__generation_file__`` continue to work." in backend_source


def test_transport_registry_prunes_intermediate_only_files_but_preserves_light_metadata(tmp_path):
    intermediate = tmp_path / "intermediate.png"
    final = tmp_path / "final.png"
    intermediate.write_bytes(b"intermediate-bytes")
    final.write_bytes(b"final-bytes")

    runtime = GenerationRuntime.__new__(GenerationRuntime)
    payload, metrics = runtime._externalize_transport(
        {
            "steps": [
                {
                    "outputs": {
                        "temp": {
                            "__generation_file__": True,
                            "local_path": str(intermediate),
                            "filename": "intermediate.png",
                            "content_type": "image/png",
                            "node_id": "10",
                        },
                        "final_copy": {
                            "__generation_file__": True,
                            "local_path": str(final),
                            "filename": "final-from-step.png",
                            "content_type": "image/png",
                            "node_id": "20",
                        },
                    }
                }
            ],
            "outputs": {
                "output_1": {
                    "__generation_file__": True,
                    "local_path": str(final),
                    "filename": "final.png",
                    "content_type": "image/png",
                    "node_id": "20",
                }
            },
            "context": {
                "input_image": {
                    "__generation_file__": True,
                    "local_path": str(intermediate),
                    "filename": "input.jpg",
                    "content_type": "image/jpeg",
                }
            },
        }
    )

    assert len(payload["files"]) == 1
    final_ref = payload["outputs"]["output_1"]
    assert "__generation_file_ref__" in final_ref
    assert payload["steps"][0]["outputs"]["final_copy"]["__generation_file_ref__"] == final_ref["__generation_file_ref__"]

    omitted_step = payload["steps"][0]["outputs"]["temp"]
    omitted_context = payload["context"]["input_image"]
    assert omitted_step["__generation_file_omitted__"] is True
    assert omitted_context["__generation_file_omitted__"] is True
    assert "data" not in omitted_step
    assert "local_path" not in omitted_step

    assert metrics["transport_discovered_unique_file_count"] == 2
    assert metrics["transport_unique_file_count"] == 1
    assert metrics["transport_omitted_intermediate_unique_file_count"] == 1
    assert metrics["transport_omitted_intermediate_declared_file_bytes"] == len(b"intermediate-bytes")

    diagnostics = metrics["transport_unique_files"]
    transported = next(item for item in diagnostics if item["transported"])
    omitted = next(item for item in diagnostics if not item["transported"])
    assert transported["file_id"] == final_ref["__generation_file_ref__"]
    assert "outputs.output_1" in transported["paths"]
    assert omitted["file_id"] is None
    assert "steps[0].outputs.temp" in omitted["paths"]
