from __future__ import annotations

import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.beam_engine.beam_config import BeamSyncConfig
from app.services.beam_engine.beam_models import BeamModelFile, BeamSyncSummary
from app.services.beam_engine.beam_multipart_client import BeamMultipartClient
from app.services.beam_engine.beam_progress_service import BeamProgressService
from app.services.beam_engine.beam_volume_service import BeamVolumeService

Notify = Callable[..., None]


class BeamModelSyncService:
    @staticmethod
    def _items(manifest_models: list[dict[str, Any]]) -> list[BeamModelFile]:
        items=[]
        seen=set()
        for raw in manifest_models:
            if not raw.get("found", True):
                continue
            source=Path(str(raw.get("source_path") or "")).resolve()
            relative=str(raw.get("target_path") or raw.get("relative_path") or source.name).replace("\\", "/")
            if relative.startswith("models/"):
                relative=relative[7:]
            relative=str(PurePosixPath(relative.strip("/")))
            key=(str(source).casefold(),relative.casefold())
            if not source.is_file() or key in seen:
                continue
            seen.add(key)
            items.append(BeamModelFile(source,relative,relative.split("/",1)[0],source.stat().st_size,raw.get("sha256"),dict(raw)))
        return items

    @classmethod
    def sync(cls, db: Session, *, manifest_models: list[dict[str, Any]], remote_prefix: str, skip_identical: bool, notify: Notify) -> dict[str, Any]:
        config=BeamSyncConfig.load(db)
        items=cls._items(manifest_models)
        summary=BeamSyncSummary()
        total_bytes=sum(i.size_bytes for i in items)
        sent_before=0
        inventory=BeamVolumeService.metadata_index(config) if skip_identical else {}
        started=time.perf_counter()
        for index,item in enumerate(items,1):
            if BeamProgressService.is_cancelled():
                raise RuntimeError("Sincronización Beam cancelada por el usuario.")
            remote_path="/".join(p for p in (remote_prefix.strip("/\\").replace("\\","/"),item.relative_path) if p)
            destination=BeamVolumeService.remote_uri(config.volume_name,remote_path)
            if skip_identical and remote_path in inventory:
                summary.skipped+=1
                notify("beam-skipped", max(1,int(99*index/max(1,len(items)))), f"SKIPPED {item.relative_path}", {"file_name":item.source.name,"category":item.category,"file_index":index,"files_total":len(items),"file_progress":100,"global_progress":round(100*index/max(1,len(items)),2),"bytes_sent":sent_before,"bytes_total":total_bytes,"status":"SKIPPED"})
                continue
            error=None
            for attempt in range(1,config.retries+1):
                try:
                    def line(_text: str, metrics: dict[str, Any]) -> None:
                        if BeamProgressService.is_cancelled():
                            raise RuntimeError("Sincronización Beam cancelada por el usuario.")
                        current=sent_before+int(metrics.get("file_bytes_sent") or 0)
                        elapsed=max(.001,time.perf_counter()-started)
                        speed=int(metrics.get("speed_bps") or current/elapsed)
                        eta=int((total_bytes-current)/speed) if speed else 0
                        details={**metrics,"file_name":item.source.name,"category":item.category,"relative_path":item.relative_path,"file_index":index,"files_total":len(items),"global_progress":round(100*current/max(1,total_bytes),2),"bytes_sent":current,"bytes_total":total_bytes,"speed_bps":speed,"eta_seconds":eta,"attempt":attempt,"status":"UPLOADING"}
                        notify("beam-uploading", max(1,min(99,int(details["global_progress"]))), f"Beam {item.source.name} · {index}/{len(items)} · {details['file_progress']:.1f}%", details)
                    BeamMultipartClient.upload_file(config,item.source,destination,line)
                    summary.ok+=1; summary.bytes_sent+=item.size_bytes; sent_before+=item.size_bytes; error=None
                    break
                except Exception as exc:
                    error=exc
                    if attempt < config.retries:
                        time.sleep(min(5,attempt*2))
            if error is not None:
                summary.failed+=1
                summary.failures.append({"path":item.relative_path,"error":str(error)})
                notify("beam-failed", max(1,int(99*index/max(1,len(items)))), f"FAILED {item.relative_path}: {error}", {"file_name":item.source.name,"category":item.category,"file_index":index,"files_total":len(items),"status":"FAILED","attempts":config.retries})
        return {"volume_name":config.volume_name,"target":BeamVolumeService.remote_uri(config.volume_name,remote_prefix),"files_total":len(items),"files_uploaded":summary.ok,"files_failed":summary.failed,"files_skipped":summary.skipped,"bytes_total":total_bytes,"bytes_uploaded":summary.bytes_sent,"failures":summary.failures,"elapsed_seconds":round(time.perf_counter()-started,3),"transfer_mode":"beam-independent-multipart-per-file","windows_sdk_patch":True}
