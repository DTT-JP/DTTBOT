import os
import asyncpg
import datetime
from dotenv import load_dotenv

# .envを読み込む
load_dotenv() 

# .envからアクセスURLを取得
DATABASE_URL = os.getenv("DATABASE_URL")

# グローバル接続オブジェクト
conn = None

# --- ヘルパー関数 ---
def _get_scope_id(server_id: int | None) -> int | None:
    return server_id if server_id is not None else None

async def connect_to_db():
    """
    データベースに接続し、グローバル接続オブジェクトを設定する。
    接続成功後、create_tables()を呼び出してテーブルの存在を確認する。
    
    引数: なし
    戻り値: なし
    """
    global conn
    if conn is not None:
        return

    if not DATABASE_URL:
        print("E: DATABASE_URLが設定されていません。")
        return

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("I: データベースに接続しました。")
        await create_tables()
    except Exception as e:
        print(f"E: データベース接続エラー: {e}")
        conn = None

async def close_db_connection():
    """
    データベース接続を閉じる。
    
    引数: なし
    戻り値: なし
    """
    global conn
    if conn:
        await conn.close()
        conn = None
        print("I: データベース接続を閉じました。")

# ----------------------------------------------------------------------
# データベース初期化/リセット機能
# ----------------------------------------------------------------------

