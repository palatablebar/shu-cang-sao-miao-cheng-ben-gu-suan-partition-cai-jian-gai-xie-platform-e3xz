"""澜图零售数仓演示数据集（纯数据 + 确定性生成，不依赖数据库/SQLAlchemy）。

同一个模块被 ``scripts/seed_demo.py``（写库）和离线校验脚本（只读）共同使用，
因此这里的每一个字节数都是可复现的：分区字节、列字节都由固定权重归一化得到。

规模契约（batch-plan gb-570）：
    tables=6  partitions=90  queries=60（其中 18 条裁剪失效）  estimates=2  suggestions=12  users=3
"""
from __future__ import annotations

from datetime import date, timedelta

GIB = 1024 ** 3

END_DATE = date(2026, 11, 12)
BRAND = "partfit"
SCHEMA = "lantu_ads"
CUSTOMER = "澜图零售 · 数据平台组"

# ---------------------------------------------------------------------------
# 1. 表 / 列 / 分区
# ---------------------------------------------------------------------------
# (列名, 类型, 字节权重, 备注) —— 权重归一化到表总字节；分区键权重固定 0（只存在路径里）
TABLES: list[dict] = [
    {
        "table_name": "ods_order_raw",
        "layer": "ODS",
        "partitions": 20,
        "total_gib": 6.2,
        "owner": "刘岚 · 采集组",
        "description": "订单中心 binlog 落仓原始表，按 dt 日分区，含退款回写与渠道标记。",
        "partition_formula": 41,
        "columns": [
            ("dt", "string", 0, "分区键 YYYY-MM-DD"),
            ("order_id", "string", 96, "订单号"),
            ("user_id", "string", 58, "会员 ID"),
            ("shop_id", "string", 44, "店铺 ID"),
            ("sku_id", "string", 52, "商品 SKU"),
            ("item_count", "int", 18, "商品件数"),
            ("amount", "decimal", 44, "订单金额"),
            ("discount_amount", "decimal", 26, "优惠金额"),
            ("pay_amount", "decimal", 44, "实付金额"),
            ("order_status", "string", 18, "订单状态"),
            ("channel", "string", 22, "渠道"),
            ("province", "string", 20, "省份"),
            ("city", "string", 26, "城市"),
            ("promo_id", "string", 24, "活动 ID"),
            ("coupon_id", "string", 26, "优惠券 ID"),
            ("create_time", "string", 46, "创建时间"),
            ("update_time", "string", 46, "更新时间"),
            ("raw_ext", "string", 250, "上游扩展 JSON"),
        ],
        "suggested": ["order_id", "user_id", "shop_id", "amount", "pay_amount", "channel", "create_time"],
    },
    {
        "table_name": "dwd_order_detail",
        "layer": "DWD",
        "partitions": 30,
        "total_gib": 12.4,
        "owner": "陈肃 · 数据开发",
        "description": "订单明细事实表（DWD 核心大表），日分区 + 22 列，remark_text 为只读备注大字段。",
        "partition_formula": 37,
        "columns": [
            ("dt", "string", 0, "分区键 YYYY-MM-DD"),
            ("order_id", "string", 90, "订单号"),
            ("buyer_id", "string", 55, "买家 ID"),
            ("shop_id", "string", 45, "店铺 ID"),
            ("sku_id", "string", 50, "商品 SKU"),
            ("brand_id", "string", 30, "品牌 ID"),
            ("cate_id", "string", 25, "类目 ID"),
            ("qty", "int", 20, "件数"),
            ("unit_price", "decimal", 40, "单价"),
            ("gmv", "decimal", 45, "成交金额"),
            ("discount", "decimal", 25, "优惠金额"),
            ("pay_amount", "decimal", 45, "实付金额"),
            ("order_status", "string", 18, "订单状态"),
            ("channel", "string", 20, "渠道"),
            ("province", "string", 20, "省份"),
            ("city", "string", 28, "城市"),
            ("coupon_code", "string", 30, "券码"),
            ("promotion_id", "string", 25, "活动 ID"),
            ("create_time", "string", 45, "下单时间"),
            ("pay_time", "string", 45, "支付时间"),
            ("refund_flag", "int", 8, "退款标记"),
            ("is_new_buyer", "int", 10, "新客标记"),
            ("remark_text", "string", 281, "客服备注大字段（极少被查询）"),
        ],
        "suggested": [
            "order_id",
            "buyer_id",
            "shop_id",
            "gmv",
            "pay_amount",
            "order_status",
            "channel",
            "create_time",
        ],
    },
    {
        "table_name": "dwd_payment_flow",
        "layer": "DWD",
        "partitions": 12,
        "total_gib": 3.6,
        "owner": "陈肃 · 数据开发",
        "description": "支付流水事实表，12 个日分区，含支付渠道与清分状态。",
        "partition_formula": 53,
        "columns": [
            ("dt", "string", 0, "分区键 YYYY-MM-DD"),
            ("pay_id", "string", 120, "支付流水号"),
            ("order_id", "string", 110, "订单号"),
            ("buyer_id", "string", 62, "买家 ID"),
            ("pay_channel", "string", 26, "支付渠道"),
            ("pay_amount", "decimal", 60, "支付金额"),
            ("fee_amount", "decimal", 34, "手续费"),
            ("clear_status", "string", 20, "清分状态"),
            ("bank_code", "string", 22, "银行编码"),
            ("pay_time", "string", 48, "支付时间"),
            ("settle_date", "string", 26, "结算日"),
            ("trace_id", "string", 90, "链路追踪 ID"),
            ("ext_json", "string", 376, "支付扩展字段"),
        ],
        "suggested": ["pay_id", "order_id", "buyer_id", "pay_channel", "pay_amount", "pay_time"],
    },
    {
        "table_name": "dws_trade_summary",
        "layer": "DWS",
        "partitions": 10,
        "total_gib": 2.1,
        "owner": "赵仪 · 数仓建模",
        "description": "交易汇总宽表（店铺 × 渠道 × 日），10 个日分区。",
        "partition_formula": 29,
        "columns": [
            ("dt", "string", 0, "分区键 YYYY-MM-DD"),
            ("shop_id", "string", 150, "店铺 ID"),
            ("channel", "string", 90, "渠道"),
            ("order_cnt", "bigint", 60, "订单数"),
            ("buyer_cnt", "bigint", 60, "买家数"),
            ("gmv", "decimal", 120, "成交额"),
            ("pay_amount", "decimal", 120, "实付额"),
            ("refund_amount", "decimal", 90, "退款额"),
            ("avg_order_value", "decimal", 70, "客单价"),
            ("new_buyer_cnt", "bigint", 60, "新客数"),
            ("update_time", "string", 80, "更新时间"),
        ],
        "suggested": ["shop_id", "channel", "gmv", "pay_amount", "order_cnt"],
    },
    {
        "table_name": "ads_sales_daily",
        "layer": "ADS",
        "partitions": 10,
        "total_gib": 0.85,
        "owner": "赵仪 · 数仓建模",
        "description": "销售日报 ADS 表，BI 直连，10 个日分区。",
        "partition_formula": 61,
        "columns": [
            ("dt", "string", 0, "分区键 YYYY-MM-DD"),
            ("shop_id", "string", 200, "店铺 ID"),
            ("cate_name", "string", 150, "类目"),
            ("sale_amount", "decimal", 180, "销售额"),
            ("sale_qty", "bigint", 90, "销量"),
            ("refund_amount", "decimal", 110, "退款额"),
            ("top_sku", "string", 150, "Top SKU"),
            ("etl_version", "string", 120, "ETL 版本"),
        ],
        "suggested": ["shop_id", "cate_name", "sale_amount", "sale_qty"],
    },
    {
        "table_name": "ads_member_value",
        "layer": "ADS",
        "partitions": 8,
        "total_gib": 0.62,
        "owner": "赵仪 · 数仓建模",
        "description": "会员价值分层 ADS 表（RFM 分档），8 个日分区。",
        "partition_formula": 17,
        "columns": [
            ("dt", "string", 0, "分区键 YYYY-MM-DD"),
            ("member_id", "string", 240, "会员 ID"),
            ("value_tier", "string", 110, "价值分层"),
            ("last_order_dt", "string", 130, "最近下单日"),
            ("gmv_90d", "decimal", 170, "90 天 GMV"),
            ("order_cnt_90d", "bigint", 90, "90 天订单数"),
            ("churn_score", "decimal", 130, "流失分"),
            ("tag_json", "string", 130, "标签 JSON"),
        ],
        "suggested": ["member_id", "value_tier", "gmv_90d", "churn_score"],
    },
]


