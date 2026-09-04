#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""compute 平台历史上传记录去重回填 / 行级去重脚本。

背景
----
上传接口升级为 L1(file_hash) + L2(content_hash) + L3(row_hash) 三层去重后，
只有"改动之后"的新上传会被判重。历史已上传记录 content_hash / row_hash 为 NULL，
无法参与判重。本脚本做三件事：

  1. 回填 content_hash：对 data_uploads 中 content_hash 为 NULL 的记录，
     用其 solder_paste_data.raw_payload 重建 DataFrame，套用与上传接口同一算法的
     calculate_content_hash 算出内容哈希并写回。
     （file_hash 依赖原始字节，历史上传已无原文件，故不回填，保持 NULL。）

  2. 按 content_hash 去重：相同内容的多条上传只保留最早一条(id 最小)，
     其余连同其 solder_paste_data 数据行、关联的 experiments 记录一并删除。

  3. 回填 row_hash：为 solder_paste_data 中 row_hash 为 NULL 的每一行计算行哈希写回。
     这是 L3 行级去重对历史数据生效的前提——历史行必须先有 row_hash，未来上传才能与之判重。
     加 --dedup-rows 可进一步删除库内已存在的重复数据行（保留每组最早一条，并回写 row_count）。

用法
----
  python backend/scripts/backfill_dedup.py                 # 默认 dry-run：仅打印，不改动数据
  python backend/scripts/backfill_dedup.py --apply        # 真正执行 content_hash 回填与删除
  python backend/scripts/backfill_dedup.py --apply --dedup-rows   # 额外删除库内重复数据行

