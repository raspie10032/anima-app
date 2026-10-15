# NAI token setup / 토큰 설정 / トークン設定

[README](../README.md) · [한국어 생성 가이드](IMAGE_GENERATION_KO.md) · [English](IMAGE_GENERATION_EN.md) · [日本語](IMAGE_GENERATION_JA.md)

**한국어:** v0.6.1은 **연결 · 준비 → NAI로 생성 → NAI 액세스 토큰 → 토큰 적용**에서 입력합니다. 입력 후 내용은 지워지고 기본은 실행 PC의 휘발성 메모리에만 보관하며 앱 종료 시 사라집니다. **이 PC에 저장 (다음 실행에도 사용)**을 선택하면 운영체제 자격증명 저장소에 보관하고 다음 실행에 복원합니다. **토큰 지우기**로 해제합니다. 저장하지 않은 토큰은 앱을 재시작하면 다시 입력합니다. 아래 터미널 방식도 사용할 수 있습니다.

**English:** In v0.6.1 use **Connect & prepare → Generate with NAI → NAI access token → Apply token**. The field is cleared after submission; by default the token stays only in volatile memory on the PC running the app until exit. Select **Save on this PC (use after restart)** to restore it at the next launch from the operating system credential store. Use **Clear token** to disconnect, and enter unsaved tokens again after restarting the app. The terminal method below is also available.

**日本語:** v0.6.1では **接続・準備 → NAIで生成 → NAIアクセストークン → トークンを適用** から入力します。送信後は入力欄を消去し、通常は実行PCの揮発性メモリだけに保持し、終了時に消えます。**このPCに保存（次回起動時も使用）**を選ぶとOSの資格情報ストアに保存し、次回起動時に復元します。以下のターミナル手順も使用できます。

## 다음 실행에도 유지 / Keep across launches / 次回起動時も使用

- **한국어:** 토큰 입력 후 **이 PC에 저장 (다음 실행에도 사용) → 토큰 적용**. 이미 연결되어 있으면 입력칸을 비워 둔 채 같은 선택을 하면 현재 토큰을 저장합니다. 체크를 해제하고 **토큰 적용**을 누르면 현재 연결은 유지하면서 저장본만 지웁니다. **토큰 지우기**는 연결과 저장본을 함께 지웁니다. 배럭 계정의 저장·삭제는 배럭에서 별도로 관리합니다.
- **English:** Check **Save on this PC (use after restart)** before **Apply token**. Leave the token field empty to save the currently connected token. Uncheck and apply to delete the saved copy while keeping the current connection. **Clear token** removes both. Manage saved Barracks accounts separately in Barracks.
- **日本語:** **このPCに保存（次回起動時も使用）→ トークンを適用**を選びます。接続済みなら入力欄を空にして現在のトークンを保存できます。チェックを外して適用すると現在の接続を保ったまま保存を解除します。**トークンを消去**は接続と保存済みトークンを両方削除します。バラックの保存は別に管理します。

Storage uses the current OS user's credential store: Windows Credential Manager, macOS Keychain, or Linux Secret Service (including KDE's compatible service). The OS may ask to unlock it. If unavailable, saving reports an error; no plaintext fallback is used. Install/update app dependencies with `python -m pip install -e .` when upgrading an existing checkout. See [keyring's supported OS backends](https://keyring.readthedocs.io/en/latest/).

The metadata-only index is `outputs/credentials/index.json`; token values are in the OS credential store, scoped to this installation path. Moving the app to a different folder or OS account requires registering tokens again. To remove saved credentials, use the app controls before deleting or moving the app folder. Tokens configured in the launch environment take precedence over the saved default token; neither source is automatically saved without choosing the option.

## Get a token / 토큰 발급 / トークンの取得

여러 계정은 상단 **배럭 → 계정 이름·NAI 액세스 토큰 → 계정 추가**에 등록합니다. 배럭은 NAI t2i 단독 생성 전용이며, **현재 NAI 토큰 추가**로 위에서 설정한 계정을 가져올 수 있습니다. See [배럭 / Barracks / バラック](BARRACKS.md) for multi-account setup and generation.

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

토큰을 바꾸려면 실행 중인 작업이 끝난 뒤 **연결 · 준비**에서 새 값을 적용하세요. 터미널 환경변수로 바꾸는 경우에는 앱을 종료하고 새 값을 설정한 터미널에서 다시 실행합니다. 브라우저 새로고침만으로 실행 PC의 프로세스 환경변수는 바뀌지 않습니다.

トークンを変更するには、実行中の処理が完了してから**接続・準備**で新しい値を適用します。ターミナルの環境変数を変更する場合はアプリを終了し、新しい値を設定したターミナルで起動し直します。ページの再読み込みだけでは実行PCのプロセス環境変数は更新されません。

## Storage contract

- `NAI_ACCESS_TOKEN` takes precedence over compatibility variable `NAI_API_TOKEN`.
- The app reads the launch environment or explicitly saved local credentials. It does **not** automatically load `.env`, save a token in browser storage, or provide email/password login.
- The commands above are session-scoped; a new terminal/reboot needs configuration again. An app started with saved credentials restores them automatically in the same OS account and installation folder.
- Tokens do not belong in prompts, generation JSON, presets, PNG metadata, screenshots or Git. The API rejects credential fields in generation requests.
- For an offline UI trial, use `serve --dry-run-default`; this does not test credentials or generate images.