def partition_dates(count: int) -> list[str]:
    """Oldest → newest, ending at END_DATE."""
    start = END_DATE - timedelta(days=count - 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(count)]


def _normalize(weights: list[int], total: int) -> list[int]:
    weight_sum = sum(weights) or 1
    values = [int(total * w / weight_sum) for w in weights]
    values[-1] += total - sum(values)
    return values


def build_tables() -> list[dict]:
    """Materialize the 6 tables with exact partition/column byte splits."""
    result: list[dict] = []
    for spec in TABLES:
        total_bytes = int(round(spec["total_gib"] * GIB))
        dates = partition_dates(spec["partitions"])
        raw_weights = [
            84 + ((i * spec["partition_formula"] + 13) % 41) for i in range(len(dates))
        ]
        sizes = _normalize(raw_weights, total_bytes)

        column_weights = [c[2] for c in spec["columns"]]
        column_bytes = _normalize(column_weights, total_bytes)
        # 分区键只存在于目录路径中，不占文件字节
        pk_index = next((i for i, c in enumerate(spec["columns"]) if c[0] == "dt"), None)
        if pk_index is not None:
            column_bytes[pk_index] = 0
            column_bytes[-1] += total_bytes - sum(column_bytes)

        columns = []
        for ordinal, ((name, data_type, _weight, note), nbytes) in enumerate(
            zip(spec["columns"], column_bytes)
        ):
            columns.append(
                {
                    "name": name,
                    "data_type": data_type,
                    "bytes": nbytes,
                    "byte_ratio": round(nbytes / total_bytes, 6),
                    "ordinal": ordinal,
                    "is_partition_key": name == "dt",
                    "note": note,
                }
            )

        partitions = []
        for index, (dt, nbytes) in enumerate(zip(dates, sizes)):
            partitions.append(
                {
                    "dt": dt,
                    "bytes": nbytes,
                    "row_count": int(nbytes / (3.1 * GIB / 1_000_000)) or 1,
                    "file_count": 48 + (index * 7) % 37,
                    "is_current": index == len(dates) - 1,
                }
            )

        result.append(
            {
                "schema_name": SCHEMA,
                "table_name": spec["table_name"],
                "layer": spec["layer"],
                "storage_format": "parquet",
                "partition_key": "dt",
                "partition_type": "date_str",
                "partition_count": len(partitions),
                "row_count": sum(p["row_count"] for p in partitions),
                "total_bytes": sum(p["bytes"] for p in partitions),
                "data_column_count": len([c for c in columns if not c["is_partition_key"]]),
                "owner": spec["owner"],
                "description": spec["description"],
                "suggested_columns": spec["suggested"],
                "last_analyzed_dt": END_DATE.isoformat(),
                "columns": columns,
                "partitions": partitions,
            }
        )
    return result


