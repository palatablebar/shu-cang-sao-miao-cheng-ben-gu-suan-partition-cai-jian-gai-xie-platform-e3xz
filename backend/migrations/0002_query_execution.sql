-- partfit / 模板账本（query template ledger）
-- 0002: query_execution —— 每次查询执行的计费流水，按小时窗 + 模板指纹聚合。
-- 运行时 src.config.database.init_db() 会自动 create_all；本文件供 DBA 手工预建与评审。

CREATE TABLE query_execution (
	id SERIAL NOT NULL,
	external_id VARCHAR(40) NOT NULL,
	executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	window_start VARCHAR(16) NOT NULL,
	fingerprint VARCHAR(32) NOT NULL,
	canonical_sql TEXT NOT NULL,
	param_fingerprint VARCHAR(32) NOT NULL DEFAULT '',
	param_values JSONB NOT NULL,
	sql_normalized BOOLEAN NOT NULL DEFAULT true,
	query_log_id INTEGER,
	title VARCHAR(160) NOT NULL DEFAULT '',
	source VARCHAR(48) NOT NULL DEFAULT 'adhoc',
	submitted_by VARCHAR(80) NOT NULL DEFAULT '',
	target_table VARCHAR(96),
	is_scheduled BOOLEAN NOT NULL DEFAULT false,
	run_status VARCHAR(16) NOT NULL DEFAULT 'success',
	error_message TEXT,
	duration_ms INTEGER NOT NULL DEFAULT 0,
	is_billed BOOLEAN NOT NULL DEFAULT true,
	dedupe_key VARCHAR(128) NOT NULL DEFAULT '',
	scan_bytes BIGINT NOT NULL DEFAULT 0,
	scan_cost_cny FLOAT NOT NULL DEFAULT 0.0,
	parse_status VARCHAR(24) NOT NULL DEFAULT 'parsed',
	prunable BOOLEAN NOT NULL DEFAULT false,
	blocked_reason VARCHAR(32) NOT NULL DEFAULT 'none',
	hit_partition_count INTEGER NOT NULL DEFAULT 0,
	total_partition_count INTEGER NOT NULL DEFAULT 0,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(query_log_id) REFERENCES query_log (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_query_execution_external_id ON query_execution (external_id);
CREATE INDEX ix_qe_window_fingerprint ON query_execution (window_start, fingerprint);
CREATE INDEX ix_qe_query_log_id ON query_execution (query_log_id);
CREATE INDEX ix_qe_run_status ON query_execution (run_status);
CREATE INDEX ix_query_execution_target_table ON query_execution (target_table);
