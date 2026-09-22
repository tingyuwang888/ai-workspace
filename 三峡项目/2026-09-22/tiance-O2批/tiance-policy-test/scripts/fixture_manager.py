#!/usr/bin/env python3
"""Prepare, verify, and clean isolated MySQL fixtures for policy tests."""

import argparse
import json
import os
import re
import sys
from pathlib import Path


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RUN_ID_PLACEHOLDER = "${RUN_ID}"


def _identifier(value, label):
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} 不是安全的 SQL 标识符: {value!r}")
    return value


def render_value(value, run_id):
    if isinstance(value, str):
        return value.replace(RUN_ID_PLACEHOLDER, run_id)
    return value


def validate_manifest(manifest):
    errors = []
    fixtures = manifest.get("fixtures") if isinstance(manifest, dict) else None
    absence_checks = manifest.get("absenceChecks") if isinstance(manifest, dict) else None
    if fixtures is None:
        fixtures = []
    if absence_checks is None:
        absence_checks = []
    if not isinstance(fixtures, list):
        return ["fixtures 必须是数组"]
    if not isinstance(absence_checks, list):
        return ["absenceChecks 必须是数组"]
    if not fixtures and not absence_checks:
        return ["fixtures 和 absenceChecks 不能同时为空"]
    seen_ids = set()
    for index, fixture in enumerate(fixtures, 1):
        prefix = f"fixture[{index}]"
        if not isinstance(fixture, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        fixture_id = fixture.get("id")
        if not fixture_id:
            errors.append(f"{prefix} 缺少 id")
        elif fixture_id in seen_ids:
            errors.append(f"{prefix} id 重复: {fixture_id}")
        else:
            seen_ids.add(fixture_id)
        try:
            _identifier(fixture.get("table"), f"{prefix}.table")
        except ValueError as exc:
            errors.append(str(exc))
        key_columns = fixture.get("keyColumns")
        if not isinstance(key_columns, list) or not key_columns:
            errors.append(f"{prefix}.keyColumns 必须是非空数组")
            key_columns = []
        for column in key_columns:
            try:
                _identifier(column, f"{prefix}.keyColumns")
            except ValueError as exc:
                errors.append(str(exc))
        rows = fixture.get("rows")
        if not isinstance(rows, list) or not rows:
            errors.append(f"{prefix}.rows 必须是非空数组")
            continue
        for row_index, row in enumerate(rows, 1):
            row_prefix = f"{prefix}.rows[{row_index}]"
            if not isinstance(row, dict):
                errors.append(f"{row_prefix} 必须是对象")
                continue
            for column in row:
                try:
                    _identifier(column, f"{row_prefix} 列名")
                except ValueError as exc:
                    errors.append(str(exc))
            missing_keys = [key for key in key_columns if key not in row]
            if missing_keys:
                errors.append(
                    f"{row_prefix} 缺少清理键 {', '.join(missing_keys)}"
                )
            if key_columns and not any(
                RUN_ID_PLACEHOLDER in str(row.get(key, ""))
                for key in key_columns
            ):
                errors.append(
                    f"{row_prefix} 至少一个 keyColumns 值必须包含 "
                    f"{RUN_ID_PLACEHOLDER}"
                )
    for index, check in enumerate(absence_checks, 1):
        prefix = f"absenceChecks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        try:
            _identifier(check.get("table"), f"{prefix}.table")
        except ValueError as exc:
            errors.append(str(exc))
        key_columns = check.get("keyColumns")
        row = check.get("row")
        if not isinstance(key_columns, list) or not key_columns:
            errors.append(f"{prefix}.keyColumns 必须是非空数组")
            continue
        if not isinstance(row, dict):
            errors.append(f"{prefix}.row 必须是对象")
            continue
        for column in key_columns:
            try:
                _identifier(column, f"{prefix}.keyColumns")
            except ValueError as exc:
                errors.append(str(exc))
            if column not in row:
                errors.append(f"{prefix}.row 缺少清理键 {column}")
        if not any(RUN_ID_PLACEHOLDER in str(row.get(key, "")) for key in key_columns):
            errors.append(
                f"{prefix}.row 至少一个 keyColumns 值必须包含 {RUN_ID_PLACEHOLDER}"
            )
    return errors


def render_fixture_rows(manifest, run_id):
    rendered = []
    for fixture in manifest["fixtures"]:
        rendered.append({
            "id": fixture["id"],
            "table": fixture["table"],
            "keyColumns": list(fixture["keyColumns"]),
            "rows": [
                {
                    column: render_value(value, run_id)
                    for column, value in row.items()
                }
                for row in fixture["rows"]
            ],
        })
    return rendered


def render_absence_checks(manifest, run_id):
    return [{
        "id": check.get("id", "absence_check"),
        "table": check["table"],
        "keyColumns": list(check["keyColumns"]),
        "row": {
            column: render_value(value, run_id)
            for column, value in check["row"].items()
        },
    } for check in manifest.get("absenceChecks", [])]


def build_insert(table, row):
    columns = list(row)
    quoted = ", ".join(f"`{_identifier(column, 'column')}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return (
        f"INSERT INTO `{_identifier(table, 'table')}` ({quoted}) "
        f"VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def build_key_query(table, key_columns, row, delete=False):
    where = " AND ".join(
        f"`{_identifier(column, 'key column')}` = %s"
        for column in key_columns
    )
    verb = "DELETE" if delete else "SELECT COUNT(*) AS count"
    return (
        f"{verb} FROM `{_identifier(table, 'table')}` WHERE {where}",
        tuple(row[column] for column in key_columns),
    )


def group_fixture_rows(fixture):
    """Group rows sharing the service query key for safe multi-row fixtures."""
    groups = {}
    key_columns = fixture["keyColumns"]
    for row in fixture["rows"]:
        key = tuple(row[column] for column in key_columns)
        groups.setdefault(key, []).append(row)
    return list(groups.values())


def _db_config(args):
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    file_config = {}
    if config_path.exists():
        file_config = json.loads(
            config_path.read_text(encoding="utf-8")
        ).get("db", {})

    def resolve(cli_value, env_name, key, default=None):
        if cli_value not in (None, ""):
            return cli_value
        if os.environ.get(env_name):
            return os.environ[env_name]
        value = file_config.get(key, default)
        if isinstance(value, str) and value.startswith("$ENV:"):
            env_key = value[5:]
            env_val = os.environ.get(env_key)
            if env_val is None:
                print(
                    f"config.json 中 '{key}' 配置为 '{value}'，但环境变量 {env_key} 未设置。\n"
                    f"请设置: export {env_key}=<对应值>",
                    file=sys.stderr,
                )
            return env_val
        return value

    config = {
        "host": resolve(args.host, "TIANCE_DB_HOST", "host"),
        "port": int(resolve(args.port, "TIANCE_DB_PORT", "port", 3306)),
        "user": resolve(args.user, "TIANCE_DB_USER", "user"),
        "password": resolve(args.password, "TIANCE_DB_PASS", "password"),
        "database": resolve(args.database, "TIANCE_DB_NAME", "database"),
        "charset": "utf8mb4",
    }
    missing = [key for key, value in config.items() if value in (None, "")]
    if missing:
        raise RuntimeError(f"数据库配置缺少: {', '.join(missing)}")
    return config


def _connect(args):
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("需要安装 pymysql") from exc
    return pymysql.connect(
        **_db_config(args),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def apply_fixtures(connection, fixtures):
    with connection.cursor() as cursor:
        for fixture in fixtures:
            for rows in group_fixture_rows(fixture):
                row = rows[0]
                sql, values = build_key_query(
                    fixture["table"],
                    fixture["keyColumns"],
                    row,
                )
                cursor.execute(sql, values)
                existing = cursor.fetchone()
                if existing and int(existing.get("count", 0)) > 0:
                    raise RuntimeError(
                        f"{fixture['id']}: 隔离键已存在，拒绝覆盖存量数据"
                    )
            for row in fixture["rows"]:
                sql, values = build_insert(fixture["table"], row)
                cursor.execute(sql, values)
    connection.commit()


def verify_fixtures(connection, fixtures):
    missing = []
    with connection.cursor() as cursor:
        for fixture in fixtures:
            for rows in group_fixture_rows(fixture):
                row = rows[0]
                sql, values = build_key_query(
                    fixture["table"],
                    fixture["keyColumns"],
                    row,
                )
                cursor.execute(sql, values)
                found = cursor.fetchone()
                if not found or int(found.get("count", 0)) != len(rows):
                    missing.append(fixture["id"])
    return missing


def verify_absence(connection, checks):
    collisions = []
    with connection.cursor() as cursor:
        for check in checks:
            sql, values = build_key_query(
                check["table"], check["keyColumns"], check["row"]
            )
            cursor.execute(sql, values)
            found = cursor.fetchone()
            if found and int(found.get("count", 0)) != 0:
                collisions.append(check["id"])
    return collisions


def cleanup_fixtures(connection, fixtures):
    deleted = 0
    with connection.cursor() as cursor:
        for fixture in fixtures:
            for rows in group_fixture_rows(fixture):
                row = rows[0]
                sql, values = build_key_query(
                    fixture["table"],
                    fixture["keyColumns"],
                    row,
                    delete=True,
                )
                deleted += cursor.execute(sql, values)
    connection.commit()
    return deleted


def main():
    parser = argparse.ArgumentParser(
        description="天策策略测试隔离 Fixture 管理器"
    )
    parser.add_argument("action", choices=["validate", "setup", "verify", "cleanup"])
    parser.add_argument("--manifest", required=True, help="Fixture JSON 清单")
    parser.add_argument("--run-id", required=True, help="本次测试唯一标识")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--database")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    errors = validate_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    fixtures = render_fixture_rows(manifest, args.run_id)
    absence_checks = render_absence_checks(manifest, args.run_id)
    if args.action == "validate":
        print(json.dumps({
            "ok": True,
            "fixtures": len(fixtures),
            "absenceChecks": len(absence_checks),
        }, ensure_ascii=False))
        return 0

    connection = _connect(args)
    try:
        if args.action == "setup":
            collisions = verify_absence(connection, absence_checks)
            if collisions:
                raise RuntimeError(
                    "隔离空结果键已有存量数据，拒绝继续: " + ", ".join(collisions)
                )
            apply_fixtures(connection, fixtures)
            print(f"已创建 {sum(len(item['rows']) for item in fixtures)} 条隔离数据")
        elif args.action == "verify":
            missing = verify_fixtures(connection, fixtures)
            collisions = verify_absence(connection, absence_checks)
            if missing or collisions:
                print(
                    "Fixture 校验失败: "
                    + ", ".join(missing + [f"应为空:{item}" for item in collisions]),
                    file=sys.stderr,
                )
                return 2
            print("Fixture 校验通过")
        else:
            deleted = cleanup_fixtures(connection, fixtures)
            print(f"已清理 {deleted} 条本次隔离数据")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
