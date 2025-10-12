import os
import asyncpg
import datetime
from dotenv import load_dotenv

# .envを読み込み
load_dotenv() 

# 接続URLを環境変数から取得 (例: postgresql://user:pass@host:port/dbname)
DATABASE_URL = os.getenv("DATABASE_URL")

# グローバル接続オブジェクト
conn = None

async def connect_to_db():
    """データベースに接続し、グローバル接続オブジェクトを設定する"""
    global conn
    if conn is not None:
        return

    if not DATABASE_URL:
        print("E: DATABASE_URLが設定されていません。")
        return

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("I: データベースに接続しました。")
        # 接続後、テーブルが存在することを確認・作成する
        await create_tables()
    except Exception as e:
        print(f"E: データベース接続エラー: {e}")
        conn = None # 接続失敗時はNoneを維持

async def close_db_connection():
    """データベース接続を閉じる"""
    global conn
    if conn:
        await conn.close()
        conn = None
        print("I: データベース接続を閉じました。")

# ----------------------------------------------------------------------
# データベース初期化/リセット機能
# ----------------------------------------------------------------------

async def create_tables():
    """必要なすべてのテーブル（logs, auth_messages, settings）を作成する
    テーブルが既に存在する場合は何もしません (IF NOT EXISTS)。
    """
    if conn is None: return

    # 1. ログテーブル
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

    # 2. 認証Bot用テーブル
    # id: 認証メッセージを一意に識別するBot内部ID (自動連番)
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

    # 3. サーバー設定テーブル (例)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            server_id BIGINT PRIMARY KEY,
            setting_key TEXT NOT NULL,
            setting_value TEXT
        );
    """)
    print("I: 必要なすべてのテーブルが存在することを確認しました。")

async def reset_database():
    """すべてのテーブルを削除し、データベースを完全にリセットする (全体リセット)"""
    if conn is None: return "データベースに接続されていません。"
    try:
        # CASCADEで依存関係にあるオブジェクトも削除
        await conn.execute("DROP TABLE IF EXISTS logs CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS auth_messages CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS server_settings CASCADE;")
        
        # テーブルを削除した後、再作成する
        await create_tables() 
        return "✅ 全てのテーブルを削除し、再作成しました。（完全リセット）"
    except Exception as e:
        return f"❌ データベースリセットエラー: {e}"

async def recreate_tables():
    """テーブルを削除せず、存在しないテーブルのみ作成する (テーブル作成)"""
    if conn is None: return "データベースに接続されていません。"
    try:
        # 既にテーブルが存在する場合は無視されるため、データは保持される
        await create_tables()
        return "✅ 存在しないテーブルを作成しました。既存のデータは保持されています。"
    except Exception as e:
        return f"❌ テーブル作成エラー: {e}"

# ----------------------------------------------------------------------
# 認証Bot機能: 登録と取得
# ----------------------------------------------------------------------

async def add_auth_message(server_id, channel_id, title, comment, button_name, role_id):
    """
    認証メッセージ情報をDBに挿入し、自動生成された一意のIDを返します。
    """
    if conn is None: return None

    # RETURNING id で、データベースが自動生成したID (BIGSERIAL) を即座に取得
    record_id = await conn.fetchval("""
        INSERT INTO auth_messages (
            timestamp, server_id, channel_id, title, comment, button_name, role_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7
        ) RETURNING id;
    """, datetime.datetime.now(), server_id, channel_id, title, comment, button_name, role_id)
    
    return record_id # 一意のID (BIGINT) を返す

async def get_auth_message(record_id):
    """
    一意のID (record_id) を与えると、その認証メッセージの全ての情報を返します。
    """
    if conn is None: return None

    # 必要なすべてのフィールドを取得
    record = await conn.fetchrow("""
        SELECT 
            server_id, channel_id, title, comment, button_name, role_id
        FROM auth_messages
        WHERE id = $1;
    """, record_id)

    if record:
        # 辞書形式で情報を返す
        return {
            "server_id": record['server_id'],
            "channel_id": record['channel_id'],
            "title": record['title'],
            "comment": record['comment'],
            "button_name": record['button_name'],
            "role_id": record['role_id'],
        }
    return None # 見つからない場合はNoneを返す

# ----------------------------------------------------------------------
# 既存のログ記録機能 (変更なし)
# ----------------------------------------------------------------------

async def insert_log(message_id, server_id, channel_id, user_id, content):
    """メッセージログをlogsテーブルに挿入する"""
    if conn is None: return

    try:
        await conn.execute("""
            INSERT INTO logs (id, timestamp, server_id, channel_id, user_id, content)
            VALUES ($1, $2, $3, $4, $5, $6);
        """, message_id, datetime.datetime.now(), server_id, channel_id, user_id, content)
    except Exception as e:
        # ログはPRIMARY KEY (id) が重複すると失敗するため、エラーを無視することが多い
        pass

# ----------------------------------------------------------------------
# 既存の設定機能 (変更なし)
# ----------------------------------------------------------------------
# 例: サーバーごとの設定を保存する関数 (実装は省略)
async def set_server_setting(server_id, key, value):
    """サーバー設定を保存・更新する"""
    if conn is None: return
    await conn.execute("""
        INSERT INTO server_settings (server_id, setting_key, setting_value)
        VALUES ($1, $2, $3)
        ON CONFLICT (server_id) DO UPDATE
        SET setting_key = $2, setting_value = $3;
    """, server_id, key, value)
    
async def get_server_setting(server_id, key):
    """サーバー設定を取得する"""
    if conn is None: return None
    return await conn.fetchval("""
        SELECT setting_value FROM server_settings WHERE server_id = $1 AND setting_key = $2;
    """, server_id, key)
