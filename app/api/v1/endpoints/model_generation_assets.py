import base64
import hashlib
import hmac
import json
import re
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.v1.guards.internal_appweb_guard import internal_appweb_guard
from app.core.config import settings
from app.models.model_generation_asset import ModelGenerationAsset
from app.models.storage_file import StorageFile
from app.services.model_generation_asset_service import model_generation_asset_service
from app.services.storage_service import storage_service

router = APIRouter()


def _face_signature(payload: str) -> str:
    secret = (settings.APPWEB_INTERNAL_KEY or "").encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _encode_face_state(*, used_ids: list[int], current_pair: list[int]) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps({"u": used_ids, "c": current_pair}, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    payload = f"v3.{encoded}"
    return f"{payload}.{_face_signature(payload)}"


def _decode_face_state(token: object, ordered_ids: list[int]) -> tuple[list[int], list[int]]:
    if not isinstance(token, str) or not token:
        return [], []
    current = re.fullmatch(r"v3\.([A-Za-z0-9_-]+)\.([0-9a-f]{64})", token)
    if current:
        payload = f"v3.{current.group(1)}"
        if not hmac.compare_digest(_face_signature(payload), current.group(2)):
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        try:
            encoded = current.group(1) + "=" * (-len(current.group(1)) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
            used = [int(value) for value in decoded.get("u", [])]
            pair = [int(value) for value in decoded.get("c", [])]
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        if len(pair) not in {0, 2} or len(used) > 10000:
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        return list(dict.fromkeys(used)), pair

    # Compatibility with the temporary multi-pair index token. This lets a
    # deployment move forward or backward without invalidating saved drafts.
    indexed_history = re.fullmatch(r"v2\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)", token)
    if indexed_history:
        payload = f"v2.{indexed_history.group(1)}"
        expected = hmac.new(
            (settings.APPWEB_INTERNAL_KEY or "").encode("utf-8"),
            payload.encode("utf-8"), hashlib.sha256,
        ).digest()
        try:
            received = base64.urlsafe_b64decode(indexed_history.group(2) + "=" * (-len(indexed_history.group(2)) % 4))
            raw = indexed_history.group(1) + "=" * (-len(indexed_history.group(1)) % 4)
            pairs = json.loads(base64.urlsafe_b64decode(raw).decode("utf-8")).get("p", [])
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        if not hmac.compare_digest(expected, received) or not isinstance(pairs, list) or not pairs:
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        converted: list[list[int]] = []
        for pair in pairs[:5]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise HTTPException(status_code=400, detail="El historial facial no es válido.")
            first_index, second_index = int(pair[0]), int(pair[1])
            if first_index == second_index or min(first_index, second_index) < 0 or max(first_index, second_index) >= len(ordered_ids):
                raise HTTPException(status_code=400, detail="El historial facial no es válido.")
            converted.append([ordered_ids[first_index], ordered_ids[second_index]])
        used = list(dict.fromkeys(asset_id for pair in converted for asset_id in pair))
        return used, converted[0]

    # One-time migration from the original index-based AppWeb token.
    legacy = re.fullmatch(r"v1\.(\d+)\.(\d+)\.([A-Za-z0-9_-]+)", token)
    if legacy:
        payload = f"v1.{legacy.group(1)}.{legacy.group(2)}"
        expected = hmac.new(
            (settings.APPWEB_INTERNAL_KEY or "").encode("utf-8"),
            payload.encode("utf-8"), hashlib.sha256,
        ).digest()
        try:
            received = base64.urlsafe_b64decode(legacy.group(3) + "=" * (-len(legacy.group(3)) % 4))
        except ValueError:
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        first_index, second_index = int(legacy.group(1)), int(legacy.group(2))
        if (
            not hmac.compare_digest(expected, received)
            or first_index == second_index
            or first_index >= len(ordered_ids)
            or second_index >= len(ordered_ids)
        ):
            raise HTTPException(status_code=400, detail="El historial facial no es válido.")
        pair = [ordered_ids[first_index], ordered_ids[second_index]]
        return pair.copy(), pair
    raise HTTPException(status_code=400, detail="El historial facial no es válido.")


def _multipart_face_pair(*, first: bytes, first_type: str, second: bytes, second_type: str,
                         token: str, cycle_executions: int, remaining_executions: int) -> tuple[bytes, str]:
    boundary = f"tryon-face-{uuid4().hex}"
    chunks: list[bytes] = []

    def field(name: str, value: str) -> None:
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])

    def image(name: str, filename: str, content_type: str, content: bytes) -> None:
        chunks.extend([
            (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n').encode(),
            content, b"\r\n",
        ])

    field("history_token", token)
    field("cycle_executions", str(cycle_executions))
    field("remaining_executions", str(remaining_executions))
    safe_first_type = first_type if re.fullmatch(r"image/[A-Za-z0-9.+-]+", first_type) else "image/webp"
    safe_second_type = second_type if re.fullmatch(r"image/[A-Za-z0-9.+-]+", second_type) else "image/webp"
    image("face_reference", "face-reference.webp", safe_first_type, first)
    image("face_reference2", "face-reference2.webp", safe_second_type, second)
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary



@router.get("/private/facial-structures/count")
def private_face_count(
    _: None = Depends(internal_appweb_guard),
    db: Session = Depends(get_db),
):
    total = db.query(ModelGenerationAsset).filter(
        ModelGenerationAsset.tool_key == "facial_structures",
        ModelGenerationAsset.is_active.is_(True),
        ModelGenerationAsset.poster_storage_file_id.isnot(None),
    ).count()
    return {"total": total}


@router.get("/private/facial-structures/reference")
def private_face_reference(
    index: int = Query(ge=0),
    _: None = Depends(internal_appweb_guard),
    db: Session = Depends(get_db),
):
    row = db.query(ModelGenerationAsset).filter(
        ModelGenerationAsset.tool_key == "facial_structures",
        ModelGenerationAsset.is_active.is_(True),
        ModelGenerationAsset.poster_storage_file_id.isnot(None),
    ).order_by(ModelGenerationAsset.id.asc()).offset(index).limit(1).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Face reference not found.")
    stored = db.get(StorageFile, row.poster_storage_file_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Face reference file not found.")
    content = storage_service.read_bytes(db, storage_file=stored)
    return Response(
        content=content,
        media_type=stored.content_type or "image/webp",
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": 'inline; filename="face-reference.webp"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/private/facial-structures/select")
async def private_face_pair(
    request: Request,
    _: None = Depends(internal_appweb_guard),
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Solicitud de referencias inválida.")
    history_token = body.get("history_token") if isinstance(body, dict) else None
    reuse_current_pair = body.get("reuse_current_pair") is True if isinstance(body, dict) else False

    # The full active inventory and its StorageFile rows are resolved in one
    # query. Stable asset IDs drive the cycle; no image hashes or offsets.
    rows = (
        db.query(ModelGenerationAsset, StorageFile)
        .join(StorageFile, StorageFile.id == ModelGenerationAsset.poster_storage_file_id)
        .filter(
            ModelGenerationAsset.tool_key == "facial_structures",
            ModelGenerationAsset.is_active.is_(True),
            ModelGenerationAsset.poster_storage_file_id.isnot(None),
        )
        .order_by(ModelGenerationAsset.id.asc())
        .all()
    )
    if len(rows) < 2:
        raise HTTPException(status_code=409, detail="Se requieren al menos dos estructuras faciales activas.")

    by_id = {asset.id: stored for asset, stored in rows}
    active_ids = list(by_id)
    active_set = set(active_ids)
    used_ids, current_pair = _decode_face_state(history_token, active_ids)
    used_ids = [asset_id for asset_id in used_ids if asset_id in active_set]
    current_pair = [asset_id for asset_id in current_pair if asset_id in active_set]

    if reuse_current_pair:
        if len(current_pair) != 2 or current_pair[0] == current_pair[1]:
            raise HTTPException(status_code=409, detail="El par facial anterior ya no está disponible.")
        selected_ids = current_pair
    else:
        used_set = set(used_ids)
        available_ids = [asset_id for asset_id in active_ids if asset_id not in used_set]
        if len(available_ids) < 2:
            # Start a new cycle and, whenever possible, avoid an immediate
            # repeat of either face from the final pair of the previous cycle.
            previous_pair = set(current_pair)
            without_previous = [asset_id for asset_id in active_ids if asset_id not in previous_pair]
            available_ids = without_previous if len(without_previous) >= 2 else active_ids
            used_ids = []
        selected_ids = secrets.SystemRandom().sample(available_ids, 2)
        used_ids.extend(selected_ids)
        current_pair = selected_ids

    first_stored = by_id[selected_ids[0]]
    second_stored = by_id[selected_ids[1]]
    first_content = storage_service.read_bytes(db, storage_file=first_stored)
    second_content = storage_service.read_bytes(db, storage_file=second_stored)
    cycle_executions = len(active_ids) // 2
    remaining_executions = max(0, (len(active_ids) - len(set(used_ids))) // 2)
    content, boundary = _multipart_face_pair(
        first=first_content,
        first_type=first_stored.content_type or "image/webp",
        second=second_content,
        second_type=second_stored.content_type or "image/webp",
        token=_encode_face_state(used_ids=used_ids, current_pair=current_pair),
        cycle_executions=cycle_executions,
        remaining_executions=remaining_executions,
    )
    return Response(
        content=content,
        media_type=f"multipart/form-data; boundary={boundary}",
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
    )


@router.get("")
def list_assets(
    tool_key: str | None = None,
    tool_keys: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        if tool_key == "facial_structures" or (tool_keys and "facial_structures" in {item.strip() for item in tool_keys.split(",")}):
            raise ValueError("Unsupported tool key.")
        requested_tools = (
            [item.strip() for item in tool_keys.split(",") if item.strip()]
            if tool_keys
            else None
        )
        rows = model_generation_asset_service.list(
            db,
            tool_key=tool_key,
            tool_keys=requested_tools,
            active_only=True,
        )
        return {"items": [model_generation_asset_service.response(db, row) for row in rows], "total": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
