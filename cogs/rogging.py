import discord
from discord.ext import commands
import database

class Logging(commands.Cog):
    """メッセージの作成、編集、削除イベントをデータベースに記録するCog"""
    
    def __init__(self, bot):
        # Botのインスタンスを保持
        self.bot = bot

    # ----------------------------------------------------------------------
    # 1. メッセージ作成時のログ記録
    # ----------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message):
        # Bot自身のメッセージは無視
        if message.author.bot:
            return
        
        # サーバーがないDMメッセージは無視（message.guild.idがないため）
        if message.guild is None:
            return
            
        try:
            # ログをデータベースに記録
            await database.insert_log(
                message.id, 
                message.guild.id, 
                message.channel.id, 
                message.author.id, 
                message.content
            )
        except Exception as e:
            # データベース接続エラーなどをログ出力
            print(f"E:Add New Message Log Err {e}")
        pass


    # ----------------------------------------------------------------------
    # 2. メッセージ編集時のログ記録
    # ----------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Bot自身または内容が変わっていない場合は無視
        if before.author.bot or before.content == after.content:
            return

        # サーバーがないDMメッセージは無視
        if after.guild is None:
            return

        try:
            # データベースのログを更新し、編集前後の情報を取得
            log_details = await database.update_log(
                after.id, 
                after.content
            )
            # 取得したlog_detailsを使って、監査ログチャンネルなどに通知の例
            # print(f"メッセージ編集: U:{log_details['user_id']} | 旧: {log_details['content_old']} -> 新: {log_details['content_new']}")
        except Exception as e:
            print(f"E:Add Edit Message Log Err {e}")


    # ----------------------------------------------------------------------
    # 3. メッセージ削除時のログ記録
    # ----------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # Bot自身が削除したメッセージは無視
        if message.author.bot:
            return
            
        # サーバーがないDMメッセージは無視
        if message.guild is None:
            return

        try:
            # データベースに削除ログを挿入し、削除された内容を取得
            log_details = await database.delete_log(message.id)
            
            # 削除された内容を監査ログチャンネルなどに通知の例
            # print(f"メッセージ削除: U:{log_details['user_id']} | 内容: {log_details['content_deleted']}")
        except Exception as e:
            # データベースにログがない場合（Botが起動していない間に送信されたメッセージなど）もここで捕捉されます
            print(f"E:Add Del Message Log Err {e}")


# ----------------------------------------------------------------------
# Cogのセットアップ関数 (mainファイルから読み込むために必要)
# ----------------------------------------------------------------------
async def setup(bot):
    await bot.add_cog(Logging(bot))