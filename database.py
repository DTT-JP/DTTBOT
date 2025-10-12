import asyncpg
import os
from typing import List, Any, Optional, Dict

# 環境変数からDB接続URLを取得
DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("E:not found 'DATABASE_URL'")

POOL: Optional[asyncpg.Pool] = None
LogDetails = Dict[str, Any]

# ----------------------------------------------------------------------
# 接続管理関数
# ----------------------------------------------------------------------

async def connect_to_db() -> bool:
    """データベース接続プールを確立し、全テーブルを初期化する。"""
    global POOL
    if not DATABASE_URL: return False
    if POOL is not None: return True

    try:
        POOL = await asyncpg.create_pool(DATABASE_URL)
        print("Connnected to the database successfully.")
        await _initialize_tables()
        print("Database tables initialized.")
        return True
    except Exception as e:
        print(f"E: Detabace Accsess Err {e}")
        POOL = None
        return False

async def close_db_connection() -> None:
    """データベース接続プールを閉じる。"""
    global POOL
    if POOL: await POOL.close()
    POOL = None

def is_connected() -> bool:
    """データベース接続プールがアクティブかどうかを返す。"""
    return POOL is not None

# ----------------------------------------------------------------------
# 内部初期化関数
# ----------------------------------------------------------------------

async def _initialize_tables():
    """テーブルが存在しない場合に作成する。"""
    if not POOL: return

    async with POOL.acquire() as conn:
        async with conn.transaction():
            # 1. ログテーブル
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id BIGSERIAL PRIMARY KEY,
                    server_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    action_type VARCHAR(10) NOT NULL, -- 'CREATE', 'EDIT', 'DELETE'
                    content TEXT,                     -- メッセージの現在の内容
                    previous_log_id BIGINT,           -- 編集前のログレコードID (EDIT, DELETE時)
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_message_id_create ON logs (message_id) WHERE action_type = 'CREATE';")
            
            # 2. サーバー設定テーブル
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    server_id BIGINT NOT NULL,
                    setting_key VARCHAR(50) NOT NULL,
                    setting_value TEXT,
                    PRIMARY KEY (server_id, setting_key)
                );
            """)

            # 3. ユーザー設定テーブル
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id BIGINT NOT NULL,
                    setting_key VARCHAR(50) NOT NULL,
                    setting_value TEXT,
                    PRIMARY KEY (user_id, setting_key)
                );
            """)

            # 4. グローバル・ブロックリスト
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS global_blocklist (
                    id BIGSERIAL PRIMARY KEY,
                    value TEXT UNIQUE NOT NULL, 
                    type VARCHAR(10) NOT NULL,  -- 'USER_ID' or 'IP'
                    reason TEXT,
                    added_by BIGINT
                );
            """)
            
            # 5. サーバーごとのブロックリスト
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS server_blocklist (
                    id BIGSERIAL PRIMARY KEY,
                    server_id BIGINT NOT NULL,
                    value TEXT NOT NULL,
                    type VARCHAR(10) NOT NULL,
                    reason TEXT,
                    added_by BIGINT,
                    UNIQUE (server_id, value)
                );
            """)


# ----------------------------------------------------------------------
# CRUD 操作ヘルパー (汎用)
# ----------------------------------------------------------------------

async def execute_query(query: str, *params: Any) -> None:
    """データを変更するクエリ (INSERT, UPDATE, DELETE) を実行する。"""
    if not is_connected(): raise ConnectionError("データベースに接続されていません。")
    async with POOL.acquire() as conn: await conn.execute(query, *params)

async def fetch_one(query: str, *params: Any) -> Optional[asyncpg.Record]:
    """SELECT クエリを実行し、結果の1行を取得する。"""
    if not is_connected(): raise ConnectionError("データベースに接続されていません。")
    async with POOL.acquire() as conn: return await conn.fetchrow(query, *params)

async def fetch_all(query: str, *params: Any) -> List[asyncpg.Record]:
    """SELECT クエリを実行し、結果の全行をリストで取得する。"""
    if not is_connected(): raise ConnectionError("データベースに接続されていません。")
    async with POOL.acquire() as conn: return await conn.fetch(query, *params)

# ----------------------------------------------------------------------
# ログ (logs) 拡張関数
# ----------------------------------------------------------------------

async def insert_log(
    message_id: int, 
    server_id: int, 
    channel_id: int, 
    user_id: int, 
    content: str
) -> LogDetails:
    """
    メッセージ作成ログを記録し、その詳細を返す。（引数順序変更済み）
    
    Returns:
        LogDetails: 作成されたログの主要情報を含む辞書。
    """
    sql = """
    INSERT INTO logs (message_id, server_id, channel_id, user_id, action_type, content) 
    VALUES ($1, $2, $3, $4, 'CREATE', $5)
    RETURNING id, server_id, channel_id, user_id, message_id, content
    """
    record = await fetch_one(sql, message_id, server_id, channel_id, user_id, content)
    if record:
        return dict(record)
    raise Exception("ログ記録に失敗しました。")