# ---------------------------------------------------------------------------
# 2. 查询日志（60 条，其中 18 条裁剪失效）
# ---------------------------------------------------------------------------
USERS = [
    {
        "email": "admin@partfit.io",
        "display_name": "沈知远 · 平台负责人",
        "role": "admin",
        "team": "澜图零售 · 数据平台组",
    },
    {
        "email": "engineer@partfit.io",
        "display_name": "陈肃 · 数据开发",
        "role": "engineer",
        "team": "澜图零售 · 数据平台组",
    },
    {
        "email": "viewer@partfit.io",
        "display_name": "周娅 · 财务 BP",
        "role": "viewer",
        "team": "澜图零售 · 财务共享中心",
    },
]

PASSWORD = "Demo@2026"

ENGINEER = USERS[1]["display_name"]
ADMIN = USERS[0]["display_name"]
VIEWER = USERS[2]["display_name"]

SOURCES = ["finebi", "adhoc", "superset", "调度-SQL 节点", "metabase"]


def _pick(dates: list[str], index: int) -> str:
    return dates[index % len(dates)]


def build_queries(tables: list[dict] | None = None) -> list[dict]:
    """Deterministic 60-row query log: 18 blocked (10 wrapped / 8 implicit cast... ) + 42 prunable.

    裁剪失效构成（与 batch-plan 对齐）：
        6 条 分区列函数包裹、8 条 隐式类型转换、4 条 缺分区谓词 = 18 条
    其中 QL-0007（dwd_order_detail + to_char 包裹 + SELECT *）是全量扫描 Top1。
    """
    table_map = {t["table_name"]: t for t in (tables or build_tables())}
    dates = {name: [p["dt"] for p in t["partitions"]] for name, t in table_map.items()}
    rows: list[dict] = []

    def add(
        table: str,
        title: str,
        sql: str,
        source: str,
        submitted_by: str,
        day_index: int,
        duration_ms: int,
        scheduled: bool = False,
    ) -> None:
        rows.append(
            {
                "external_id": f"QL-{len(rows) + 1:04d}",
                "title": title,
                "sql_text": sql,
                "source": source,
                "submitted_by": submitted_by,
                "query_date": END_DATE.isoformat(),
                "duration_ms": duration_ms,
                "is_scheduled": scheduled,
                "table_name": table,
                "day_index": day_index,
            }
        )

    dd = "dwd_order_detail"
    ods = "ods_order_raw"
    pay = "dwd_payment_flow"
    dws = "dws_trade_summary"
    sales = "ads_sales_daily"
    member = "ads_member_value"

    # --- 1. Top1：分区列函数包裹 + SELECT *（dwd_order_detail 全量扫描） ---
    add(
        dd,
        "双 11 成交明细全量导出（运营临时取数）",
        f"SELECT * FROM dwd_order_detail WHERE to_char(dt, 'YYYY-MM-DD') = '{_pick(dates[dd], 29)}'",
        "adhoc",
        ENGINEER,
        29,
        486_000,
    )
    add(
        dd,
        "退款率按渠道口径复核",
        f"SELECT channel, count(*) AS cnt, sum(refund_flag) AS refund_cnt\n"
        f"FROM dwd_order_detail\nWHERE date(dt) = '{_pick(dates[dd], 27)}' AND order_status = 'PAID'\n"
        f"GROUP BY channel",
        "finebi",
        ENGINEER,
        27,
        189_000,
    )
    add(
        ods,
        "订单原始表状态分布（周报）",
        f"SELECT order_status, count(*) AS cnt FROM ods_order_raw\n"
        f"WHERE substr(dt, 1, 7) = '{_pick(dates[ods], 18)[:7]}'\nGROUP BY order_status",
        "superset",
        ENGINEER,
        18,
        152_000,
    )
    add(
        ods,
        "渠道 GMV 对账（小时级刷新）",
        f"SELECT channel, sum(pay_amount) AS gmv FROM ods_order_raw\n"
        f"WHERE to_char(dt, 'YYYY-MM-DD') = '{_pick(dates[ods], 19)}'\nGROUP BY channel",
        "调度-SQL 节点",
        ENGINEER,
        19,
        98_000,
        scheduled=True,
    )
    add(
        pay,
        "支付流水清分状态巡检",
        f"SELECT clear_status, count(*) AS cnt FROM dwd_payment_flow\n"
        f"WHERE dt::date = '{_pick(dates[pay], 11)}'\nGROUP BY clear_status",
        "metabase",
        ENGINEER,
        11,
        76_000,
    )
    add(
        dws,
        "店铺日报刷新前的行数校验",
        f"SELECT shop_id, order_cnt FROM dws_trade_summary\n"
        f"WHERE trunc(dt) = '{_pick(dates[dws], 9)}' LIMIT 500",
        "调度-SQL 节点",
        ENGINEER,
        9,
        41_000,
        scheduled=True,
    )

    # --- 2. 隐式类型转换（8 条） ---
    add(
        dd,
        "订单量按日核对（整型日期写法）",
        f"SELECT count(*) AS cnt FROM dwd_order_detail WHERE dt = {_pick(dates[dd], 21).replace('-', '')}",
        "adhoc",
        ENGINEER,
        21,
        210_000,
    )
    add(
        dd,
        "近一周成交额趋势（整型区间）",
        f"SELECT dt, sum(pay_amount) AS gmv FROM dwd_order_detail\n"
        f"WHERE dt >= {_pick(dates[dd], 26).replace('-', '')} AND dt <= {_pick(dates[dd], 29).replace('-', '')}\n"
        f"GROUP BY dt ORDER BY dt",
        "finebi",
        ENGINEER,
        26,
        324_000,
    )
    add(
        ods,
        "新客首单占比（整型日期）",
        f"SELECT dt, count(*) AS cnt FROM ods_order_raw WHERE dt = {_pick(dates[ods], 16).replace('-', '')}"
        f" AND promo_id IS NOT NULL\nGROUP BY dt",
        "superset",
        ENGINEER,
        16,
        143_000,
    )
    add(
        ods,
        "订单更新时间漂移监控",
        f"SELECT count(*) AS cnt FROM ods_order_raw WHERE dt >= {_pick(dates[ods], 12).replace('-', '')}",
        "metabase",
        ADMIN,
        12,
        96_000,
    )
    add(
        pay,
        "支付手续费按渠道汇总",
        f"SELECT pay_channel, sum(fee_amount) AS fee FROM dwd_payment_flow\n"
        f"WHERE dt = {_pick(dates[pay], 9).replace('-', '')}\nGROUP BY pay_channel",
        "finebi",
        ENGINEER,
        9,
        88_000,
    )
    add(
        pay,
        "大额支付明细抽查",
        f"SELECT pay_id, order_id, pay_amount FROM dwd_payment_flow\n"
        f"WHERE dt BETWEEN {_pick(dates[pay], 4).replace('-', '')} AND {_pick(dates[pay], 8).replace('-', '')}\n"
        f"  AND pay_amount > 5000",
        "adhoc",
        ENGINEER,
        8,
        132_000,
    )
    add(
        sales,
        "类目销售额日报（整型日期）",
        f"SELECT cate_name, sum(sale_amount) AS amount FROM ads_sales_daily\n"
        f"WHERE dt = {_pick(dates[sales], 7).replace('-', '')}\nGROUP BY cate_name ORDER BY amount DESC",
        "superset",
        ENGINEER,
        7,
        36_000,
    )
    add(
        member,
        "会员分层人数日核对（整型日期）",
        f"SELECT value_tier, count(*) AS cnt FROM ads_member_value\n"
        f"WHERE dt = {_pick(dates[member], 5).replace('-', '')}\nGROUP BY value_tier",
        "finebi",
        VIEWER,
        5,
        22_000,
    )

    # --- 3. 缺分区谓词（4 条） ---
    add(
        dd,
        "全量订单明细拉取给算法组（疑似漏写 dt）",
        "SELECT order_id, buyer_id, gmv, create_time FROM dwd_order_detail WHERE order_status = 'PAID' LIMIT 10000",
        "adhoc",
        ENGINEER,
        0,
        612_000,
    )
    add(
        ods,
        "历史订单找回（漏写 dt）",
        "SELECT order_id, user_id, pay_amount FROM ods_order_raw WHERE order_id LIKE 'LT2026%' LIMIT 2000",
        "adhoc",
        ENGINEER,
        0,
        388_000,
    )
    add(
        pay,
        "支付流水全量导出核对清分",
        "SELECT pay_id, clear_status, settle_date FROM dwd_payment_flow WHERE clear_status <> 'CLEARED' LIMIT 5000",
        "metabase",
        ENGINEER,
        0,
        274_000,
    )
    add(
        dws,
        "店铺宽表全量快照",
        "SELECT shop_id, gmv, refund_amount FROM dws_trade_summary WHERE refund_amount > 0 LIMIT 1000",
        "superset",
        VIEWER,
        0,
        118_000,
    )

    column_sets = {
        dd: ["order_id", "buyer_id", "shop_id", "gmv", "pay_amount", "order_status", "channel", "create_time"],
        ods: ["order_id", "user_id", "shop_id", "amount", "pay_amount", "channel"],
        pay: ["pay_id", "order_id", "pay_channel", "pay_amount", "pay_time"],
        dws: ["shop_id", "channel", "gmv", "pay_amount", "order_cnt"],
        sales: ["shop_id", "cate_name", "sale_amount", "sale_qty"],
        member: ["member_id", "value_tier", "gmv_90d", "churn_score"],
    }

    # --- 4. 42 条裸列谓词（可裁剪） ---
    plan = [
        (dd, 13),
        (ods, 7),
        (pay, 6),
        (dws, 6),
        (sales, 6),
        (member, 4),
    ]
    titles = {
        dd: [
            "当日成交明细按店铺下钻",
            "近三日退款订单排查",
            "品牌成交排行",
            "类目环比取数",
            "店铺订单状态分布",
            "新客成交明细",
        ],
        ods: ["订单增量同步核对", "渠道订单量对比", "活动订单明细", "省份订单分布"],
        pay: ["支付渠道流水对账", "结算日清分核对", "大额支付明细"],
        dws: ["店铺宽表查询", "渠道汇总趋势", "退款额异常排查"],
        sales: ["日报类目下钻", "店铺销售额快照"],
        member: ["会员价值分层查询", "流失分高客群明细"],
    }
    columns_sql = {
        dd: "order_id, buyer_id, shop_id, gmv, pay_amount, order_status, create_time",
        ods: "order_id, user_id, channel, pay_amount",
        pay: "pay_id, order_id, pay_channel, pay_amount",
        dws: "shop_id, channel, gmv, pay_amount",
        sales: "shop_id, cate_name, sale_amount",
        member: "member_id, value_tier, gmv_90d",
    }

    for table_name, count in plan:
        date_list = dates[table_name]
        for offset in range(count):
            index = len(date_list) - 1 - (offset % max(1, len(date_list) - 1))
            stamp = _pick(date_list, index)
            source = SOURCES[offset % len(SOURCES)]
            title_list = titles[table_name]
            title = title_list[offset % len(title_list)]
            mode = offset % 5
            if mode == 0:
                sql = (
                    f"SELECT {columns_sql[table_name]} FROM {table_name}\n"
                    f"WHERE dt = '{stamp}'"
                )
            elif mode == 1:
                start = _pick(date_list, max(0, index - 2))
                sql = (
                    f"SELECT {columns_sql[table_name]} FROM {table_name}\n"
                    f"WHERE dt BETWEEN '{start}' AND '{stamp}'"
                )
            elif mode == 2:
                sql = (
                    f"SELECT {columns_sql[table_name]} FROM {table_name}\n"
                    f"WHERE dt IN ('{stamp}', '{_pick(date_list, max(0, index - 1))}')"
                )
            elif mode == 3:
                start = _pick(date_list, max(0, index - 6))
                sql = (
                    f"SELECT {columns_sql[table_name]} FROM {table_name}\n"
                    f"WHERE dt >= '{start}' AND dt < '{stamp}'"
                )
            else:
                sql = (
                    f"SELECT count(*) AS cnt, {column_sets[table_name][0]} FROM {table_name}\n"
                    f"WHERE dt = '{stamp}'"
                )
            add(
                table_name,
                title,
                sql,
                source,
                ENGINEER if offset % 3 else ADMIN,
                index,
                12_000 + offset * 3_100,
                scheduled=(offset % 7 == 0),
            )

    return rows


