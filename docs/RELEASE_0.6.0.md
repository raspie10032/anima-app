# Anima APP v0.6.0 — image workspace and connected generation

Release date: **2026-10-15**. Distribution: **source-checkout beta**.

**[Download anima-app-0.6.0-source.zip](https://github.com/raspie10032/anima-app/releases/download/v0.6.0/anima-app-0.6.0-source.zip)** · [SHA-256 checksum](https://github.com/raspie10032/anima-app/releases/download/v0.6.0/anima-app-0.6.0-source.zip.sha256) · [GitHub release](https://github.com/raspie10032/anima-app/releases/tag/v0.6.0)

## 한국어

**NAI·Anima 이미지 생성부터 유사사례 검색, 작가 조합·프롬프트 재사용까지 한 화면 흐름으로 연결한 버전입니다.**

- **이미지 작업실:** 기준 그림 고정, 크기 조절 갤러리, 유사사례 검색, 작가 조합별 탐색, 두 후보 비교, 즐겨찾기·태그·컬렉션·메모.
- **생성 작업 순서:** NAI → Anima 디테일러, Anima → NAI 디테일러, 순서 변경 가능한 최대 6개 후처리 단계, 단계별 설정과 중간 결과 비교.
- **프롬프트 연결:** 엔진별 가중치와 `artist:` / `@` 변환, 실제 전달 미리보기, 초안 자동 저장, 참고 사례와 정확한 생성 기록 연결. 접두사 없는 작가명은 준비한 로컬 목록과 정확히 일치할 때만 변환합니다.
- **한·영·일 UI:** 작업 중 언어 전환, 선택 언어 저장, 작성 중 프롬프트와 생성 조건 유지.
- **NovelAI 기능:** T2I, Img2Img, 인페인트·Focused, Vibe·Precise, Medium Effort, 최대 22개 저장 캐릭터 슬롯, 선택 WD/PixAI 매칭.
- **저메모리 보정 수정:** 디테일러만 실행할 때 자동 메모리 프로필이 불필요한 업스케일 단계를 추가하지 않습니다.

### 처음 실행하기

1. 위 **`anima-app-0.6.0-source.zip`**을 내려받아 압축을 풉니다.
2. Python 3.10 이상을 준비하고, 압축을 푼 폴더에서 [한국어 생성 가이드](IMAGE_GENERATION_KO.md#2-설치와-실행)의 가상환경·설치 명령을 실행합니다. ZIP에는 Python과 모델 가중치가 포함되지 않습니다.
3. **NAI:** [토큰 설정](NAI_TOKEN_SETUP.md)을 따라 앱을 실행할 터미널에 `NAI_ACCESS_TOKEN`을 입력합니다. 웹 화면에는 토큰 입력칸이 없습니다. **Anima:** 화면의 모델 준비 기능으로 체크포인트·텍스트 인코더·VAE를 준비합니다.
4. 설치한 환경에서 아래 명령으로 실행합니다. Windows의 `Run-AnimaAPP-GUI.cmd`도 해당 Python 환경에서 실행할 수 있습니다.

```bash
python -m anima_app.cli serve --host 127.0.0.1 --port 8768 --open
```

5. 생성 엔진을 고르고 프롬프트·크기·시드를 입력한 뒤 **단계별 전달 미리보기 → 생성하기** 순서로 진행합니다.

**이미지 관리와 CPU 유사 검색은 별도 비전 모델 없이 사용할 수 있습니다.** VRS 검색을 쓰려면 [VRS-INT 인코더 설정](IMAGE_LIBRARY_KO.md#실행-및-선택적-인코더-설정)을 준비합니다. 이미지 라이브러리는 최대 2,000장을 참조하며 원본 폴더의 파일을 옮기지 않습니다. 접두사 없는 작가명의 인식을 원하면 [로컬 작가 목록](GENERATION_WORKSPACE_KO.md)을 준비하세요. 명시적인 `artist:` / `@`는 목록 없이도 변환합니다.

### 기존 설치에서 업데이트

1. 진행 중인 생성·색인이 끝난 뒤 앱을 종료하고 **기존 설치 폴더를 백업**합니다. 라이브러리 DB는 앱이 꺼진 상태에서 복사합니다.
2. ZIP의 내부 앱 폴더를 기존 설치의 **같은 경로**에 풀어 코드와 문서를 갱신합니다. `models/`, `inputs/`, `outputs/`, `.venv/`, 개인 `autocomplete.txt`는 삭제하지 않습니다. 직접 수정한 `wildcards/`는 백업본과 비교해 보존합니다.
3. 기존 가상환경에서 `python -m pip install -e .`을 다시 실행합니다. 디테일러를 사용하면 `python -m pip install -e ".[face-detailer]"`도 적용합니다.
4. 기존 토큰·VRS 환경설정과 같은 호스트·포트로 다시 시작합니다. 브라우저를 새로고침하고 이력·라이브러리·프리셋을 확인합니다.

외부에서 가져온 원본 이미지의 경로는 그대로 유지하세요. 앱 경로나 원본 폴더를 옮기면 기존 라이브러리의 경로 연결이 끊길 수 있습니다. Git 체크아웃을 사용한다면 개인 변경을 보존한 뒤 `git pull --ff-only`로 코드를 갱신합니다.

## English

This release connects **reference image → similar cases → recorded artist combinations → prompt reuse → generation**.

- A full image workspace with a pinned reference, adjustable gallery, pairwise comparison and local annotations.
- Ordered NAI/Anima workflows with up to six post-processing stages and intermediate results.
- Per-provider prompt weights and artist notation, persistent drafts and exact source-record links.
- English, Korean and Japanese UI; expanded NovelAI features and a detail-only low-memory fix.

Download the **source ZIP** above and follow the [first-image guide](IMAGE_GENERATION_EN.md). Install Python 3.10+ and dependencies; prepare local generation models separately. For NovelAI, set `NAI_ACCESS_TOKEN` in the **server's terminal environment** using the [hidden-input instructions](NAI_TOKEN_SETUP.md). There is no browser token field. Launch from the installed environment with the command above.

Image management and CPU similarity search need no vision model. Optional VRS search requires a separately prepared [local VRS-INT encoder](IMAGE_LIBRARY_EN.md#optional-vrs-int-encoder). Imported images are referenced in place, with a 2,000-image capacity. Explicit `artist:` / `@` tags work without an artist catalog; unprefixed artist matching needs a local catalog.

To upgrade, finish active jobs, stop the app and back up the installation. Update code **at the same path**, preserve `models/`, `inputs/`, `outputs/`, the environment and personal autocomplete/wildcards, then reinstall with `python -m pip install -e .` (or `'.[face-detailer]'` for detailers). Keep imported image paths and the browser host/port unchanged. Restart with the existing token/VRS environment, refresh the browser and check history, library and presets.

## 日本語

**参照画像 → 類似事例 → 記録された作家の組み合わせ → プロンプト再利用 → 生成**をつなぐバージョンです。

- 参照画像を固定する画像ワークスペース、可変サイズのギャラリー、候補比較、タグ・お気に入り。
- NAI → Anima / Anima → NAI のディテーラー、最大6段階の後処理、途中結果の比較。
- エンジン別の重み・作家表記変換、下書き保存、参照元の生成記録へのリンク。
- 日本語・韓国語・英語のUI、NovelAI機能の拡充、低メモリ設定でのディテーラー動作修正。

上の **source ZIP** を展開し、[画像生成ガイド](IMAGE_GENERATION_JA.md)に従って Python 3.10 以降と依存関係を用意します。ローカル生成のモデルは別途準備してください。NAIトークンはブラウザーではなく、[起動するターミナルに設定](NAI_TOKEN_SETUP.md)します。

画像管理とCPU類似検索にはビジョンモデルは不要です。VRS検索には別途ローカルのVRS-INTエンコーダーが必要です。画像は元の場所を参照し、最大2,000枚を登録できます。明示した `artist:` / `@` は作家リストなしでも変換できます。

更新時は処理の完了後にアプリを停止してバックアップし、**同じインストール先**のコードを更新します。モデル・入力・出力・個人設定を保持し、`python -m pip install -e .` で依存関係を更新してください。元画像のパスとブラウザーのホスト・ポートを維持し、以前のトークン・VRS環境設定で再起動します。

## Verification

The release checks cover CPU-safe regression tests, Python lint, browser JavaScript syntax, vendored runtime integrity, wheel contents and an extracted source archive. The source ZIP is built from a **clean committed checkout** with `scripts/source_archive.py --require-clean`; its fixed ZIP metadata permits byte-for-byte reproduction. The uploaded `.sha256` identifies that exact ZIP. [Artifact manifest](RELEASE_MANIFEST.md).

The [main integration record](MAIN_UPDATE_2026-10-14.md) retains the earlier 1,122-test baseline, 46 browser scenarios and limited live NAI/Anima examples. Release packaging does not make new paid generation requests; Windows launcher checks do not establish Windows GPU execution.

The ZIP includes app source, browser resources, the vendored local runtime, launcher, guides and notices. Python, third-party installed dependencies, model weights, local artist catalogs, image collections, embeddings and tokens are prepared locally. The wheel is a package-verification artifact, not the full generation distribution. See [licenses and references](REFERENCES.md).
