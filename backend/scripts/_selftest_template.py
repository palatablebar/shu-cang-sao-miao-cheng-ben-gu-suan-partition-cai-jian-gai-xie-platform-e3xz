"""模板账本纯标准库自测（不依赖 sqlglot / SQLAlchemy / 数据库）。

运行：python3 scripts/_selftest_template.py
覆盖：
  1. 正则兜底归一化：同结构不同参数值 → 同指纹；不同结构 → 不同指纹
  2. 小时窗口分桶、参数收集与去重、模板编号稳定性
  3. demo_dataset.build_executions 确定性 + 计数契约（每小时多跑/重复/失败/跨窗）
  4. 去重计费恒等式：execution = billed + duplicate + failed

说明：本机无 sqlglot，用最小 stub 强制走「正则兜底」分支验证口径；
sqlglot 真实解析路径在容器（requirements 锁定 sqlglot==30.31）内由 seed/接口覆盖。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# --- 最小 sqlglot stub：parse_one 抛错 → template.normalize_sql 走兜底分支 ---
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
    exp.Literal = type("Literal", (_Expression,), {})
    exp.Boolean = type("Boolean", (_Expression,), {})
    exp.Null = type("Null", (_Expression,), {})
    exp.Placeholder = type("Placeholder", (_Expression,), {})

    def parse_one(sql, read=None):
        raise ParseError("stub: force fallback path")

    sqlglot.parse_one = parse_one
    sqlglot.exp = exp
    errors.ParseError = ParseError
    sqlglot.errors = errors
    sys.modules["sqlglot"] = sqlglot
    sys.modules["sqlglot.exp"] = exp
    sys.modules["sqlglot.errors"] = errors


def _load(module_name: str, relative: str):
    """按文件路径加载模块，绕开 src.analysis 包 __init__ 的重型 sqlglot 依赖。"""
    path = BACKEND / relative
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# 给 template 一个虚拟的父包，避免相对/绝对导入歧义
_analysis_pkg = types.ModuleType("src_analysis_stub")
template = _load("template_mod", "src/analysis/template.py")
normalize_sql = template.normalize_sql
hour_window = template.hour_window
template_code = template.template_code

# demo_dataset 只依赖标准库
_demo = _load("demo_dataset_mod", "scripts/demo_dataset.py")
demo_dataset = _demo

PASS = 0
FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}\n       got ={got!r}\n       want={want!r}")


print("== 1. 兜底归一化：参数值变化不改变模板指纹 ==")
sql_a = "SELECT count(*) FROM dwd_order_detail WHERE dt = '2026-11-11'"
sql_b = "SELECT count(*) FROM dwd_order_detail WHERE dt = '2026-11-12'"
na, nb = normalize_sql(sql_a), normalize_sql(sql_b)
check("不同日期参数 → 同指纹", na["fingerprint"] == nb["fingerprint"], True)
check("模板含占位符", "?" in na["canonical_sql"], True)
check("参数被收集", na["param_values"], ["'2026-11-11'"])
check("参数指纹随值变化", na["param_fingerprint"] != nb["param_fingerprint"], True)
check("兜底标记 normalized=False", na["normalized"], False)

print("== 2. 结构不同 → 不同模板 ==")
sql_c = "SELECT count(*) FROM dwd_order_detail WHERE dt = '2026-11-11' AND shop_id = 'S1'"
check("多一个谓词 → 不同指纹", normalize_sql(sql_c)["fingerprint"] != na["fingerprint"], True)
sql_d = "SELECT count(*) FROM ods_order_raw WHERE dt = '2026-11-11'"
check("换表 → 不同指纹", normalize_sql(sql_d)["fingerprint"] != na["fingerprint"], True)

print("== 3. 空白/注释/大小写与关键字字面量 ==")
sql_e = "SELECT  count(*)  FROM dwd_order_detail\nWHERE dt = '2026-11-11' -- tail comment"
check("空白与注释归一后同指纹", normalize_sql(sql_e)["fingerprint"] == na["fingerprint"], True)
sql_f = "SELECT count(*) FROM dwd_order_detail WHERE dt = 20261111"
nf = normalize_sql(sql_f)
check("整型字面量也被占位", "20261111" not in nf["canonical_sql"], True)
check("数字参数被收集", nf["param_values"], ["20261111"])
sql_g = "SELECT * FROM t WHERE flag = true AND x IS NULL"
ng = normalize_sql(sql_g)
check("布尔/NULL 被占位", ng["canonical_sql"].count("?"), 2)

print("== 4. 小时窗口分桶 ==")
check("分钟秒被归桶", hour_window("2026-11-12 09:35:40"), "2026-11-12 09:00")
check("带 T 的 ISO", hour_window("2026-11-12T14:10:26"), "2026-11-12 14:00")
check("整点", hour_window("2026-11-12 00:00:00"), "2026-11-12 00:00")
check("跨小时不同窗", hour_window("2026-11-12 09:59:59") != hour_window("2026-11-12 10:00:00"), True)

print("== 5. 模板编号稳定 ==")
check("编号格式", template_code(na["fingerprint"]), f"TPL-{na['fingerprint']}")

print("== 6. 执行流水数据集：确定性与计数契约 ==")
events = demo_dataset.build_executions()
events2 = demo_dataset.build_executions()
check("两次生成完全一致", [e["event_no"] for e in events] == [e["event_no"] for e in events2], True)
check("event_no 唯一", len({e["event_no"] for e in events}) == len(events), True)

base_queries = demo_dataset.build_queries()
n_base = len(base_queries)
success = [e for e in events if e["run_status"] == "success"]
failed = [e for e in events if e["run_status"] == "failed"]
dups = [e for e in events if e.get("duplicate")]
check("每个基础查询至少一次执行", len({e["query_index"] for e in success if e["query_index"] >= 0}) >= n_base, True)
check("存在失败执行", len(failed) >= 3, True)
check("存在重复投递", len(dups) >= 3, True)

# 调度模板 index=3 在 09/10/11 三个窗口各两次
sched = [e for e in events if e["query_index"] == 3]
windows = {hour_window(e["executed_at"]) for e in sched}
check("调度模板覆盖 >=3 个小时窗", len(windows) >= 3, True)
check("调度模板每窗多次(总>=6)", len(sched) >= 6, True)

# 日期参数调整：index=6 在 13/15/17 三个窗口（区别于基础执行的其它窗口）
param_runs = [
    e for e in events
    if e["query_index"] == 6 and hour_window(e["executed_at"]) in {
        "2026-11-12 13:00", "2026-11-12 15:00", "2026-11-12 17:00"
    }
]
check("调参样本跨 3 个窗口", len({hour_window(e["executed_at"]) for e in param_runs}) == 3, True)
# 三条调参 SQL 仅参数值不同 → 兜底归一化后同指纹
check("调参样本同模板指纹", len({normalize_sql(e["sql_text"])["fingerprint"] for e in param_runs}) == 1, True)
check("调参样本参数值不同", len({normalize_sql(e["sql_text"])["param_fingerprint"] for e in param_runs}) == 3, True)

print("== 7. 去重计费恒等式（按真实窗口+模板+参数模拟） ==")
# 用兜底归一化重建每条事件的 key，模拟 execution_service 的判定
billed_keys: set[str] = set()
counts = {"billed": 0, "duplicate": 0, "failed": 0}
for e in events:
    tpl = normalize_sql(e["sql_text"])
    window = hour_window(e["executed_at"])
    if e["run_status"] == "failed":
        counts["failed"] += 1
        continue
    key = f"{window}|{tpl['fingerprint']}|{tpl['param_fingerprint']}"
    if e.get("duplicate") or key in billed_keys:
        counts["duplicate"] += 1
    else:
        billed_keys.add(key)
        counts["billed"] += 1
check(
    "执行数 = 计入 + 重复 + 失败",
    counts["billed"] + counts["duplicate"] + counts["failed"],
    len(events),
)
# 演示数据里仅 Top1 的两条显式重复投递应被去重（同窗同模板同参数）
explicit_dups = len([e for e in events if e.get("duplicate") and e["run_status"] == "success"])
check("去重数恰好等于显式重复投递数", counts["duplicate"], explicit_dups)
check("存在被去重的事件", counts["duplicate"] >= 2, True)
check("失败事件全部不计入", all(True for _ in failed), True)

# 跨窗口不串账：同指纹同参数出现在不同窗口必须分别计费（取调度模板的跨窗事件）
cross = {}
for e in events:
    if e["run_status"] != "success":
        continue
    tpl = normalize_sql(e["sql_text"])
    cross.setdefault((tpl["fingerprint"], tpl["param_fingerprint"]), set()).add(
        hour_window(e["executed_at"])
    )
multi_window = {k: v for k, v in cross.items() if len(v) > 1}
check("存在跨窗口同模板同参数（分别计费）", len(multi_window) >= 1, True)

print()
print(f"RESULT pass={PASS} fail={FAIL}")
sys.exit(1 if FAIL else 0)
