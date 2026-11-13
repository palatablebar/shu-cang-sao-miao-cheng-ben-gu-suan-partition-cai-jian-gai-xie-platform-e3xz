"""查询模板归一化：把「结构相同、仅参数值不同」的 SQL 归并为同一个模板。

口径（与需求「按时间窗把结构和参数值相同的执行归为一个查询模板」对齐）
------------------------------------------------------------------
1. 用 sqlglot 做真实解析（PostgreSQL 方言），把所有字面量（字符串/数字/布尔/NULL）
   以及 IN 列表统一替换成位置占位符 ``?``，再规范化空白与大小写无关的结构，
   得到 **模板 SQL**（canonical_sql）。
2. ``fingerprint = sha256(canonical_sql)[:16]`` —— 结构相同即同指纹；
   日期参数从 ``'2026-11-11'`` 改成 ``'2026-11-12'`` 只改变参数值，不改变指纹，
   因此「调整日期参数后被拆成不同查询」的问题被消除。
3. 同一次执行的参数值按出现顺序收集为 ``param_values``，其指纹 ``param_fingerprint``
   用于识别「重复投递」：同窗口 + 同模板 + 同参数值 = 同一份计费工作。
4. sqlglot 解析失败时走正则兜底（注释/空白归一 + 字面量替换），
   兜底模板以 ``raw:`` 前缀标识，绝不抛异常、绝不静默丢日志。

纯函数模块，不依赖数据库，可被离线脚本与单元测试直接调用。
"""
from __future__ import annotations

import hashlib
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

PLACEHOLDER = "?"

# 字面量节点类型：参数值的差异不应改变模板结构
_LITERAL_TYPES = (
    exp.Literal,       # String / Number / NumericString
    exp.Boolean,
    exp.Null,
)

# --- 正则兜底（仅在 sqlglot 解析失败时使用） ---
_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_WS_RE = re.compile(r"\s+")
# 单引号字符串（含转义的 ''），数字（含小数/负号/科学计数法），布尔/NULL 关键字
_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_KEYWORD_RE = re.compile(r"(?<![A-Za-z0-9_])(?:true|false|null)(?![A-Za-z0-9_])", re.IGNORECASE)


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _canonical_spaces(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _replace_literals(tree: exp.Expression) -> tuple[exp.Expression, list[str]]:
    """自底向上把字面量替换成占位符，同时按出现顺序收集参数值（去重保留顺序）。"""
    values: list[str] = []

    def _rewrite(node: exp.Expression):
        if isinstance(node, _LITERAL_TYPES):
            values.append(node.sql())
            return exp.Placeholder()
        return node

    rewritten = tree.transform(_rewrite, copy=True)
    seen: set[str] = set()
    ordered = [v for v in values if not (v in seen or seen.add(v))]
    return rewritten, ordered


def normalize_sql(sql: str) -> dict:
    """把一条 SQL 归一化为模板。

    返回 dict：
        canonical_sql   占位符化后的模板 SQL（规范化空白）
        fingerprint     模板指纹（结构身份，跨参数值稳定）
        param_values    本次执行的参数值（按出现顺序、去重）
        param_fingerprint 参数值指纹（同模板下识别重复投递）
        normalized      sqlglot 是否解析成功（False = 正则兜底）
    """
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
        if tree is None:
            raise ParseError("empty statement")
        rewritten, params = _replace_literals(tree)
        # 重新生成 SQL：占位符化后由 sqlglot 统一关键字大小写/空白，再做空白规范化
        canonical = _canonical_spaces(rewritten.sql(dialect="postgres"))
        normalized = True
    except Exception:
        canonical, params = _fallback_normalize(sql)
        normalized = False

    return {
        "canonical_sql": canonical,
        "fingerprint": _stable_hash(canonical),
        "param_values": params,
        "param_fingerprint": _stable_hash("|".join(params)),
        "normalized": normalized,
    }


def _fallback_normalize(sql: str) -> tuple[str, list[str]]:
    """解析失败时的确定性兜底：去注释 → 收集/替换字面量 → 压缩空白。"""
    text = _COMMENT_RE.sub(" ", sql)
    params: list[str] = []

    def _take(match: re.Match) -> str:
        params.append(match.group(0))
        return PLACEHOLDER

    text = _STRING_RE.sub(_take, text)
    text = _NUMBER_RE.sub(_take, text)
    text = _KEYWORD_RE.sub(_take, text)

    seen: set[str] = set()
    ordered = [v for v in params if not (v in seen or seen.add(v))]
    return _canonical_spaces(text), ordered


def template_code(fingerprint: str) -> str:
    """对外展示的模板编号，例：TPL-a1b2c3d4e5f60718。"""
    return f"TPL-{fingerprint}"


def hour_window(ts: str) -> str:
    """把 ISO 时间戳归桶到小时窗口，返回 ``YYYY-MM-DD HH:00``（与分钟/秒无关）。"""
    # 容忍 'YYYY-MM-DD HH:MM:SS' / 带 T / 带时区后缀
    head = ts.replace("T", " ").strip()
    date_part, _, time_part = head.partition(" ")
    hour = (time_part or "00:00:00").split("+")[0].split("Z")[0].split(":")[0] or "00"
    return f"{date_part} {int(hour):02d}:00"