# ---------------------------------------------------------------------------
# 2b. 执行流水（模板账本数据源）
# ---------------------------------------------------------------------------
# 演示日 = END_DATE（2026-11-12）。执行按小时窗归桶，覆盖：
#   ① 同一模板每小时跑多次（调度小时级刷新）② 调整日期参数 → 同指纹不同参数
#   ③ 重复投递（同窗口同模板同参数，只计一次费）④ 跨窗口不串账
#   ⑤ 失败执行（engine 报错 / 解析失败，单列且计入覆盖率）
EXECUTION_DAY = END_DATE.isoformat()
# 失败态样本：engine 执行失败（SQL 本身可解析，但跑挂了，不计扫描量）
FAILED_RUN_SQL = (
    "SELECT order_id, buyer_id, gmv, pay_amount FROM dwd_order_detail\n"
    "WHERE dt = '2026-11-12' AND order_status = 'PAID'"
)
# 解析失败 / 缺表样本：算法 1 无法估算（unparsed / missing_table）
UNPARSED_RUN_SQL = "SELECT FROM FROM dwd_order_detail WHERE dt = '2026-11-12'"
MISSING_TABLE_RUN_SQL = "SELECT id FROM lantu_tmp.tmp_offline_export_20261112 WHERE dt = '2026-11-12'"