注意：删除不可逆。建议先 dry-run 确认，再 --apply。
"""
import argparse
import hashlib
import json
import os
import sys

# 让脚本能 import backend 包。
# 项目结构：compute/ 为根，compute/backend/ 即名为 "backend" 的 namespace 包，
# 故需把 compute/ 加入 sys.path（而非 compute/backend）。
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from dotenv import load_dotenv

# compute/.env 位于 compute/backend 的上一级
load_dotenv(os.path.join(BACKEND_DIR, "..", ".env"))

from backend.app.core.database import SessionLocal
from backend.app.models.experiment import DataUpload, SolderPasteData, Experiment


def calculate_content_hash(df: pd.DataFrame) -> str:
    """与 endpoints.upload_data 中完全一致的 L2 内容哈希算法。

    列名排序 + NaN 归一为 None + json.dumps(sort_keys, default=str)，保证
    同内容(即使列序被打乱)哈希一致，异内容哈希不同。
    """
    cols = sorted(str(c) for c in df.columns)
    sub = df[cols]
    records = sub.where(sub.notna(), None).to_dict(orient="records")
    blob = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def calculate_row_hash(payload: dict) -> str:
    """与 endpoints.upload_data 中完全一致的 L3 行哈希算法。

    基于 row_to_record 生成的 raw_payload（NaN 已归一为 None），列名排序后 sha256。
    """
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def compute_hash_map(db):
    """为每条上传记录计算 content_hash（DB 已有则直接复用，否则从 raw_payload 重建）。

    返回 {upload_id: content_hash_or_None}
    """
    hash_map = {}
    for up in db.query(DataUpload).all():
        if up.content_hash:
            hash_map[up.id] = up.content_hash
            continue
        rows = db.query(SolderPasteData).filter(SolderPasteData.upload_id == up.id).all()
        payloads = [r.raw_payload for r in rows if isinstance(r.raw_payload, dict)]
        if not payloads:
            hash_map[up.id] = None  # 无数据行，无法计算
            continue
        hash_map[up.id] = calculate_content_hash(pd.DataFrame(payloads))
    return hash_map


def backfill(db, hash_map, dry_run):
    """把计算出的 content_hash 写回 DB（仅当 DB 中为 NULL 且有值时）。"""
    updated = 0
    skipped = 0
    for up_id, ch in hash_map.items():
        up = db.get(DataUpload, up_id)
        if up.content_hash:
            continue
        if ch is None:
            print(f"  [skip]     upload id={up_id} filename={up.filename!r} 无数据行，跳过回填")
            skipped += 1
            continue
        print(f"  [backfill] upload id={up_id} filename={up.filename!r} content_hash={ch[:12]}...")
        if not dry_run:
            up.content_hash = ch
        updated += 1
    if not dry_run and updated:
        db.commit()
    return updated, skipped


def plan_dedup(db, hash_map):
    """按 content_hash 分组，返回需要删除的 upload_id 列表(保留每组最小 id)。"""
    groups = {}
    for up_id, ch in hash_map.items():
        if ch is None:
            continue
        groups.setdefault(ch, []).append(up_id)

    duplicate_ids = []
    for ch, ids in groups.items():
        if len(ids) <= 1:
            continue
        ids_sorted = sorted(ids)
        keep_id = ids_sorted[0]
        for dup_id in ids_sorted[1:]:
            n_rows = db.query(SolderPasteData).filter(SolderPasteData.upload_id == dup_id).count()
            up = db.get(DataUpload, dup_id)
            print(f"  [dup] content_hash={ch[:12]}... 保留 id={keep_id} | 删除 id={dup_id} "
                  f"filename={up.filename!r} 含 {n_rows} 条数据")
            duplicate_ids.append(dup_id)
    return duplicate_ids


def apply_delete(db, duplicate_ids):
    deleted_uploads = deleted_rows = deleted_exps = 0
    for dup_id in duplicate_ids:
        n_rows = db.query(SolderPasteData).filter(SolderPasteData.upload_id == dup_id).count()
        # 关联 experiments（properties_y 中以 upload_id 记录）
        exp_q = db.query(Experiment).filter(Experiment.properties_y["upload_id"].astext == str(dup_id))
        n_exp = exp_q.count()
        exp_q.delete()
        db.query(SolderPasteData).filter(SolderPasteData.upload_id == dup_id).delete()
        db.query(DataUpload).filter(DataUpload.id == dup_id).delete()
        deleted_rows += n_rows
        deleted_exps += n_exp
        deleted_uploads += 1
        print(f"  [deleted] upload id={dup_id} 数据行={n_rows} 关联实验={n_exp}")
    db.commit()
    return deleted_uploads, deleted_rows, deleted_exps


def backfill_row_hashes(db, dry_run):
    """为 solder_paste_data 中 row_hash 为 NULL 的行计算并写回行哈希。

    这一步是 L3 行级去重生效的前提：历史行必须先有 row_hash，未来上传才能
    与之判重。保留最早出现的重复行（id 最小）。
    """
    updated = kept_as_is = 0
    rows = db.query(SolderPasteData).filter(SolderPasteData.row_hash.is_(None)).all()
    for r in rows:
        if not isinstance(r.raw_payload, dict):
            kept_as_is += 1
            continue
        r.row_hash = calculate_row_hash(r.raw_payload)
        updated += 1
    # flush 使后续查询能看到新哈希（dry-run 下不 commit，进程结束自动丢弃）
    if updated:
        db.flush()
    if not dry_run and updated:
        db.commit()
    return updated, kept_as_is


def plan_dedup_rows(db):
    """按 row_hash 分组，找出库内重复行（跨上传 / 同上传内部）。

    返回需要删除的行 id 列表（每组保留 id 最小的一条）。
    """
    groups = {}
    for r in db.query(SolderPasteData).filter(SolderPasteData.row_hash.isnot(None)).all():
        if not r.row_hash:
            continue
        groups.setdefault(r.row_hash, []).append(r.id)

    duplicate_row_ids = []
    dup_groups = 0
    dup_rows = 0
    for rh, ids in groups.items():
        if len(ids) <= 1:
            continue
        dup_groups += 1
        ids_sorted = sorted(ids)
        duplicate_row_ids.extend(ids_sorted[1:])
        dup_rows += len(ids_sorted) - 1
    print(f"  检测到 {dup_groups} 组重复行（共 {dup_rows} 条待删除），保留每组最早一条。")
    return duplicate_row_ids


def apply_delete_rows(db, duplicate_row_ids):
    """删除重复行，并回写所属上传记录的 row_count，使其与真实数据行数一致。"""
    # 先记录受影响的 upload_id
    affected = {}
    rows = db.query(SolderPasteData.id, SolderPasteData.upload_id).filter(
        SolderPasteData.id.in_(duplicate_row_ids)
    ).all()
    for rid, uid in rows:
        affected[uid] = affected.get(uid, 0) + 1

    n = db.query(SolderPasteData).filter(SolderPasteData.id.in_(duplicate_row_ids)).delete(
        synchronize_session=False
    )
    db.commit()

    # 回写 row_count
    for uid, cnt in affected.items():
        up = db.get(DataUpload, uid)
        if up is not None:
            up.row_count = max((up.row_count or 0) - cnt, 0)
    db.commit()
    return n


def main():
    parser = argparse.ArgumentParser(description="compute 平台历史上传去重回填 / 行级去重")
    parser.add_argument("--apply", action="store_true", help="真正执行回填与删除（默认 dry-run）")
    parser.add_argument("--dedup-rows", action="store_true",
                        help="额外执行库内行级去重（删除重复数据行，保留每组最早一条）。需配合 --apply")
    args = parser.parse_args()
    dry_run = not args.apply
    dedup_rows = args.dedup_rows

    db = SessionLocal()
    try:
        print("=" * 64)
        print("阶段1：计算 / 回填 content_hash")
        print("=" * 64)
        hash_map = compute_hash_map(db)
        total = len(hash_map)
        with_hash = sum(1 for v in hash_map.values() if v)
        print(f"上传记录总数={total}，已有 content_hash={with_hash}，需计算={total - with_hash}")
        updated, skipped = backfill(db, hash_map, dry_run)
        print(f"回填：更新 {updated} 条，跳过(无数据) {skipped} 条  [dry_run={dry_run}]")

        print("\n" + "=" * 64)
        print("阶段2：按 content_hash 去重规划")
        print("=" * 64)
        duplicate_ids = plan_dedup(db, hash_map)

        if not duplicate_ids:
            print("未发现重复内容的上传记录，无需清理。")
        else:
            print(f"\n将删除 {len(duplicate_ids)} 条重复上传记录。")
            if dry_run:
                print("（dry-run 模式，未改动任何数据。确认无误后加 --apply 真正执行）")
            else:
                print("\n" + "=" * 64)
                print("阶段3：执行 content_hash 去重删除")
                print("=" * 64)
                du, dr, de = apply_delete(db, duplicate_ids)
                print(f"清理完成：删除上传记录 {du} 条，数据行 {dr} 条，关联实验 {de} 条。")

        print("\n" + "=" * 64)
        print("阶段4：回填 solder_paste_data.row_hash（L3 行级去重的生效前提）")
        print("=" * 64)
        ru, rk = backfill_row_hashes(db, dry_run)
        print(f"行哈希回填：更新 {ru} 条，跳过(无 payload) {rk} 条  [dry_run={dry_run}]")

        if dedup_rows:
            print("\n" + "=" * 64)
            print("阶段5：库内行级去重规划/执行")
            print("=" * 64)
            dup_row_ids = plan_dedup_rows(db)
            if not dup_row_ids:
                print("未发现库内重复数据行。")
            elif dry_run:
                print("（dry-run 模式，未删除。确认无误后加 --apply --dedup-rows 真正执行）")
            else:
                n = apply_delete_rows(db, dup_row_ids)
                print(f"行级去重完成：删除重复数据行 {n} 条，并已回写各上传记录的 row_count。")
        else:
            print("\n（未指定 --dedup-rows：本次跳过库内行级删除，仅回填 row_hash。"
                  "若需清理库内重复行，请加 --dedup-rows 重新运行。）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
