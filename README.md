# Crypto AI Lab Mobile v0.2

iPhone Safariに対応した、暗号資産のバックテストと手動更新式ペーパートレードのStreamlitアプリです。**実際の売買注文は一切行いません。AI予測モデルも未実装です。**

## スマホで使う（Streamlit Community Cloud）
1. GitHubに**プライベート**リポジトリを作り、このZIPの中身（`app.py`, `engine.py`, `requirements.txt`, `.streamlit/config.toml`）をアップロード。
2. https://share.streamlit.io/ にGitHubアカウントでログインして「Create app」を選択。
3. リポジトリ、ブランチ、エントリーファイル `app.py` を指定してDeploy。
4. 発行されたURLをiPhoneのSafariで開く。Safariの共有メニューから「ホーム画面に追加」も可能。

**注意：** Community Cloudの無料ホスティングはスリープ・再起動・再デプロイ等でSQLiteのデータが消えることがあります。定期的にCSVを書き出してください。またこの試作にはユーザー認証がなく、同じURLにアクセスした人が同じ仮想口座を閲覧・変更できます。URLを第三者に公開せず、実際の資金・API秘密鍵を入力しないでください。個人専用の永続運用には認証と外部DBが必要です。

## Macでローカル実行
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 実装内容
- BTC/ETH/DOGEのJPY価格（日次、CoinGecko）
- 移動平均・モメンタム・ボラティリティによるルールベース売買
- 取引コストを考慮した簡易バックテスト
- SQLiteによるペーパー口座（銘柄ごとに仮想資金1,000円）
- 確定日足をボタンで反映し、シグナルに応じた仮想注文
- CSVエクスポート

## 限界
- 24時間自動監視は未実装。ページを開き更新ボタンを押す必要があります。
- 初回更新は過去の仮想取引を遡及しません。
- 日足の終値を用いた近似約定。実取引所の板、最低注文金額、税金、API障害は再現しません。
- CoinGeckoの無料APIは過去期間・レート制限があり、Demoキーが必要な場合があります。
- 価格取得元のデータが遅延する場合があります。