async def update_log(message_id: int, new_content: str) -> LogDetails:
    """
    メッセージ編集ログを記録し、編集前後の情報を返す。
    
    Returns:
        LogDetails: 編集前後の内容、ID情報を含む辞書。
    """
    if not is_connected(): raise ConnectionError("データベースに接続されていません。")

    async with POOL.acquire() as conn:
        async with conn.transaction():
            # 1. 編集前の最新のログを取得
            sql_prev = "SELECT id, content, server_id, channel_id, user_id FROM logs WHERE message_id = $1 ORDER BY id DESC LIMIT 1"
            prev_record = await conn.fetchrow(sql_prev, message_id)
            
            if not prev_record:
                raise ValueError(f"メッセージID {message_id} のログが見つかりませんでした。")
                
            previous_log_id = prev_record['id']
            old_content = prev_record['content']
            
            # 2. 新しい編集ログを挿入
            sql_insert = """
            INSERT INTO logs (server_id, channel_id, user_id, message_id, action_type, content, previous_log_id) 
            VALUES ($1, $2, $3, $4, 'EDIT', $5, $6)
            RETURNING id, content
            """
            new_record = await conn.fetchrow(
                sql_insert, 
                prev_record['server_id'], 
                prev_record['channel_id'], 
                prev_record['user_id'], 
                message_id, 
                new_content, 
                previous_log_id
            )
            
            if new_record:
                return {
                    'server_id': prev_record['server_id'],
                    'channel_id': prev_record['channel_id'],
                    'user_id': prev_record['user_id'],
                    'message_id': message_id,
                    'content_new': new_content,
                    'content_old': old_content,
                    'action_type': 'EDIT'
                }
            raise Exception("編集ログ記録に失敗しました。")


async def delete_log(message_id: int) -> LogDetails:
    """
    メッセージ削除ログを記録し、削除されたメッセージの情報を返す。
    
    Returns:
        LogDetails: 削除された内容、ID情報を含む辞書。
    """
    if not is_connected(): raise ConnectionError("データベースに接続されていません。")

    async with POOL.acquire() as conn:
        async with conn.transaction():
            # 1. 削除対象の最新のログを取得
            sql_prev = "SELECT id, server_id, channel_id, user_id, content FROM logs WHERE message_id = $1 ORDER BY id DESC LIMIT 1"
            prev_record = await conn.fetchrow(sql_prev, message_id)
            
            if not prev_record:
                raise ValueError(f"メッセージID {message_id} のログが見つかりませんでした。")
                
            previous_log_id = prev_record['id']
            deleted_content = prev_record['content']
            
            # 2. 削除ログを挿入
            sql_insert = """
            INSERT INTO logs (server_id, channel_id, user_id, message_id, action_type, content, previous_log_id) 
            VALUES ($1, $2, $3, $4, 'DELETE', $5, $6)
            RETURNING server_id
            """
            # contentには削除されたことを示すプレースホルダを挿入
            new_record = await conn.fetchrow(
                sql_insert, 
                prev_record['server_id'], 
                prev_record['channel_id'], 
                prev_record['user_id'], 
                message_id, 
                "メッセージは削除されました", 
                previous_log_id
            )

            if new_record:
                # 戻り値の整形
                return {
                    'server_id': prev_record['server_id'],
                    'channel_id': prev_record['channel_id'],
                    'user_id': prev_record['user_id'],
                    'message_id': message_id,
                    'content_deleted': deleted_content, # 削除された内容
                    'action_type': 'DELETE'
                }
            raise Exception("削除ログ記録に失敗しました。")


async def get_logs_by_user(user_id: int, limit: int = 10):
    """特定のユーザーの最新のログを取得する。"""
    sql = "SELECT content, created_at, action_type, previous_log_id FROM logs WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2"
    return await fetch_all(sql, user_id, limit)

