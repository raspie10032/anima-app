# 배럭 / Barracks / バラック

[README](../README.md) · [NAI token setup](NAI_TOKEN_SETUP.md) · [App reference](APP_REFERENCE.md)

## 한국어

**배럭은 여러 NAI 계정으로 텍스트→이미지(t2i) 단독 생성 작업을 나누는 기능입니다.** 메인 생성 화면의 프롬프트·캐릭터·모델·크기·샘플러·스텝·CFG·Opus 보호 설정을 그대로 사용합니다. 작가 표기와 가중치 변환도 일반 NAI 생성과 동일합니다.

1. 메인 화면에서 **생성 엔진 → NovelAI**, **텍스트→이미지**를 선택하고 프롬프트와 크기를 입력합니다. 작업 순서는 **생성만**으로 설정합니다.
2. 상단 **배럭**을 엽니다.
3. **계정 이름**과 **NAI 액세스 토큰**을 입력하고 **계정 추가**를 누릅니다. 이미 연결한 토큰은 **현재 NAI 토큰 추가**로 등록할 수 있습니다. 서로 다른 계정의 토큰을 사용하세요. 최대 8개를 등록할 수 있으며 같은 토큰의 중복 등록은 막습니다.
4. 사용할 계정의 체크박스를 켜고 **생성 장수**를 1~100장으로 정합니다. 이 수치는 전체 장수입니다. 계정별 장수가 아닙니다.
5. **시드 증가**, **매번 무작위**, **같은 시드** 중 하나를 고릅니다. 메인 화면의 시드가 비어 있으면 시작 시드를 무작위로 정합니다. 시드 증가는 그 값부터 한 장마다 1씩 늘립니다.
6. **현재 생성 조건**을 확인하고 **배럭 시작**을 누릅니다. 계정당 한 장씩 생성하고, 완료한 계정이 다음 대기 이미지를 맡습니다.
7. 결과 카드에서 이미지·시드·계정 이름을 확인합니다. 이미지는 일반 생성 이력에도 저장됩니다. 배럭 창을 닫아도 실행 PC에서 앱이 켜져 있으면 생성은 계속됩니다. 다시 배럭을 열면 진행 상황을 확인할 수 있습니다.

**배럭 중지**는 다음 요청을 중지합니다. 이미 NAI에 전송한 요청의 결과는 받아서 저장합니다. 인증·결제·통신 오류가 발생한 계정은 해당 배치에서 멈추며, 실패한 이미지를 다른 계정으로 재전송하지 않습니다. 429는 기존 NAI 요청 처리와 같이 대기 후 한 번만 재시도하고, 계속 제한되면 그 계정을 멈춥니다. 남아 있는 계정은 아직 전송하지 않은 이미지를 계속 처리합니다.

**지원 범위:** NAI t2i 한 단계입니다. Img2Img·인페인트·디테일러·업스케일·후속 작업 순서·Vibe Transfer·Precise Reference가 있으면 시작을 차단합니다. 계정 정보는 배럭이 끝난 후 수정하거나 삭제할 수 있습니다.

토큰은 기본적으로 실행 PC의 휘발성 메모리에만 보관하며 앱 종료 시 사라집니다. 계정 추가 전 **이 PC에 저장 (다음 실행에도 사용)**을 선택하거나, 등록된 계정 옆의 **이 PC에 저장**을 누르면 운영체제 자격증명 저장소에 보관하고 다음 실행에 복원합니다. **저장 해제**는 현재 연결을 유지하면서 저장본을 지우고, **삭제**는 현재 계정과 저장본을 함께 지웁니다. 브라우저 저장소나 생성 기록에는 토큰을 저장하지 않습니다. 생성 기록에는 계정 이름·배치 ID·작업 ID만 남습니다. **드라이런**이 켜져 있으면 실제 이미지 요청 없이 검증합니다.

## English

**Barracks distributes standalone NAI text-to-image jobs across multiple accounts.** It uses the main screen's prompt, character slots, model, size, sampler, steps, CFG and Opus protection, including the existing artist/weight conversion.

1. Select **NovelAI**, **Text to image** and **Generate only** on the main screen. Enter the prompt and image settings.
2. Open **Barracks** in the top toolbar.
3. Add an account name and NAI token, or use **Add current NAI token**. Register up to 8 different account tokens; duplicate tokens are rejected.
4. Check the accounts to use. Set **Image count** to 1–100 images **in total**, then choose incrementing, random or fixed seeds. A blank starting seed is randomized once for fixed/incrementing modes.
5. Review the current settings and start. Each account handles one image at a time, taking the next waiting image after completion.
6. View images, seeds and account names in the result cards or generation history. Closing the dialog leaves the batch running on the PC running the app; reopen it to see progress.

