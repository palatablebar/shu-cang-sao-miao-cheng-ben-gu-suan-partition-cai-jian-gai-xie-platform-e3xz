"""模板账本「聚合口径」纯标准库自测（不依赖数据库 / SQLAlchemy）。

运行：python3 scripts/_selftest_ledger.py

用内存中的假执行对象复刻 template_service 的分组聚合规则，验证：
  1. (window, fingerprint) 分组 → 同模板跨窗口拆成两行，不串账
  2. 累计扫描量/费用只对 is_billed=True 求和（重复投递不重复计费）
  3. 计数恒等式 execution = billed + duplicate + failed
  4. 覆盖率 = (execution - failed) / execution
  5. 排序：累计扫描量、执行次数两个维度
  6. 单次代表值取「最近一次计入执行」
"""
from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# --- stub sqlglot（与 _selftest_template 一致，仅为加载 template 模块） ---
if "sqlglot" not in sys.modules:
    sqlglot = types.ModuleType("sqlglot")
    errors = types.ModuleType("sqlglot.errors")

    class ParseError(Exception):
        pass

    class _Expression:
        pass

    exp = types.ModuleType("sqlglot.exp")
    exp.ParseError = ParseError
    exp.Expression = _Expression
    for _name in ("Literal", "Boolean", "Null", "Placeholder"):
        setattr(exp, _name, type(_name, (_Expression,), {}))
    sqlglot.parse_one = lambda *a, **k: (_ for _ in ()).throw(ParseError("stub"))
    sqlglot.exp = exp
    errors.ParseError = ParseError
    sqlglot.errors = errors
    sys.modules["sqlglot"] = sqlglot
    sys.modules["sqlglot.exp"] = exp
    sys.modules["sqlglot.errors"] = errors


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


template_mod = _load("template_mod2", "src/analysis/template.py")
hour_window = template_mod.hour_window
normalize_sql = template_mod.normalize_sql


@dataclass
class FakeExec:
    external_id: str
    sql_text: str
    executed_at: str
    run_status: str = "success"
    is_billed: bool = True
    scan_bytes: int = 0
    scan_cost_cny: float = 0.0
    duration_ms: int = 0
    title: str = "t"
    target_table: str = "dwd_order_detail"
    prunable: bool = True
    blocked_reason: str = "none"

    @property
    def window_start(self) -> str:
        return hour_window(self.executed_at)

    @property
    def fingerprint(self) -> str:
        return normalize_sql(self.sql_text)["fingerprint"]


PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}\n       got ={got!r}\n       want={want!r}")


# 复刻 template_service 的聚合（同口径：仅 is_billed 求和；失败/重复计入总数）
def aggregate(rows: list[FakeExec]):
    groups: dict[tuple[str, str], list[FakeExec]] = {}
    for r in rows:
        groups.setdefault((r.window_start, r.fingerprint), []).append(r)
    result = []
    for (window, fp), members in groups.items():
        billed = [m for m in members if m.is_billed]
        failed = [m for m in members if m.run_status == "failed"]
        dup = [m for m in members if not m.is_billed and m.run_status != "failed"]
        latest = max(billed, key=lambda m: m.executed_at, default=None)
        result.append(
            {
                "window": window,
                "fingerprint": fp,
                "execution_count": len(members),
                "billed_count": len(billed),
                "duplicate_count": len(dup),
                "failed_count": len(failed),
                "billed_scan_bytes": sum(m.scan_bytes for m in billed),
                "billed_cost_cny": round(sum(m.scan_cost_cny for m in billed), 6),
                "coverage_pct": round((len(members) - len(failed)) / len(members) * 100, 2) if members else 0.0,
                "single_scan_bytes": latest.scan_bytes if latest else 0,
            }
        )
    return result


SQL_A = "SELECT count(*) FROM dwd_order_detail WHERE dt = '2026-11-11'"
SQL_A2 = "SELECT count(*) FROM dwd_order_detail WHERE dt = '2026-11-12'"   # 同结构 → 同指纹
SQL_B = "SELECT id FROM ods_order_raw WHERE dt = '2026-11-11'"             # 不同结构

