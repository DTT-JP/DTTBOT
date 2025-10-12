import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
import database

# .envを読み込み
load_dotenv() 

# envからbotトークン取得
TOKEN = os.getenv('DISCORD_BOT_TOKEN') 

# インテントの設定
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True
intents.voice_states = True

# BOTの初期化
bot = commands.Bot(command_prefix='!', intents=intents)

# 読み込むコグファイルのリスト
INITIAL_EXTENSIONS = [
    'cogs.rogging', # メッセージログを取得し、処理するcogs
]

# 起動時の処理
@bot.event
async def on_ready():
    print(f'Logging in: {bot.user}')

    # データベースに接続
    await database.connect_to_db()
    # たりないテーブルを作成
    await database.recreate_tables()
    
    # 起動時にすべてのコグを読み込む
    for cog in INITIAL_EXTENSIONS:
        try:
            await bot.load_extension(cog)
            print(f'Loading Cogs: {cog} loaded successfully.')
        except Exception as e:
            print(f'E: Failed to load cog {cog}: {e}')

    # スラッシュコマンドをDiscordに同期
    try:
        await bot.tree.sync()
        print('Loading Cogs: Slash commands synchronized successfully.')
    except Exception as e:
        print(f'E: Failed to synchronize slash commands: {e}')

if TOKEN is not None:
    bot.run(TOKEN)
else:
    print("E: Failed to find Discord-Token in .env file.")

@bot.event
async def on_disconnect():
    await database.close_db_connection()