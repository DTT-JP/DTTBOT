# DTTBOT Githubリポジトリ
# **まだリリースされていない未完成なプロジェクトです**

**[English](README.en.md)** | **[简体中文](README.zh-CN.md)** | **[Ferur](README.Ferur.md)**

## 目次

[セットアップ手順](#セットアップ手順)

## セットアップ手順
[Ubuntu/Debian](#debain系の導入手順)

~~[Arch](#arch系の導入手順)~~

### Debain系の導入手順

* システムを更新して最新に
  
  `sudo apt update && sudo apt upgrade -y`

* 必要なものをインストール

  `sudo apt install -y python3 python3-pip python3-venv python3-dev libpq-dev postgresql postgresql-contrib	git`

* プロジェクトをクローン

  `git clone https://github.com/DTT-JP/zikosyoukai.git && rm -rf zikosyoukai/.git`

* 作業フォルダに移動

  `cd zikosyoukai`

* PostgreSQLが動いているか確認

  `sudo systemctl status postgresql`

* ユーザーをPostgreSQLの管理ユーザーへ

  `sudo -i -u postgres`

* PostgreSQLプロンプトへ

  `psql`

* postgresユーザーにパスワードを設定

  `ALTER USER postgres WITH PASSWORD 'your_secure_password';`

  'your_secure_password' の部分は推測されにくいパスワードを設定してください（以後使います）

* PostgreSQLプロンプトから抜ける

  `\q`

* Linuxのpostgessユーザーから抜ける

  `exit`

* PostgreSQLを再起動

  `sudo systemctl restart postgresql`

* env.templateに書き込み

  ファイル内に書き方は記述されています

* env.templateを.envへ

  `mv env.template .env`

* .envの権限を設定

  `chmod 600 .env`

* venvを作成

  `python3 -m venv venv`

* venvを有効化

  `source venv/bin/activate`

* pythonライブラリをインストール

  `pip install -r requirements.txt`

* BOTを実行

  `python main.py`
### Arch系の導入手順

* 準備中、、、