FAILED_RUN_ERROR = "engine error: partition column file missing (FileNotFound 404)"
UNPARSED_RUN_ERROR = "sqlglot 解析失败：mismatched input 'FROM'"
MISSING_TABLE_RUN_ERROR = "目标表 tmp_offline_export_20261112 不在元数据目录中"


def _ts(hour: int, minute: int, second: int = 0) -> str:
    return f"{EXECUTION_DAY} {hour:02d}:{minute:02d}:{second:02d}"


def build_executions(queries: list[dict] | None = None) -> list[dict]:
    """确定性生成执行流水（纯数据，不依赖数据库/模板归一化）。

    每条事件字段：
        event_no      自然键 EX-####（幂等 seed 用）
        query_index   对应 build_queries() 的行序号（0-based）；失败样本为 -1/-2/-3
        sql_text      实际执行的 SQL（失败样本独立提供）
        executed_at   执行时间戳
        run_status    success / failed
        error_message 失败原因（成功为 None）
        duration_ms   本次耗时
        duplicate     是否重复投递（同窗口同模板同参数，不计费）
    模板指纹 / 窗口 / 计费判定在 seed 阶段由 analysis.template + 服务层统一计算，
    本函数只负责给出真实世界会发生的「执行事件」。
    """
    queries = queries if queries is not None else build_queries()
    events: list[dict] = []

    def add(query_index: int, sql: str, hour: int, minute: int, *,
            status: str = "success", error: str | None = None,
            duration_ms: int | None = None, duplicate: bool = False,
            second: int = 0) -> None:
        base = queries[query_index] if 0 <= query_index < len(queries) else {}
        events.append(
            {
                "event_no": f"EX-{len(events) + 1:04d}",
                "query_index": query_index,
                "sql_text": sql,
                "title": base.get("title", "（失败执行）"),
                "source": base.get("source", "adhoc"),
                "submitted_by": base.get("submitted_by", ENGINEER),
                "is_scheduled": base.get("is_scheduled", False),
                "executed_at": _ts(hour, minute, second),
                "run_status": status,
                "error_message": error,
                "duration_ms": duration_ms if duration_ms is not None else base.get("duration_ms", 12_000),
                "duplicate": duplicate,
            }
        )

    # --- 1. 每个模板至少一次成功执行，时间窗按行号确定性分散在 08:00-18:00 ---
    for index, row in enumerate(queries):
        hour = 8 + (index * 37 % 11)          # 08..18
        minute = (index * 13) % 60
        add(index, row["sql_text"], hour, minute)

    # --- 2. 调度模板：每小时跑几次（09/10/11 三个窗口），两次运行参数不同 → 同模板都计费 ---
    #   取两条 is_scheduled 的代表：QL-0004（ods 渠道 GMV 小时刷新，index=3）
    #   与 QL-0006（dws 行数校验，index=5）
    ods_dates = _scheduled_dates("ods_order_raw")

    def _ods_gmv_sql(stamp: str) -> str:
        return (
            "SELECT channel, sum(pay_amount) AS gmv FROM ods_order_raw\n"
            f"WHERE to_char(dt, 'YYYY-MM-DD') = '{stamp}'\nGROUP BY channel"
        )

    for k, hour in enumerate((9, 10, 11)):
        idx = min(k, len(ods_dates) - 1)
        stamp = ods_dates[idx]
        # 同窗第二次取与首条不同的另一个分区；偏移 2 并环形回绕，
        # 既避开同条参数（重复投递由 Top1 显式样本演示），也避开 base run 的末分区参数
        stamp_alt = ods_dates[(idx - 2) % len(ods_dates)]
        add(3, _ods_gmv_sql(stamp), hour, 5, duration_ms=94_000 + k * 1_200, second=12)
        # 同窗第二次：换一个日期参数 → 同模板、不同参数值，仍各自计费（不是重复投递）
        add(3, _ods_gmv_sql(stamp_alt), hour, 35, duration_ms=96_000 + k * 900, second=40)

    # --- 3. 调整日期参数：同模板、不同参数值、不同窗口（验证指纹不随参数变化） ---
    for k, hour in enumerate((13, 15, 17)):
        day = 21 + k
        stamp = f"202611{day:02d}"
        sql = f"SELECT count(*) AS cnt FROM dwd_order_detail WHERE dt = {stamp}"
        add(6, sql, hour, 20, duration_ms=205_000 + k * 2_000)

    # --- 4. 重复投递：同窗口 + 同模板 + 同参数，只有首条计费 ---
    top1 = queries[0]  # QL-0001 双 11 全量导出
    add(0, top1["sql_text"], 14, 10, duration_ms=486_000)
    add(0, top1["sql_text"], 14, 10, duration_ms=481_000, duplicate=True, second=26)
    add(0, top1["sql_text"], 14, 11, duration_ms=479_000, duplicate=True, second=48)

    # --- 5. 失败执行（engine 报错）：SQL 可解析但执行失败，单列、不计费、纳入覆盖率 ---
    add(-1, FAILED_RUN_SQL, 16, 22, status="failed", error=FAILED_RUN_ERROR, duration_ms=312_000)
    add(-1, FAILED_RUN_SQL, 16, 41, status="failed", error=FAILED_RUN_ERROR,
        duration_ms=298_000, duplicate=True)
    # 解析失败 / 缺表：模板归一化走正则兜底，算法 1 失败态显式保留
    add(-2, UNPARSED_RUN_SQL, 17, 8, status="failed", error=UNPARSED_RUN_ERROR, duration_ms=4_200)
    add(-3, MISSING_TABLE_RUN_SQL, 18, 2, status="failed", error=MISSING_TABLE_RUN_ERROR, duration_ms=7_600)

    return events