rows = [
    # 模板 A，09 窗：1 次计入 + 1 次重复投递（同参数）
    FakeExec("EX-1", SQL_A, "2026-11-12 09:05:00", scan_bytes=100, scan_cost_cny=0.1),
    FakeExec("EX-2", SQL_A, "2026-11-12 09:40:00", is_billed=False, scan_bytes=100, scan_cost_cny=0.1),
    # 模板 A，09 窗：换参数的另一次执行（不同 param → 仍计费）
    FakeExec("EX-3", SQL_A2, "2026-11-12 09:55:00", scan_bytes=120, scan_cost_cny=0.12),
    # 模板 A，10 窗：跨窗口，必须独立成行
    FakeExec("EX-4", SQL_A, "2026-11-12 10:15:00", scan_bytes=110, scan_cost_cny=0.11),
    # 模板 A，10 窗：1 次失败（不计费、扫描 0，但计入执行数与覆盖率）
    FakeExec("EX-5", SQL_A, "2026-11-12 10:48:00", run_status="failed", is_billed=False),
    # 模板 B，09 窗
    FakeExec("EX-6", SQL_B, "2026-11-12 09:20:00", scan_bytes=300, scan_cost_cny=0.3),
]

agg = aggregate(rows)
print("== 1. 分组：同模板跨窗口拆行，不串账 ==")
fp_a = normalize_sql(SQL_A)["fingerprint"]
fp_b = normalize_sql(SQL_B)["fingerprint"]
check("同结构不同参数 → 同指纹", normalize_sql(SQL_A)["fingerprint"] == normalize_sql(SQL_A2)["fingerprint"], True)
check("分组数 = 3（A@09, A@10, B@09）", len(agg), 3)
check("不同结构不同指纹", fp_a != fp_b, True)

a09 = next(g for g in agg if g["window"] == "2026-11-12 09:00" and g["fingerprint"] == fp_a)
a10 = next(g for g in agg if g["window"] == "2026-11-12 10:00" and g["fingerprint"] == fp_a)
b09 = next(g for g in agg if g["window"] == "2026-11-12 09:00" and g["fingerprint"] == fp_b)

print("== 2. 重复投递不重复计费（累计只算 is_billed） ==")
check("A@09 执行数=3", a09["execution_count"], 3)
check("A@09 计入=2", a09["billed_count"], 2)
check("A@09 重复=1", a09["duplicate_count"], 1)
check("A@09 累计扫描=220（100+120，重复的100剔除）", a09["billed_scan_bytes"], 220)
check("A@09 累计费用=0.22", a09["billed_cost_cny"], 0.22)

print("== 3. 失败执行单列、计入覆盖率 ==")
check("A@10 执行数=2（含1失败）", a10["execution_count"], 2)
check("A@10 异常数=1", a10["failed_count"], 1)
check("A@10 失败不计费→累计扫描=110", a10["billed_scan_bytes"], 110)
check("A@10 覆盖率=50.0", a10["coverage_pct"], 50.0)
check("A@09 无失败覆盖率=100.0", a09["coverage_pct"], 100.0)

print("== 4. 计数恒等式 ==")
for g in agg:
    check(f"{g['window']} 恒等式", g["execution_count"], g["billed_count"] + g["duplicate_count"] + g["failed_count"])

print("== 5. 排序维度 ==")
by_scan = sorted(agg, key=lambda g: g["billed_scan_bytes"], reverse=True)
check("按累计扫描量首位是 B@09(300)", (by_scan[0]["window"], by_scan[0]["fingerprint"]), ("2026-11-12 09:00", fp_b))
by_count = sorted(agg, key=lambda g: g["execution_count"], reverse=True)
check("按执行次数首位是 A@09(3)", (by_count[0]["window"], by_count[0]["fingerprint"]), ("2026-11-12 09:00", fp_a))

print("== 6. 单次代表值 = 最近一次计入执行 ==")
check("A@09 单次扫描=120（EX-3 最晚）", a09["single_scan_bytes"], 120)

print("== 7. 全局覆盖率 ==")
total_exec = sum(g["execution_count"] for g in agg)
total_failed = sum(g["failed_count"] for g in agg)
global_cov = round((total_exec - total_failed) / total_exec * 100, 2)
check("全局 6 执行 1 失败 → 83.33%", global_cov, 83.33)

print()
print(f"RESULT pass={PASS} fail={FAIL}")
sys.exit(1 if FAIL else 0)