async def get_filtered_logs(
    server_id: int, 
    channel_id: Optional[int] = None, 
    user_id: Optional[int] = None, 
    time_limit_minutes: Optional[int] = None
) -> List[asyncpg.Record]:
    """
    指定した条件でログをフィルタリングして取得する。
    """
    base_sql = "SELECT * FROM logs WHERE server_id = $1"
    params = [server_id]
    
    if channel_id:
        base_sql += f" AND channel_id = ${len(params) + 1}"
        params.append(channel_id)
        
    if user_id:
        base_sql += f" AND user_id = ${len(params) + 1}"
        params.append(user_id)
        
    if time_limit_minutes is not None and time_limit_minutes > 0:
        base_sql += f" AND created_at >= NOW() - INTERVAL '{time_limit_minutes} minutes'"
        
    base_sql += " ORDER BY created_at DESC LIMIT 100"
    
    return await fetch_all(base_sql, *params)


# ----------------------------------------------------------------------
# サーバー設定 (server_settings)
# ----------------------------------------------------------------------
async def set_server_setting(server_id: int, key: str, value: str):
    sql = """
    INSERT INTO server_settings (server_id, setting_key, setting_value) 
    VALUES ($1, $2, $3)
    ON CONFLICT (server_id, setting_key) DO UPDATE 
    SET setting_value = $3
    """
    await execute_query(sql, server_id, key, value)

async def get_server_setting(server_id: int, key: str) -> Optional[str]:
    sql = "SELECT setting_value FROM server_settings WHERE server_id = $1 AND setting_key = $2"
    record = await fetch_one(sql, server_id, key)
    return record['setting_value'] if record else None

# ----------------------------------------------------------------------
# ユーザー設定 (user_settings)
# ----------------------------------------------------------------------
async def set_user_setting(user_id: int, key: str, value: str):
    sql = """
    INSERT INTO user_settings (user_id, setting_key, setting_value) 
    VALUES ($1, $2, $3)
    ON CONFLICT (user_id, setting_key) DO UPDATE 
    SET setting_value = $3
    """
    await execute_query(sql, user_id, key, value)

async def get_user_setting(user_id: int, key: str) -> Optional[str]:
    sql = "SELECT setting_value FROM user_settings WHERE user_id = $1 AND setting_key = $2"
    record = await fetch_one(sql, user_id, key)
    return record['setting_value'] if record else None

# ----------------------------------------------------------------------
# ブロックリスト
# ----------------------------------------------------------------------

async def add_global_block(value: str, type: str, reason: str, added_by: int):
    sql = "INSERT INTO global_blocklist (value, type, reason, added_by) VALUES ($1, $2, $3, $4) ON CONFLICT (value) DO NOTHING"
    await execute_query(sql, value, type, reason, added_by)

async def is_globally_blocked(value: str) -> bool:
    sql = "SELECT 1 FROM global_blocklist WHERE value = $1"
    return await fetch_one(sql, value) is not None

async def add_server_block(server_id: int, value: str, type: str, reason: str, added_by: int):
    sql = "INSERT INTO server_blocklist (server_id, value, type, reason, added_by) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (server_id, value) DO UPDATE SET reason = $4, added_by = $5"
    await execute_query(sql, server_id, value, type, reason, added_by)

async def is_server_blocked(server_id: int, value: str) -> bool:
    sql = "SELECT 1 FROM server_blocklist WHERE server_id = $1 AND value = $2"
    return await fetch_one(sql, server_id, value) is not None

async def check_is_blocked(server_id: int, value: str, type: str) -> bool:
    is_global = await is_globally_blocked(value)
    if is_global: return True
    if server_id > 0:
        return await is_server_blocked(server_id, value)
    return False

async def get_block_details(server_id: int, value: str, type: str) -> Optional[asyncpg.Record]:
    record = None
    if server_id > 0:
        sql_server = "SELECT reason, added_by, 'server' AS list_type, id FROM server_blocklist WHERE server_id = $1 AND value = $2 AND type = $3"
        record = await fetch_one(sql_server, server_id, value, type)
        if record: return record

    sql_global = "SELECT reason, added_by, 'global' AS list_type, id FROM global_blocklist WHERE value = $1 AND type = $2"
    record = await fetch_one(sql_global, value, type)
    return record

async def get_processor_actions(added_by_user_id: int) -> List[int]:
    sql_global = "SELECT id FROM global_blocklist WHERE added_by = $1"
    sql_server = "SELECT id FROM server_blocklist WHERE added_by = $1"
    
    global_ids = [r['id'] for r in await fetch_all(sql_global, added_by_user_id)]
    server_ids = [r['id'] for r in await fetch_all(sql_server, added_by_user_id)]
    return global_ids + server_ids

async def get_block_entry_details(entry_id: int, is_global: bool) -> Optional[asyncpg.Record]:
    table_name = "global_blocklist" if is_global else "server_blocklist"
    sql = f"SELECT * FROM {table_name} WHERE id = $1"
    return await fetch_one(sql, entry_id)

# ----------------------------------------------------------------------
# end
# ----------------------------------------------------------------------