async def create_tables():
    """
    必要なすべてのテーブル（logs, auth_messages, server_settings, user_settings, blacklist_entries）を作成する。
    テーブルが既に存在する場合は何もしません (IF NOT EXISTS)。
    
    引数: なし
    戻り値: なし
    """
    if conn is None: return

    # 1. ログテーブル: Discordメッセージのログを保持
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id BIGINT PRIMARY KEY,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            server_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            content TEXT
        );
    """)

    # 2. 認証Bot用テーブル: ロール付与パネルの情報を保持
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_messages (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            server_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            title TEXT,
            comment TEXT,
            button_name TEXT NOT NULL,
            role_id BIGINT NOT NULL
        );
    """)

    # 3. サーバー設定テーブル: サーバーごとの設定を保持
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            server_id BIGINT PRIMARY KEY,
            setting_key TEXT NOT NULL,
            setting_value TEXT
        );
    """)
    
    # 4. ユーザー設定テーブル: ユーザーIDと設定キーの複合主キーで複数の設定を保持
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id BIGINT NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT,
            PRIMARY KEY (user_id, setting_key)
        );
    """)

    # 5. ブラックリストテーブル: 複数の識別子とスコープに対応
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist_entries (
            id BIGSERIAL PRIMARY KEY,
            scope_id BIGINT,              -- サーバーID (グローバルの場合はNULL)
            identifier_value TEXT NOT NULL, -- IPアドレスまたはUUIDの値
            identifier_type TEXT NOT NULL,  -- 'IP' または 'UUID'
            added_by_uuid TEXT NOT NULL,    -- 追加した管理者のUUID
            reason TEXT,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            -- 同じスコープ(サーバーIDまたはNULL)内で、同じ識別子の種類と値は重複できない
            UNIQUE (scope_id, identifier_value, identifier_type)
        );
    """)
    
    print("I: 必要なすべてのテーブルが存在することを確認しました。")

async def reset_database():
    """
    すべてのテーブルを削除し、データベースを完全にリセットする (全体リセット)。
    既存のすべてのデータが失われます。
    
    引数: なし
    戻り値: 処理結果を示すメッセージ (str)
    """
    if conn is None: return "データベースに接続されていません。"
    try:
        # CASCADEで依存関係にあるオブジェクトも削除
        await conn.execute("DROP TABLE IF EXISTS logs CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS auth_messages CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS server_settings CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS user_settings CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS blacklist_entries CASCADE;") 
        
        # テーブルを削除した後、再作成する
        await create_tables() 
        return "I:全てのテーブルを削除し、再作成しました。"
    except Exception as e:
        return f"E:データベースリセットエラー {e}"

async def recreate_tables():
    """
    テーブルを削除せず、存在しないテーブルのみ作成する (テーブル作成)。
    既存のデータは保持されます。
    
    引数: なし
    戻り値: 処理結果を示すメッセージ (str)
    """
    if conn is None: return "データベースに接続されていません。"
    try:
        await create_tables()
        return "I:存在しないテーブルを作成しました。既存のデータは保持されています。"
    except Exception as e:
        return f"E:テーブル作成エラー {e}"

# ----------------------------------------------------------------------
# 認証機能: 登録と取得・削除 (Auth Messages)
# ----------------------------------------------------------------------

async def add_auth_message(server_id, channel_id, title, comment, button_name, role_id):
    """
    認証メッセージ情報をDBに挿入し、自動生成された一意のIDを返します。
    
    引数: 
        server_id (int): サーバーID
        channel_id (int): チャンネルID
        title (str): パネルのタイトル
        comment (str): パネルのコメント/説明
        button_name (str): ボタンに表示するテキスト
        role_id (int): 付与するロールのID
    戻り値: 登録されたレコードの一意のID (int) または None (接続失敗時)
    """
    if conn is None: return None

    record_id = await conn.fetchval("""
        INSERT INTO auth_messages (
            timestamp, server_id, channel_id, title, comment, button_name, role_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7
        ) RETURNING id;
    """, datetime.datetime.now(), server_id, channel_id, title, comment, button_name, role_id)
    
    return record_id

async def get_auth_message(record_id):
    """
    一意のID (record_id) を与えると、その認証メッセージの全ての情報を辞書で返します。
    
    引数: record_id (int): 認証メッセージの一意のID
    戻り値: 認証情報の辞書 (dict) または None
    """
    if conn is None: return None

    record = await conn.fetchrow("""
        SELECT 
            server_id, channel_id, title, comment, button_name, role_id
        FROM auth_messages
        WHERE id = $1;
    """, record_id)

    if record:
        return {
            "server_id": record['server_id'],
            "channel_id": record['channel_id'],
            "title": record['title'],
            "comment": record['comment'],
            "button_name": record['button_name'],
            "role_id": record['role_id'],
        }
    return None

async def get_all_auth_ids_for_server(server_id):
    """
    特定のサーバーIDに登録されているすべての認証メッセージの一意のID (id) をリストで返します。
    
    引数: server_id (int): サーバーID
    戻り値: 一意のIDのリスト (list[int])
    """
    if conn is None: return []

    records = await conn.fetch("""
        SELECT id
        FROM auth_messages
        WHERE server_id = $1;
    """, server_id)

    return [record['id'] for record in records]

async def delete_auth_message(record_id):
    """
    一意のID (record_id) に対応する認証メッセージのデータベース記録を削除します。
    
    引数: record_id (int): 削除する認証メッセージの一意のID
    戻り値: 削除された行数 (int) (1: 成功, 0: 失敗)
    """
    if conn is None: return 0

    status = await conn.execute("""
        DELETE FROM auth_messages
        WHERE id = $1;
    """, record_id)
    
    return int(status.split(' ')[1])

# ----------------------------------------------------------------------
# ログ記録機能 (Logs)
# ----------------------------------------------------------------------

async def insert_log(message_id, server_id, channel_id, user_id, content):
    """
    メッセージログをlogsテーブルに挿入する。
    
    引数: 
        message_id (int): メッセージID
        server_id (int): サーバーID
        channel_id (int): チャンネルID
        user_id (int): ユーザーID
        content (str): メッセージの本文
    戻り値: なし
    """
    if conn is None: return

    try:
        await conn.execute("""
            INSERT INTO logs (id, timestamp, server_id, channel_id, user_id, content)
            VALUES ($1, $2, $3, $4, $5, $6);
        """, message_id, datetime.datetime.now(), server_id, channel_id, user_id, content)
    except Exception as e:
        pass

# ----------------------------------------------------------------------
# 設定機能 (Server and User Settings)
# ----------------------------------------------------------------------

async def set_server_setting(server_id, key, value):
    """
    サーバー設定を保存・更新する。
    
    引数: 
        server_id (int): サーバーID
        key (str): 設定キー
        value (str): 設定値
    戻り値: なし
    """
    if conn is None: return
    await conn.execute("""
        INSERT INTO server_settings (server_id, setting_key, setting_value)
        VALUES ($1, $2, $3)
        ON CONFLICT (server_id) DO UPDATE
        SET setting_key = $2, setting_value = $3;
    """, server_id, key, value)
    
async def get_server_setting(server_id, key):
    """
    サーバー設定を取得する。
    
    引数: 
        server_id (int): サーバーID
        key (str): 設定キー
    戻り値: 設定値 (str) または None
    """
    if conn is None: return None
    return await conn.fetchval("""
        SELECT setting_value FROM server_settings WHERE server_id = $1 AND setting_key = $2;
    """, server_id, key)

async def set_user_setting(user_id, key, value):
    """
    ユーザー設定を保存・更新する。
    user_idとsetting_keyの複合主キーに基づいて設定を保存・更新します。
    
    引数: 
        user_id (int): ユーザーID
        key (str): 設定キー (例: 'language', 'timezone')
        value (str): 設定値
    戻り値: なし
    """
    if conn is None: return
    await conn.execute("""
        INSERT INTO user_settings (user_id, setting_key, setting_value)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, setting_key) DO UPDATE
        SET setting_value = $3;
    """, user_id, key, value)

async def get_user_setting(user_id, key):
    """
    ユーザー設定を取得する。
    
    引数: 
        user_id (int): ユーザーID
        key (str): 設定キー
    戻り値: 設定値 (str) または None
    """
    if conn is None: return None
    return await conn.fetchval("""
        SELECT setting_value FROM user_settings WHERE user_id = $1 AND setting_key = $2;
    """, user_id, key)

# ----------------------------------------------------------------------
# ブラックリスト機能 (Blacklist) 
# ----------------------------------------------------------------------

async def add_to_blacklist(identifier_type: str, identifier_value: str, added_by_uuid: str, reason: str = None, server_id: int = None):
    """
    IPアドレスまたはUUIDをグローバルまたはサーバー単位のブラックリストに追加する。
    
    引数:
        identifier_type (str): 識別子の種類 ('IP'または'UUID')
        identifier_value (str): IPアドレスまたはUUIDの値
        added_by_uuid (str): 追加した管理者のUUID
        reason (str): ブラックリスト登録の理由 (オプション)
        server_id (int | None): サーバーID (Noneの場合グローバル)
    戻り値: なし
    """
    if conn is None: return

    scope_id = _get_scope_id(server_id)

    await conn.execute("""
        INSERT INTO blacklist_entries (
            scope_id, identifier_value, identifier_type, added_by_uuid, reason, timestamp
        ) VALUES (
            $1, $2, $3, $4, $5, $6
        )
        ON CONFLICT (scope_id, identifier_value, identifier_type) DO UPDATE
        SET 
            added_by_uuid = $4,
            reason = $5,
            timestamp = $6;
    """, scope_id, identifier_value, identifier_type, added_by_uuid, reason, datetime.datetime.now())

async def remove_from_blacklist(identifier_type: str, identifier_value: str, server_id: int = None):
    """
    IPアドレスまたはUUIDをブラックリストから削除する。
    
    引数:
        identifier_type (str): 識別子の種類 ('IP'または'UUID')
        identifier_value (str): IPアドレスまたはUUIDの値
        server_id (int | None): サーバーID (Noneの場合グローバル)
    戻り値: 削除された行数 (int) (1: 成功, 0: 失敗)
    """
    if conn is None: return 0
    
    scope_id = _get_scope_id(server_id)
    
    status = await conn.execute("""
        DELETE FROM blacklist_entries
        WHERE 
            scope_id IS NOT DISTINCT FROM $1 AND
            identifier_value = $2 AND
            identifier_type = $3;
    """, scope_id, identifier_value, identifier_type)
    
    return int(status.split(' ')[1])

async def is_blacklisted_global(identifier_type: str, identifier_value: str):
    """
    IPアドレスまたはUUIDがグローバルブラックリストに登録されているか確認する（scope_id IS NULL）。
    
    引数:
        identifier_type (str): 識別子の種類 ('IP'または'UUID')
        identifier_value (str): IPアドレスまたはUUIDの値
    戻り値: 登録されている場合は理由 (str)、されていない場合は None
    """
    if conn is None: return None

    reason = await conn.fetchval("""
        SELECT reason 
        FROM blacklist_entries
        WHERE scope_id IS NULL AND identifier_type = $1 AND identifier_value = $2;
    """, identifier_type, identifier_value)
    
    return reason

async def is_blacklisted_server(identifier_type: str, identifier_value: str, server_id: int):
    """
    IPアドレスまたはUUIDが特定のサーバーのブラックリストに登録されているか確認する（scope_id = server_id）。
    グローバルブラックリストはチェックしない。
    
    引数:
        identifier_type (str): 識別子の種類 ('IP'または'UUID')
        identifier_value (str): IPアドレスまたはUUIDの値
        server_id (int): チェックするサーバーID
    戻り値: 登録されている場合は理由 (str)、されていない場合は None
    """
    if conn is None: return None
    
    reason = await conn.fetchval("""
        SELECT reason 
        FROM blacklist_entries
        WHERE scope_id = $1 AND identifier_type = $2 AND identifier_value = $3;
    """, server_id, identifier_type, identifier_value)
    
    return reason
