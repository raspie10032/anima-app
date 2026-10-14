# NAI token setup / 토큰 설정 / トークン設定

[README](../README.md) · [한국어 생성 가이드](IMAGE_GENERATION_KO.md) · [English](IMAGE_GENERATION_EN.md) · [日本語](IMAGE_GENERATION_JA.md)

**한국어:** 앱 웹 화면에는 토큰 입력칸이 없습니다. 아래 명령을 **앱 서버를 시작할 터미널**에서 실행하고, 숨김 입력 안내가 나오면 토큰만 붙여 넣으세요. `Bearer `는 붙이지 않습니다. 앱 실행 후 **생성 엔진 → NovelAI**에서 설정 상태를 확인합니다.

**English:** There is no browser token field. Enter the token at the hidden terminal prompt below and start the server from that same terminal. Paste the token without a `Bearer ` prefix. In the app choose **Generation engine → NovelAI**.

**日本語:** ブラウザーにトークン入力欄はありません。以下の非表示入力でトークンだけを貼り付け、同じターミナルからサーバーを起動します。`Bearer `は付けません。アプリの生成エンジンで **NovelAI** を選びます。

## Get a token / 토큰 발급 / トークンの取得

On the NovelAI website, open **Settings → Account → Get Persistent API Token** and copy the token. Generating a replacement invalidates the previous token, including its use in other apps. See the [official instructions](https://docs.novelai.net/en/text/usersettings/account/).

NovelAI 사이트에서 **설정 → Account → Get Persistent API Token**으로 발급·복사합니다. 새 토큰을 발급하면 이전 토큰은 무효가 됩니다. 기존 토큰을 사용하는 다른 프로그램도 함께 갱신해야 합니다.

NovelAI の **Settings → Account → Get Persistent API Token** から取得します。再発行すると以前のトークンは無効になります。他のアプリにも同じトークンを設定している場合は更新してください。

## Linux / Bash

Run from the project root after installation. Activate your own environment if it has a different name. The prompt hides input and keeps the token out of the command itself.

```bash
source .venv/bin/activate
read -rsp 'NAI token: ' NAI_ACCESS_TOKEN; printf '\n'
export NAI_ACCESS_TOKEN
python -m anima_app.cli serve --host 127.0.0.1 --port 8768 --open
```

After stopping the server with Ctrl+C, remove the variable from that shell if desired:

```bash
unset NAI_ACCESS_TOKEN
```

## Windows PowerShell

Run from the project root after installation. This works with Windows PowerShell and PowerShell 7. The temporary secure string is converted only to supply the server environment.

```powershell
.\.venv\Scripts\Activate.ps1
$naiSecret = Read-Host 'NAI token' -AsSecureString
$naiPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($naiSecret)
try {
    $env:NAI_ACCESS_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($naiPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($naiPointer)
    $naiSecret.Dispose()
    Remove-Variable naiSecret, naiPointer
}
python -m anima_app.cli serve --host 127.0.0.1 --port 8768 --open
```

If activation is unavailable, use `.\.venv\Scripts\python.exe` for the final command. `Run-AnimaAPP-GUI.cmd` can also be launched **from this same terminal** to inherit the token. Double-clicking it from Explorer does not inherit a different terminal's temporary variable.

After stopping the server:

```powershell
Remove-Item Env:NAI_ACCESS_TOKEN
```

## Check the connection / 설정 확인 / 設定の確認

1. Open the address printed by the server. The examples above use `http://127.0.0.1:8768`.
2. Select NovelAI in the generation-engine selector. The provider status below it should show that the token is configured.
3. For a value-free check, open `/api/nai/status` on that same server. A configured environment produces:

```json
{"configured": true, "source": "environment", "variable": "NAI_ACCESS_TOKEN"}
```

This checks the presence of a nonempty environment value, **not authentication or billing**. A 401/403 during actual generation needs a valid token/account. A protection error is a separate account/operation constraint; see [NovelAI provider behavior](NOVELAI_PROVIDER.md).

토큰을 바꿨는데 적용되지 않으면 실행 중인 앱의 작업이 끝난 뒤 서버를 종료하고, 새 토큰을 설정한 터미널에서 다시 실행하세요. 브라우저 새로고침만으로 서버 환경변수는 바뀌지 않습니다.

トークン変更後は実行中の処理が完了してからサーバーを停止し、新しい値を設定したターミナルで起動し直します。ページの再読み込みだけでは環境変数は更新されません。

## Storage contract

- `NAI_ACCESS_TOKEN` takes precedence over compatibility variable `NAI_API_TOKEN`.
- The app reads the server environment. It does **not** automatically load `.env`, save a token in browser storage, or provide email/password login.
- The commands above are session-scoped; a new terminal/reboot needs configuration again. A service must receive the variable through its own launch configuration.
- Tokens do not belong in prompts, generation JSON, presets, PNG metadata, screenshots or Git. The API rejects credential fields in generation requests.
- For an offline UI trial, use `serve --dry-run-default`; this does not test credentials or generate images.
