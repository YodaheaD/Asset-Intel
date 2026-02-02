from __future__ import annotations

from uuid import UUID
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_search_index import AssetSearchIndex


# --- Scoring weights (tune later) ---
SCORE_SHA256 = 1.00
SCORE_ETAG = 0.95
SCORE_NEAR_SIZE_MAX = 0.75
SCORE_TEXT_MAX = 0.70


def _tokenize_for_search(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return " ".join(text.split()[:20])


def _near_size_score(src_len: int, other_len: int) -> float:
    if src_len <= 0 or other_len <= 0:
        return 0.0
    diff = abs(other_len - src_len) / float(src_len)
    if diff > 0.03:
        return 0.0
    return max(0.0, SCORE_NEAR_SIZE_MAX * (1.0 - (diff / 0.03)))


def _text_score(rank: float) -> float:
    k = 0.25  # tune sensitivity
    r = max(0.0, float(rank))
    return SCORE_TEXT_MAX * (r / (r + k)) if r > 0 else 0.0


def _first_words(text: str, n: int = 18) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    words = text.split()
    return " ".join(words[:n])


def _make_text_snippet(seed_query: str, preview: str, max_chars: int = 220) -> str | None:
    """
    Lightweight snippet:
    - Not true highlighting (no positions), but UI-friendly.
    - If preview exists, return a short trimmed preview.
    - (We keep it simple to avoid heavier DB functions.)
    """
    if not preview:
        return None
    s = preview.strip().replace("\n", " ")
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


def _badge_for_signal(signal_type: str) -> str:
    return {
        "sha256": "Exact duplicate",
        "etag": "Same ETag",
        "near_size": "Near duplicate",
        "text": "Text-related",
    }.get(signal_type, signal_type)


def _explain_top_signal(top: dict[str, Any], all_signals: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """
    Produce a short explanation + badges from signals.
    Explanation should read well in UI lists.
    """
    badges = []
    for s in all_signals:
        badges.append(_badge_for_signal(s["type"]))
    # Deduplicate while preserving order
    seen = set()
    badges = [b for b in badges if not (b in seen or seen.add(b))]

    t = top["type"]
    d = top.get("detail") or {}

    if t == "sha256":
        return "Exact duplicate (same SHA-256 fingerprint).", badges
    if t == "etag":
        return "Likely duplicate (same ETag from source).", badges
    if t == "near_size":
        # show approx similarity
        diff_ratio = d.get("diff_ratio")
        if isinstance(diff_ratio, (int, float)):
            pct = round(diff_ratio * 100.0, 2)
            return f"Near duplicate (same type, ~{pct}% size difference).", badges
        return "Near duplicate (same type and similar size).", badges
    if t == "text":
        return "Related by OCR text similarity.", badges

    return "Related asset.", badges


async def _get_index_row(db: AsyncSession, org_id: UUID, asset_id: UUID) -> AssetSearchIndex | None:
    res = await db.execute(
        select(AssetSearchIndex)
        .where(
            AssetSearchIndex.org_id == org_id,
            AssetSearchIndex.asset_id == asset_id,
        )
        .limit(1)
    )
    return res.scalar_one_or_none()


def _merge_candidate(
    acc: dict[str, dict[str, Any]],
    *,
    asset_id: str,
    base_fields: dict[str, Any],
    add_score: float,
    signal: str,
    signal_detail: dict[str, Any] | None = None,
) -> None:
    entry = acc.get(asset_id)
    if not entry:
        entry = {
            **base_fields,
            "asset_id": asset_id,
            "score": 0.0,
            "signals": [],
            "explanation": None,  # filled later
            "badges": [],         # filled later
            "snippet": None,       # filled later (text-related)
        }
        acc[asset_id] = entry

    entry["score"] = max(float(entry["score"]), float(add_score))
    entry["signals"].append(
        {
            "type": signal,
            "score": float(add_score),
            "detail": signal_detail or {},
        }
    )


def _finalize_candidate(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Sort signals by score desc and add explanation/badges/snippet fields.
    """
    signals = entry.get("signals") or []
    signals_sorted = sorted(signals, key=lambda s: float(s.get("score", 0.0)), reverse=True)
    entry["signals"] = signals_sorted

    top = signals_sorted[0] if signals_sorted else {"type": "unknown", "detail": {}}
    explanation, badges = _explain_top_signal(top, signals_sorted)

    entry["explanation"] = explanation
    entry["badges"] = badges

    # Add snippet if text-related signal exists
    has_text = any(s["type"] == "text" for s in signals_sorted)
    if has_text:
        seed_query = None
        for s in signals_sorted:
            if s["type"] == "text":
                seed_query = (s.get("detail") or {}).get("seed_query")
                break
        entry["snippet"] = _make_text_snippet(seed_query or "", entry.get("ocr_preview") or "")

    return entry


async def find_related_assets(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    limit_per_bucket: int = 20,
) -> dict[str, Any]:
    src = await _get_index_row(db, org_id, asset_id)
    if not src:
        return {
            "asset_id": str(asset_id),
            "note": "No search index entry for this asset yet. Run fingerprint/OCR first.",
            "buckets": {},
            "ranked": [],
        }

    buckets: dict[str, list[dict[str, Any]]] = {}
    candidates: dict[str, dict[str, Any]] = {}

    # 1) Exact duplicates: sha256
    if src.sha256:
        dup_rows = (
            await db.execute(
                select(AssetSearchIndex)
                .where(
                    AssetSearchIndex.org_id == org_id,
                    AssetSearchIndex.sha256 == src.sha256,
                    AssetSearchIndex.asset_id != asset_id,
                )
                .limit(limit_per_bucket)
            )
        ).scalars().all()

        bucket = []
        for r in dup_rows:
            aid = str(r.asset_id)
            row = {
                "asset_id": aid,
                "reason": "same_sha256",
                "sha256": r.sha256,
                "etag": r.etag,
                "content_type": r.content_type,
                "content_length": r.content_length,
                "ocr_preview": r.ocr_text_preview,
                "updated_at": r.updated_at,
            }
            bucket.append(row)
            _merge_candidate(
                candidates,
                asset_id=aid,
                base_fields=row,
                add_score=SCORE_SHA256,
                signal="sha256",
                signal_detail={"sha256": r.sha256},
            )
        buckets["exact_duplicates_sha256"] = bucket

    # 2) Strong duplicates: etag
    if src.etag:
        etag_rows = (
            await db.execute(
                select(AssetSearchIndex)
                .where(
                    AssetSearchIndex.org_id == org_id,
                    AssetSearchIndex.etag == src.etag,
                    AssetSearchIndex.asset_id != asset_id,
                )
                .limit(limit_per_bucket)
            )
        ).scalars().all()

        bucket = []
        for r in etag_rows:
            aid = str(r.asset_id)
            row = {
                "asset_id": aid,
                "reason": "same_etag",
                "sha256": r.sha256,
                "etag": r.etag,
                "content_type": r.content_type,
                "content_length": r.content_length,
                "ocr_preview": r.ocr_text_preview,
                "updated_at": r.updated_at,
            }
            bucket.append(row)
            _merge_candidate(
                candidates,
                asset_id=aid,
                base_fields=row,
                add_score=SCORE_ETAG,
                signal="etag",
                signal_detail={"etag": r.etag},
            )
        buckets["strong_duplicates_etag"] = bucket

    # 3) Near duplicates heuristic: same content_type + similar size (+/- 3%)
    if src.content_type and src.content_length:
        low = int(src.content_length * 0.97)
        high = int(src.content_length * 1.03)

        near_rows = (
            await db.execute(
                select(AssetSearchIndex)
                .where(
                    AssetSearchIndex.org_id == org_id,
                    AssetSearchIndex.content_type == src.content_type,
                    AssetSearchIndex.content_length.is_not(None),
                    AssetSearchIndex.content_length >= low,
                    AssetSearchIndex.content_length <= high,
                    AssetSearchIndex.asset_id != asset_id,
                )
                .order_by(func.abs(AssetSearchIndex.content_length - src.content_length))
                .limit(limit_per_bucket)
            )
        ).scalars().all()

        bucket = []
        for r in near_rows:
            aid = str(r.asset_id)
            other_len = int(r.content_length or 0)
            src_len = int(src.content_length)
            score = _near_size_score(src_len, other_len)

            row = {
                "asset_id": aid,
                "reason": "similar_size_and_type",
                "content_type": r.content_type,
                "content_length": r.content_length,
                "etag": r.etag,
                "sha256": r.sha256,
                "ocr_preview": r.ocr_text_preview,
                "updated_at": r.updated_at,
            }
            bucket.append(row)

            if score > 0:
                _merge_candidate(
                    candidates,
                    asset_id=aid,
                    base_fields=row,
                    add_score=score,
                    signal="near_size",
                    signal_detail={
                        "src_len": src_len,
                        "other_len": other_len,
                        "diff_ratio": abs(other_len - src_len) / float(src_len) if src_len else None,
                    },
                )

        buckets["near_duplicates_size"] = bucket

    # 4) Text related via FTS (seeded from OCR preview)
    seed_query = ""
    if src.ocr_text_preview:
        seed_query = _tokenize_for_search(src.ocr_text_preview)

    if seed_query:
        ts_query = func.plainto_tsquery("english", seed_query)
        rank = func.ts_rank_cd(AssetSearchIndex.ocr_tsv, ts_query)

        text_rows = (
            await db.execute(
                select(AssetSearchIndex, rank.label("rank"))
                .where(
                    AssetSearchIndex.org_id == org_id,
                    AssetSearchIndex.asset_id != asset_id,
                    AssetSearchIndex.ocr_tsv.is_not(None),
                    AssetSearchIndex.ocr_tsv.op("@@")(ts_query),
                )
                .order_by(func.coalesce(rank, 0).desc(), AssetSearchIndex.updated_at.desc())
                .limit(limit_per_bucket)
            )
        ).all()

        bucket = []
        for idx, rnk in text_rows:
            aid = str(idx.asset_id)
            rnk_f = float(rnk or 0)
            score = _text_score(rnk_f)

            row = {
                "asset_id": aid,
                "reason": "fts_overlap",
                "rank": rnk_f,
                "ocr_preview": idx.ocr_text_preview,
                "sha256": idx.sha256,
                "etag": idx.etag,
                "content_type": idx.content_type,
                "content_length": idx.content_length,
                "updated_at": idx.updated_at,
            }
            bucket.append(row)

            if score > 0:
                _merge_candidate(
                    candidates,
                    asset_id=aid,
                    base_fields=row,
                    add_score=score,
                    signal="text",
                    signal_detail={"rank": rnk_f, "seed_query": seed_query},
                )
        buckets["text_related"] = bucket

    # Unified ranked list + explainability fields
    ranked = []
    for entry in candidates.values():
        ranked.append(_finalize_candidate(entry))

    ranked.sort(key=lambda x: (float(x.get("score", 0.0)), x.get("updated_at") or 0), reverse=True)

    return {
        "asset_id": str(asset_id),
        "source": {
            "sha256": src.sha256,
            "etag": src.etag,
            "content_type": src.content_type,
            "content_length": src.content_length,
            "seed_query": _first_words(seed_query, 18) if seed_query else None,
        },
        "buckets": buckets,
        "ranked": ranked,
    }
