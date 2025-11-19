# CodePipeline Trigger Template (S3 + GitHub)

## 🎯 What this template does
S3アップロード or GitHub push をトリガに、
CodePipeline + CodeBuild を動かし、結果を Slack に通知する。
→ 「手動でビルド押す文化」を潰す

## 🏗 Architecture
<!-- 図を添付 -->

## Features
- S3配置 or GitHub push のどちらからでもパイプライン起動
- CodeBuildの成功/失敗をSlackに即通知
- Webhook URLはSSM Parameter Storeで安全に管理

## 🚀 Use Cases
- 手動デプロイをやめて、最低限のCI/CDを入れたい小規模チーム
- S3アップロードをきっかけにバッチ処理を自動化したいケース
- GitHubへのpushをトリガに検証用環境を毎回ビルドしたい場合

## Deploy
### 前提
- AWS CLI / SAM CLI インストール済み
- Slack Webhook URL を SSM Parameter Store に登録済み

### 手順
1. Clone this repository  
2. (Optional) Create an SSM Parameter for Slack Webhook  
3. Build the SAM template  
```bash
sam build
```
4. Deploy
```bash
sam deploy --guided
```

### Configuration
| パラメーター | 説明 |
|-------------|------|
| GitHubOwner | GitHub ユーザー / Org |
| GitHubRepo | リポジトリ名 |
| GitHubBranch | 監視するブランチ |
| ArtifactBucketName | CodePipeline 用 Artifact バケット名 |
| UploadBucketName | (任意) S3トリガ用バケット名 |

## Slack Notification
CodeBuild/CodePipeline の結果を EventBridge 経由で Lambda へ

メッセージ例：
```
text
コードをコピーする
[CodeBuild] project: my-build
Status: FAILED
Link: https://console.aws.amazon.com/codesuite/codebuild/...
```

## 💰 Cost (費用目安)
CodePipeline: 実行回数ベース
CodeBuild: ビルド時間ベース
Lambda/Events/S3: 微量
（ざっくり見積を1セクション書く）

## ❗ Known Pitfalls
### Limitations
GitHub Enterprise / self-hosted runner は未対応
高頻度トリガー（毎分クラス）には向かない
Deploy ステージはサンプルのみ（本番用には要カスタマイズ）

## 📚 FAQ


## 📝 License
本プロジェクトは [MIT License](LICENSE) のもとで公開されています。  
Created by amomo0220
