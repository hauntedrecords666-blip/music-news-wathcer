# GitHub Personal Access Token (PAT) の取り扱い手順

以下は、誤って公開してしまった PAT を取り消し（revoke）し、新しいトークンを作成するための安全な手順です。Mac（ブラウザ）での操作を想定しています。

1) まず既存トークンを無効化（revoke）する

 - ブラウザで次のページを開いてください:
   https://github.com/settings/tokens
 - ログインが必要ならログインします。
 - 表示されているトークン一覧から、公開してしまったトークン（該当のトークン名/作成日時を確認）を探し、右端の「Delete」または「Revoke」をクリックして無効化します。
 - 無効化したらすぐに再利用できなくなります。

2) 新しいトークンを作成する（推奨: Fine-grained token）

 - 同じページ（https://github.com/settings/tokens）で「Generate new token」→「Generate new fine-grained token」を選択します。
 - "Repository access" の欄で、必要なら対象リポジトリのみを選択し、権限は最小限（Read & Write）にします。
 - Expiration（有効期限）は短め（例: 30日〜90日）を推奨します。
 - 作成後、表示されるトークン文字列を必ずコピーして安全な場所に保管してください（この画面でしか表示されません）。

3) ローカルでの安全な使用例

 - 一時的にワンライナーで push する（履歴に残るので注意）:
   git push https://<USERNAME>:<TOKEN>@github.com/<OWNER>/<REPO>.git main
 - より安全にするには gh CLI を使う:
   - Homebrew で gh をインストール: `brew install gh`
   - gh でログイン: `gh auth login` （ブラウザ認証を推奨）
   - その後: `git push -u origin main`
 - macOS のキーチェーンや Git Credential Manager を使ってトークンを保存すると、コマンド履歴に残さずに済みます。

4) トークンを公開してしまった場合の注意

 - 速やかに該当トークンを revoke（無効化）してください。
 - リポジトリのアクセスログや不審なコミットがないか確認してください。
 - 今後は PAT を直接チャットや公開ファイルに貼らないでください。代わりに環境変数、シークレットマネージャ、gh CLI を利用してください。

参考: あなたが操作するスクリプトファイル
 - 実装ファイル: [`music-news-wathcer/larc_news_watcher.py:1`](music-news-wathcer/larc_news_watcher.py:1)
 - ルートコピー: [`larc_news_watcher.py:1`](larc_news_watcher.py:1)

上の手順を実行したら「無効化した」「新しいトークンを作成した」など教えてください。次に push の具体的なコマンドや gh CLI の手順を案内します。

