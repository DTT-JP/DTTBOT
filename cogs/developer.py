import discord
from discord.ext import commands
import database
from dotenv import load_dotenv
import os

# .envを読み込む
load_dotenv() 

# .envからアクセスURLを取得
DEVELOPER_UUID = os.getenv("DEVELOPER_UUID")

# 開発者チェック関数
def is_developer():
    def predicate(interaction: discord.Interaction):
        # DEVELOPPER_UUIDが設定されていなければFalse
        if not DEVELOPER_UUID:
            return False
        # 実行者のIDがDEVELOPPER_UUIDと一致すればTrue
        return str(interaction.user.id) == DEVELOPER_UUID
    return discord.app_commands.check(predicate)

class developer(commands.Cog):
    """開発者が使うコマンドを定義するCog"""

    DO_NOT_UNLOAD = [      # アンロード禁止にするcogs
        'cogs.developer',  # これ自身
        'cogs.logging',   # ログ取得
    ]
    
    def __init__(self, bot):
        # Botのインスタンスを保持
        self.bot = bot

    # ----------------------------------------------------------------------
    # /dev_load_cogs コマンド
    # ----------------------------------------------------------------------
    @discord.app_commands.command(name='dev_load_cogs', description='指定したCogをロードします (開発者専用)')
    @discord.app_commands.describe(cog_name='ロードしたいCogのドットパス (例: cogs.fun)')
    @is_developer() # 開発者チェックを適用
    async def load_extension_command(self, interaction: discord.Interaction, cog_name: str):
        """指定したCogをロードします"""
        
        # すぐに応答しないとタイムアウトするため、deferで応答を保留
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.bot.load_extension(cog_name)
            # 成功メッセージを実行者のみに送信
            await interaction.followup.send(f'**SUCCESS**：`{cog_name}` をロードしました。', ephemeral=True)
        except commands.ExtensionAlreadyLoaded:
            # 既にロードされている場合
            await interaction.followup.send(f'**WARNING**：`{cog_name}` は既にロードされています。', ephemeral=True)
        except commands.ExtensionNotFound:
             # ファイルが見つからない場合
            await interaction.followup.send(f'**ERROR**：`{cog_name}` という名前のCogが見つかりませんでした。', ephemeral=True)
        except Exception as e:
             # その他のエラー
            await interaction.followup.send(f'**ERROR**：`{cog_name}` のロード中にエラーが発生しました。\n```{type(e).__name__}: {e}```', ephemeral=True)

    # ----------------------------------------------------------------------
    # /dev_unload_cogs コマンド
    # ----------------------------------------------------------------------
    @discord.app_commands.command(name='dev_unload_cogs', description='指定したCogをアンロードします (開発者専用)')
    @discord.app_commands.describe(cog_name='アンロードしたいCogのドットパス (例: cogs.fun)')
    @is_developer() # 開発者チェックを適用
    async def unload_extension_command(self, interaction: discord.Interaction, cog_name: str):
        """指定したCogをアンロードします"""
        
        await interaction.response.defer(ephemeral=True)

        # アンロード禁止にするcogsのチェック
        if cog_name in self.DO_NOT_UNLOAD:
            await interaction.followup.send(
            f'**ERROR**：指定されたコグ (`{cog_name}`) は**アンロード禁止にするcogs**に含まれているためアンロードできません。',
            ephemeral=True
            )
            return

        try:
            await self.bot.unload_extension(cog_name)
            # 成功メッセージを実行者のみに送信
            await interaction.followup.send(f'**SUCCESS**：`{cog_name}` をアンロードしました。', ephemeral=True)
        except commands.ExtensionNotLoaded:
             # 既にアンロードされている場合
                 await interaction.followup.send(f'**WARNING**：`{cog_name}` は既にアンロードされています。', ephemeral=True)
        except commands.ExtensionNotFound:
            # ファイルが見つからない場合
            await interaction.followup.send(f'**ERROR**：`{cog_name}` という名前のCogが見つかりませんでした。', ephemeral=True)
        except Exception as e:
            # その他のエラー
            await interaction.followup.send(f'**ERROR**：`{cog_name}` のアンロード中にエラーが発生しました。\n```{type(e).__name__}: {e}```', ephemeral=True)
    
    # ----------------------------------------------------------------------
    # /dev_reset_db コマンド
    # ----------------------------------------------------------------------
    @discord.app_commands.command(name='dev_reset_db', description='データベースを初期化します (開発者専用)')
    @is_developer() # 開発者チェックを適用
    async def reset_db_command(self, interaction: discord.Interaction):
        """データベースを初期化"""
        
        await interaction.response.defer(ephemeral=True)

        try:
            resetDB = await database.reset_database()
            await interaction.followup.send(f'データベース初期化結果: {resetDB}', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'**ERROR**：データベースリセット中にエラーが発生しました。\n```{type(e).__name__}: {e}```', ephemeral=True)
        
# ----------------------------------------------------------------------
# Cogのセットアップ関数 (mainファイルから読み込むために必要)
# ----------------------------------------------------------------------
async def setup(bot):
    await bot.add_cog(developer(bot))