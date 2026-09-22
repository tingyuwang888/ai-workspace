#!/usr/bin/env python3
"""
天策策略测试结果 DB 验证脚本

数据库配置读取优先级（从高到低）：
  1. 命令行参数: --host --port --user --password --database
  2. 环境变量: TIANCE_DB_HOST / TIANCE_DB_PORT / TIANCE_DB_USER / TIANCE_DB_PASS / TIANCE_DB_NAME
  3. 配置文件: config.json（位于 skill 根目录）

用法:
  # 使用配置文件（默认，推荐）
  python3 verify_result.py --last 5

  # 使用环境变量覆盖
  TIANCE_DB_HOST=db.example.invalid python3 verify_result.py --last 5

  # 使用命令行参数覆盖
  python3 verify_result.py --host <HOST> --user <USER> --password <PASS> --database <DB> --last 5

  python3 verify_result.py --uuid "19d159554d7647a2afef6b363d08eb18"

  python3 verify_result.py --policy-code "DF_PRE_CONC_001" --since "2026-06-06 00:00:00"

输出: JSON 格式的测试结果列表
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import pymysql
except ImportError:
    print("需要安装 pymysql: pip install pymysql", file=sys.stderr)
    sys.exit(1)

# 配置文件路径：skill 根目录/config.json
_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config.json'


def _load_config_file():
    """从 config.json 加载 DB 配置，返回 dict 或 None"""
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f).get('db', {})
        except Exception:
            pass
    return {}


def _resolve_env(value):
    """解析 $ENV:VAR_NAME 占位符，从环境变量读取实际值"""
    if isinstance(value, str) and value.startswith('$ENV:'):
        env_key = value[5:]
        env_val = os.environ.get(env_key)
        if env_val is None:
            print(
                f"config.json 中密码配置为 '{value}'，"
                f"但环境变量 {env_key} 未设置。\n"
                f"请设置: export {env_key}=<你的密码>",
                file=sys.stderr,
            )
            return None
        return env_val
    return value


def get_db_config(args):
    """从 config.json → 环境变量 → 命令行参数 获取数据库配置（优先级递增）"""
    file_cfg = _load_config_file()

    def resolve(cli_val, env_key, file_key, default=None):
        # 先解析 config.json 中的 $ENV: 占位符
        file_val = _resolve_env(file_cfg.get(file_key))
        return cli_val or os.environ.get(env_key) or file_val or default

    host = resolve(args.host, 'TIANCE_DB_HOST', 'host')
    port = resolve(args.port, 'TIANCE_DB_PORT', 'port')
    user = resolve(args.user, 'TIANCE_DB_USER', 'user')
    password = resolve(args.password, 'TIANCE_DB_PASS', 'password')
    database = resolve(args.database, 'TIANCE_DB_NAME', 'database')

    if not all([host, user, password, database]):
        missing = []
        if not host: missing.append('host')
        if not user: missing.append('user')
        if not password: missing.append('password')
        if not database: missing.append('database')
        print(
            f"数据库配置不完整，缺少: {', '.join(missing)}\n"
            f"请通过以下方式之一提供:\n"
            f"  1. 配置文件: {_CONFIG_PATH}\n"
            f"  2. 环境变量: TIANCE_DB_HOST / TIANCE_DB_USER / TIANCE_DB_PASS / TIANCE_DB_NAME\n"
            f"  3. 命令行参数: --host --user --password --database",
            file=sys.stderr
        )
        sys.exit(1)

    return {
        'host': host,
        'port': int(port) if port else 3306,
        'user': user,
        'password': password,
        'database': database,
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor,
    }


def connect(config):
    return pymysql.connect(**config)


def query_latest(conn, n=5):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, uuid, token, gmt_create, policy_code,
                      policy_name, policy_deal_type_name, run_status,
                      org_code, expected_result
               FROM tiangong_policy_test
               ORDER BY id DESC LIMIT %s""",
            (n,),
        )
        return cur.fetchall()


def query_by_uuid(conn, uuid):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, uuid, token, gmt_create, policy_code,
                      policy_name, policy_deal_type_name, run_status,
                      test_details, org_code, expected_result
               FROM tiangong_policy_test WHERE uuid = %s""",
            (uuid,),
        )
        return cur.fetchone()


def query_by_policy_code(conn, code, since=None):
    sql = """SELECT id, uuid, token, gmt_create, policy_code,
                    policy_deal_type_name, run_status, org_code
             FROM tiangong_policy_test WHERE policy_code = %s"""
    params = [code]
    if since:
        sql += " AND gmt_create >= %s"
        params.append(since)
    sql += " ORDER BY id DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_details(conn, record_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT test_details FROM tiangong_policy_test WHERE id = %s",
            (record_id,),
        )
        row = cur.fetchone()
        if row and row["test_details"]:
            return json.loads(row["test_details"])
        return None


def format_result(row):
    """格式化单条测试结果为可读输出"""
    status_map = {"2": "完成", "-2": "失败", "1": "运行中", "0": "待运行"}
    run_status = str(row.get("run_status", ""))
    status_text = status_map.get(run_status, run_status)
    deal_type = row.get("policy_deal_type_name") or "(无结果)"

    lines = [
        f"  ID:       {row['id']}",
        f"  UUID:     {row['uuid']}",
        f"  Token:    {row.get('token', 'N/A')}",
        f"  策略:     {row.get('policy_code', 'N/A')}",
        f"  结果:     {deal_type}",
        f"  状态:     {status_text}",
        f"  时间:     {row.get('gmt_create', 'N/A')}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="天策策略测试结果验证")
    parser.add_argument("--host", help="MySQL 主机（或设 TIANCE_DB_HOST）")
    parser.add_argument("--port", type=int, default=0, help="MySQL 端口（或设 TIANCE_DB_PORT）")
    parser.add_argument("--user", help="数据库用户（或设 TIANCE_DB_USER）")
    parser.add_argument("--password", help="数据库密码（或设 TIANCE_DB_PASS）")
    parser.add_argument("--database", help="数据库名（或设 TIANCE_DB_NAME）")
    parser.add_argument("--last", type=int, default=0, help="查看最近 N 条")
    parser.add_argument("--uuid", help="按 UUID 查询")
    parser.add_argument("--policy-code", help="按策略编码查询")
    parser.add_argument("--since", help="起始时间 (配合 --policy-code)")
    parser.add_argument("--details", type=int, default=0, help="查看指定 ID 的测试详情")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    args = parser.parse_args()
    config = get_db_config(args)
    conn = connect(config)

    try:
        if args.details:
            details = query_details(conn, args.details)
            if details:
                print(json.dumps(details, ensure_ascii=False, indent=2))
            else:
                print(f"ID {args.details} 无测试详情")
            return

        if args.uuid:
            row = query_by_uuid(conn, args.uuid)
            if not row:
                print(f"未找到 UUID={args.uuid} 的记录")
                sys.exit(1)
            if args.json:
                print(json.dumps(row, default=str, ensure_ascii=False, indent=2))
            else:
                print(format_result(row))
            return

        if args.policy_code:
            rows = query_by_policy_code(conn, args.policy_code, args.since)
        elif args.last:
            rows = query_latest(conn, args.last)
        else:
            rows = query_latest(conn, 5)

        if not rows:
            print("未找到测试记录")
            sys.exit(1)

        if args.json:
            print(json.dumps(rows, default=str, ensure_ascii=False, indent=2))
        else:
            print(f"共 {len(rows)} 条记录:\n")
            for row in rows:
                print(format_result(row))
                print()

    finally:
        conn.close()


if __name__ == "__main__":
    main()
