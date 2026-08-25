"""每日訂單聚合：讀取 orders_raw 分區，驗證列數，寫出 orders_daily。"""

from __future__ import annotations

MIN_ROWS = 50_000


def load_partition(partition: str) -> list[dict]:
    """從 orders_raw 讀出指定日期分區的所有列。"""
    return read_table("orders_raw", partition=partition)


def validate_rowcount(rows: list[dict], partition: str) -> None:
    if len(rows) < MIN_ROWS:
        raise ValueError(f"partition {partition} has {len(rows)} rows, expected at least {MIN_ROWS}")


def aggregate(rows: list[dict]) -> dict:
    revenue = sum(row["amount"] for row in rows if row["status"] == "paid")
    return {"orders": len(rows), "revenue": revenue}


def run(partition: str) -> dict:
    rows = load_partition(partition)
    validate_rowcount(rows, partition)
    summary = aggregate(rows)
    write_table("orders_daily", partition=partition, rows=[summary])
    return summary