Stop prevents further submissions and retains results already in flight. Failed or uncertain images are never reassigned to another account. A failing account pauses for the batch; other accounts continue with unsent images. HTTP 429 receives the existing single bounded retry, then pauses that account if still limited.

Only single-stage NAI t2i is accepted: image inputs, inpainting, detailers, upscaling, workflows, Vibe Transfer and Precise Reference are rejected. Account edits are available after the batch ends. Tokens default to volatile memory on the PC running the app and disappear at app exit. Select **Save on this PC (use after restart)** when adding an account, or **Save on this PC** beside an existing account, to restore it from the OS credential store on next launch. **Forget saved token** keeps the current connection; **Delete** also removes the current account. Records contain account names and job IDs, never tokens. Dry run validates without requesting images.

## 日本語

**バラックは、複数のNAIアカウントに単独のテキスト→画像生成を分配する機能です。** メイン画面のプロンプト・キャラクター・モデル・画像サイズ・サンプラー・ステップ・CFG・Opus保護設定を使用し、作家表記と重みも通常のNAI生成と同様に変換します。

1. メイン画面で **NovelAI → テキスト→画像 → 生成のみ**を選び、プロンプトと画像設定を入力します。
2. 上部の**バラック**を開きます。
3. アカウント名とトークンを追加します。接続済みのトークンも追加できます。最大8アカウント、同一トークンの重複登録は不可です。
4. 使用するアカウントを選択し、**合計1～100枚**とシード方式（連番・毎回ランダム・固定）を指定します。開始シードが空欄の場合はランダムな値から始めます。
5. 現在の設定を確認して開始します。アカウントごとに1枚ずつ生成し、完了したアカウントが次の待機画像を担当します。
6. 結果カードと生成履歴で、画像・シード・アカウント名を確認します。画面を閉じても実行PCでアプリの処理は続き、再度開くと進捗を確認できます。

停止すると次の送信を止め、送信済みの結果は受け取って保存します。失敗・結果不明の画像を別アカウントに再送しません。エラーのアカウントはそのバッチで停止し、他のアカウントは未送信の画像を続行します。429は待機後に1回だけ再試行し、制限が続く場合は停止します。

対応範囲はNAI t2iの1段階です。Img2Img・インペイント・ディテーラー・アップスケール・後続処理・Vibe Transfer・Precise Referenceがあると開始できません。アカウントの変更はバッチ終了後に行います。トークンは通常実行PCの揮発性メモリだけに保持し、アプリ終了時に消えます。**このPCに保存（次回起動時も使用）**を選ぶとOSの資格情報ストアに保存し、次回起動時に復元します。登録済みアカウントの「このPCに保存」でも保存できます。「保存を解除」は現在の接続を維持し、「削除」はアカウントと保存済みトークンを削除します。記録にはアカウント名とジョブIDを保存し、トークンは保存しません。ドライランでは画像を生成せず検証します。

## API and verification

`GET /api/barracks/status` returns account identities and the most recent batch. `POST /api/barracks/accounts` adds `{name, token, persist:false}` or `{name, use_current:true, persist:false}`. Opt into OS credential storage with `persist:true`. `POST /api/barracks/accounts/storage` accepts `{id,persist}` to save or forget an existing account. `POST /api/barracks/accounts/remove` accepts `{id}` and removes both the active account and its saved token. `POST /api/barracks/start` accepts `{request, account_ids, count, seed_mode}`; `seed_mode` is `increment`, `random` or `fixed`. `POST /api/barracks/cancel` stops future submissions. See the running app's `/api/openapi.json` for limits. One batch can run at a time per server.

Credentials are bound to worker context, with a request gate per token shared by ordinary generation and Barracks. Each job has a unique output suffix so parallel fixed-seed jobs preserve separate results. Completed images and manifests survive restart; the in-memory batch does not automatically resume.

Run focused offline checks with:

```bash
python -m pytest -q tests/test_barracks.py tests/test_novelai_eligibility.py tests/test_novelai_integration.py
PYTHONPATH=src python scripts/browser_barracks_smoke.py
```

Automated checks use mock NAI responses and isolated output directories. They verify concurrency, request scope, cancellation, token isolation, output preservation and browser behavior; they do not measure live multi-account throughput.
