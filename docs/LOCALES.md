# App language / 앱 언어 / アプリの言語

## 한국어

상단 **앱 언어**에서 **English / 한국어 / 日本語**를 선택합니다. 이미지 작업실 상단에서도 같은 설정을 바꿀 수 있습니다. 새로고침 없이 화면 문구를 바꾸며 열린 작업실의 선택 이미지·비교 후보·작성 초안·단계 설정은 유지합니다.

- 첫 방문에는 브라우저의 지원 언어를 사용하고, 지원하는 언어가 없으면 영어로 시작합니다.
- 선택한 언어는 같은 브라우저·앱 주소의 `anima.locale`에 저장됩니다. 기존 `anima.nai.language` 설정도 처음 읽을 때 반영합니다. 다른 탭에도 변경을 전달합니다.
- 브라우저 저장소가 차단돼도 현재 화면에서는 전환할 수 있고, 저장할 수 없다는 안내를 표시합니다.
- 메인 생성 화면, 작업 순서, 이미지 작업실·비교·프롬프트 편집, NAI 입력·사용 안내·구조화된 오류 설명이 대상입니다.
- 프롬프트·작가명·이미지 파일명·모델 식별자·수집된 메타데이터·기록 원문은 번역하지 않습니다. 서버와 외부 도구의 기술 오류 상세·변환 경고는 원문을 유지할 수 있습니다. 언어는 생성 요청·프리셋·PNG의 생성 조건에 넣지 않습니다. 기본 파일 선택 버튼·파일 대화상자 같은 브라우저 자체 UI는 브라우저 언어를 따릅니다.

## English

Choose **English / 한국어 / 日本語** in **App language** at the top of the main screen or image workspace. Changes apply immediately without resetting selected images, comparison candidates, edited drafts or workflow settings.

The first visit follows a supported browser language, falling back to English. The selection is saved under `anima.locale` for the current browser and app origin; an existing `anima.nai.language` preference is honored on initial load. Other tabs update automatically. If browser storage is blocked, switching still works for the current session and a notice explains that it cannot be saved.

The setting covers generation controls, ordered workflows, library browsing/comparison/composition, NAI guidance and structured error explanations. Prompts, artist tags, file names, model identifiers, collected metadata and original records remain unchanged. Raw server/tool diagnostics and conversion warnings may retain their source language. Locale is not part of generation requests, presets or PNG generation settings. Native browser UI, such as file pickers, follows the browser language.

## 日本語

メイン画面または画像ワークスペース上部の **アプリの言語** から **English / 한국어 / 日本語** を選びます。再読み込みなしで表示が変わり、選択中の画像・比較候補・編集した下書き・作業段階の設定は保持されます。

初回はブラウザーの対応言語を使用し、該当する言語がなければ英語になります。設定は同じブラウザーとアプリのアドレスの `anima.locale` に保存され、既存の `anima.nai.language` 設定も初回読み込み時に引き継ぎます。別タブにも変更が反映されます。保存領域が使用できない場合も、その画面では切り替え可能で、保存できない旨を表示します。

生成画面・作業順序・画像の探索と比較・プロンプト編集・NAIの入力と使い方・構造化されたエラー説明に対応しています。プロンプト・作家タグ・ファイル名・モデル識別子・取得したメタデータ・記録原文は翻訳しません。サーバーや外部ツールの技術的な詳細・変換警告は原文のままの場合があります。表示言語は生成リクエスト・プリセット・PNGの生成条件には含まれません。ファイル選択ボタンやダイアログなど、ブラウザー標準のUIはブラウザーの言語に従います。

## Development and verification

`src/anima_app/static/ui-messages.json` contains source UI messages with English and Japanese translations; Korean uses the source key. `i18n.js` owns language selection, storage and explicit text/attribute bindings. `nai-i18n.js` retains existing NAI message IDs through that shared layer. `nai-error-messages.json` remains the structured three-language error catalog.

Only source-authored HTML is scanned at initial load. Runtime UI helpers register individual text nodes and attributes; they do not scan prompts, records, user metadata or arbitrary new DOM content. Text is assigned with DOM text properties rather than HTML. A locale switch updates existing nodes and does not rebuild forms or trigger generation. When a later asynchronous response replaces a bound value, the obsolete binding is discarded. Detached nodes are pruned.

When adding interface text, add its English and Japanese entries, use `AppI18n.msg` (or the `tr` helper), and bind with `setText` / `setProperty` / `setAttribute`. Keep interpolated user data separate. Use deferred text callbacks when concatenating several messages so existing cards also update on a locale change.

```bash
python -m pytest tests/test_novelai_language.py tests/test_release.py -q
PYTHONPATH=src python scripts/browser_locale_smoke.py
PYTHONPATH=src python scripts/browser_nai_language_smoke.py
python scripts/package_dry_run.py
```

Browser acceptance uses disposable synthetic images and headless Chromium, blocks generation/external requests in the app-wide locale test, and closes browser/server resources. It checks all three languages, byte-identical serialized requests across switches, preservation of original prompts and drafts, persistence, legacy preference import, cross-tab updates, blocked storage and widths 1920/1280/900/390. Existing generation, library and authoring smoke tests explicitly select Korean; they continue to check their original behavior independently of the test machine's language.