def _scheduled_dates(table_name: str) -> list[str]:
    table_map = {t["table_name"]: t for t in build_tables()}
    return [p["dt"] for p in table_map[table_name]["partitions"]][-3:]


# ---------------------------------------------------------------------------
# 3. 预算策略（admin 维护）
# ---------------------------------------------------------------------------
BUDGET_POLICIES = [
    {
        "policy_no": "BP-GLOBAL",
        "name": "澜图零售数仓 · 月扫描预算（全局）",
        "scope": "global",
        "scope_value": "all",
        "monthly_budget_cny": 1800.0,
        "unit_cost_per_gib_cny": 0.30,
        "warn_ratio": 0.75,
        "critical_ratio": 0.92,
        "scan_alert_gib": 8.0,
        "is_active": True,
        "note": "全仓月账单 1.8 万元，演示子集（6 张表）按 1/10 拆为 1,800 元/月；单查询扫描 > 8 GiB 告警。",
    },
    {
        "policy_no": "BP-DWD",
        "name": "DWD 明细层 · 扫描阈值",
        "scope": "layer",
        "scope_value": "DWD",
        "monthly_budget_cny": 960.0,
        "unit_cost_per_gib_cny": 0.30,
        "warn_ratio": 0.70,
        "critical_ratio": 0.90,
        "scan_alert_gib": 6.0,
        "is_active": True,
        "note": "明细层大表集中，阈值比全局更紧。",
    },
    {
        "policy_no": "BP-ADS",
        "name": "ADS 应用层 · 扫描阈值",
        "scope": "layer",
        "scope_value": "ADS",
        "monthly_budget_cny": 240.0,
        "unit_cost_per_gib_cny": 0.30,
        "warn_ratio": 0.80,
        "critical_ratio": 0.95,
        "scan_alert_gib": 2.0,
        "is_active": True,
        "note": "ADS 表小、查询多，关注单条扫描放大。",
    },
]

# 两次 seed 估算批次（自然键 run_no 固定）
SEED_ESTIMATES = [
    {
        "run_no": "EST-20261112-01",
        "status": "completed",
        "scope": "all",
        "scope_value": "all",
        "created_by": "沈知远 · 平台负责人",
        "note": "账单复盘基线：60 条查询全量估算（未改写）",
    },
    {
        "run_no": "EST-20261112-02",
        "status": "completed",
        "scope": "table",
        "scope_value": "dwd_order_detail",
        "created_by": "陈肃 · 数据开发",
        "note": "针对 Top1 大表的专项估算（定位函数包裹反模式）",
    },
]
