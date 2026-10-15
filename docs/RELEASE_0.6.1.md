# Anima APP v0.6.1 — easier setup, embedded VRS and Barracks

Release date: **2026-10-15**. Distribution: **source-checkout beta**.

**[Download anima-app-0.6.1-source.zip](https://github.com/raspie10032/anima-app/releases/download/v0.6.1/anima-app-0.6.1-source.zip)** · [SHA-256 checksum](https://github.com/raspie10032/anima-app/releases/download/v0.6.1/anima-app-0.6.1-source.zip.sha256) · [GitHub release](https://github.com/raspie10032/anima-app/releases/tag/v0.6.1)

## 한국어

**처음 설정하는 과정을 한곳으로 모으고, 이미지 한 장에서 유사사례·작가 조합·프롬프트를 찾는 기능을 앱에 내장했습니다. 여러 NAI 계정으로 단독 T2I를 나누어 생성하는 배럭도 추가했습니다.**

- **연결 · 준비:** NAI 토큰 입력, Anima 모델 준비, 이미지 인코더 준비를 한 화면에서 진행합니다. 필요 모델과 레퍼런스 탭에서 기능별 파일·준비 상태·원본 링크를 확인합니다. 한·영·일을 지원합니다.
- **기본/고급 화면:** 프롬프트와 이미지 크기를 중심으로 시작하고, 샘플러·스텝·CFG 등은 고급 설정에서 조정합니다. 화면 전환으로 작성한 값이 바뀌지 않습니다.
- **NAI 토큰 저장:** 기본은 **실행 PC의 휘발성 메모리**이며 종료하면 사라집니다. **이 PC에 저장**을 선택한 토큰만 운영체제 자격증명 저장소에 보관하고 다음 실행에 복원합니다. 일반 NAI 토큰과 배럭 계정 모두 지원합니다.
- **배럭:** 최대 8개 NAI 계정으로 총 1~100장의 **T2I 단독 생성**을 나눕니다. 시드 증가·무작위·고정, 계정별 진행 상황, 중지를 지원합니다. Img2Img·참조 이미지·디테일러·업스케일 등의 후속 단계는 배럭 범위에 포함하지 않습니다.
- **VRS/SWEGCA 내장:** 이미지 인코더 코드와 SWEGCA Python 근거 누적·판정 코어를 앱에 포함했습니다. 별도 저장소 경로를 연결할 필요가 없습니다. 비전 가중치는 앱에서 별도로 준비합니다.
- **캡션 없는 이미지:** 메타데이터가 없거나 일부 손상돼도 픽셀에서 특징을 추출합니다. 읽을 수 있는 생성 정보는 정제해 연결하고, 동일 픽셀의 여러 생성 기록과 출처도 보존합니다.
- **검색과 색인 개선:** 인코더와 검색 행렬을 재사용하고 색인 결과를 나누어 저장합니다. 준비된 이미지부터 검색하며 취소와 실패를 구분합니다. 명시적 사용자 평가를 제한된 개인 정렬에 반영하고 다양한 사례를 섞어 볼 수 있습니다.
- **VRS 켜기·끄기 / 장수 제한 해제:** VRS를 꺼도 기존 이미지·색인·평가는 보존하고 기본 검색과 보관은 계속 쓸 수 있습니다. 라이브러리에는 고정 장수 제한이 없습니다. 실제 처리량은 PC 자원과 저장 공간에 따라 달라집니다.

### 처음 실행하기

1. 위의 **source ZIP**을 내려받아 압축을 풉니다. Python 3.10 이상을 준비합니다.
2. [한국어 생성 가이드](IMAGE_GENERATION_KO.md#2-설치와-실행)에 따라 가상환경을 만들고 `python -m pip install -e .`을 실행합니다. 디테일러를 쓰면 `python -m pip install -e ".[face-detailer]"`도 실행합니다.
3. 설치한 환경에서 앱을 시작합니다. Windows는 같은 환경에서 `Run-AnimaAPP-GUI.cmd`도 사용할 수 있습니다.

```bash
python -m anima_app.cli serve --host 127.0.0.1 --port 8768 --open
```

4. **연결 · 준비 → NAI로 생성 → NAI 액세스 토큰 → 토큰 적용**에서 NAI를 연결합니다. NAI만 사용하면 로컬 생성 모델은 필요 없습니다. 토큰 발급·선택 저장은 [토큰 안내](NAI_TOKEN_SETUP.md)를 참고하세요.
5. 로컬 생성은 **Anima로 생성 · 보정**에서 모델을 준비합니다. VRS는 **이미지 인코더 준비 → 이미지 작업실에서 가져오기 → 등록 이미지 색인** 순서입니다. VRS 인코딩에는 현재 CUDA GPU가 필요하며 약 320 MiB의 비전 가중치와 실행 패키지를 준비합니다. 보관과 기본 CPU 유사 검색에는 비전 모델이 필요 없습니다.

[첫 설정 · 필요 모델 · VRS 스위치](../SETUP.md) · [이미지 관리](IMAGE_LIBRARY_KO.md) · [배럭 사용법](BARRACKS.md) · [레퍼런스](REFERENCES.md)

### 기존 설치에서 업데이트

1. 진행 중인 생성·색인이 끝나면 앱을 종료하고 설치 폴더를 백업합니다. 라이브러리 DB는 앱이 꺼진 상태에서 복사합니다.
2. ZIP 내부의 앱 파일을 기존 설치의 **같은 경로**에 풀어 코드와 문서를 갱신합니다. `models/`, `inputs/`, `outputs/`, `.venv/`, 개인 `autocomplete.txt`와 수정한 `wildcards/`를 보존합니다.
3. 기존 가상환경에서 `python -m pip install -e .`을 다시 실행합니다. 이 버전은 `keyring`과 갱신된 `transformers` 의존성을 포함합니다. 디테일러 사용 시 해당 선택 패키지도 갱신합니다.
4. 같은 호스트·포트로 시작하고 새로고침합니다. 저장을 선택하지 않은 토큰은 다시 입력합니다. **연결 · 준비**에서 모델·VRS 상태를 확인하고 필요하면 인코더 준비와 색인을 실행합니다.

가져온 원본 이미지 폴더의 경로를 유지하세요. 저장한 토큰은 OS 사용자와 앱 설치 경로에 연결되므로 설치 경로를 바꾸면 다시 입력·저장해야 합니다. VRS는 같은 인코더 계약의 색인만 재사용하며 다른 계약의 벡터를 섞지 않습니다. Git 설치는 개인 변경을 보존한 뒤 `git pull --ff-only`로 갱신합니다.

## English

**v0.6.1 brings setup, embedded image retrieval and standalone multi-account NAI generation into the app.**

- **Connect & prepare** combines token entry, model preparation, required-model information, references and a persistent VRS switch. Basic/advanced views preserve entered settings.
- Tokens default to **volatile memory on the PC running the app**. Explicit **Save on this PC** uses the OS credential store and restores saved default/Barracks credentials after restart.
- **Barracks** distributes 1–100 standalone NAI T2I images across up to eight accounts, with seed modes, per-account progress and cancellation. Image inputs, references and post-processing are excluded from this mode.
- VRS encoder code and the SWEGCA Python evidence accumulator are bundled. Caption-free or partially malformed metadata no longer blocks pixel-based indexing. Duplicate pixels retain their linked source records.
- Cached encoder/matrix reuse, progressive indexing, explicit personal ordering and diverse results improve retrieval usability. VRS can be disabled without deleting data. The library has no fixed image-count cap; practical capacity depends on available resources.

Download the **source ZIP**, install Python 3.10+ and dependencies, then launch with the command above. Use [Connect & prepare](../SETUP.md) to apply an NAI token or prepare local Anima models. VRS encoding currently requires CUDA and a separately prepared vision model of about 320 MiB. Storage and basic CPU similarity search work without it. See the [generation walkthrough](IMAGE_GENERATION_EN.md), [image-library guide](IMAGE_LIBRARY_EN.md) and [Barracks guide](BARRACKS.md).

To upgrade, finish jobs, stop the app and back up the installation. Update code **at the same path**, keep models, inputs, outputs, the environment and personal files, then reinstall dependencies with `python -m pip install -e .` (or `'.[face-detailer]'`). Keep imported image paths and the browser host/port stable. Saved credentials are tied to the OS user and installation path; unsaved tokens need to be entered again. Check VRS readiness and index with the active encoder contract.

## 日本語

**初期設定、内蔵VRS検索、複数NAIアカウントの単独T2I生成をまとめたバージョンです。**

- **接続・準備**でトークン入力、モデル準備、必要モデル、参照元、VRSのオン・オフを管理します。基本・詳細表示を切り替えても入力値を保持します。
- トークンは通常 **実行PCの揮発性メモリ**だけに保持します。**このPCに保存**を選んだ場合のみOSの資格情報ストアに保存し、次回起動時に復元します。
- **バラック**では最大8アカウントで合計1～100枚のNAI T2I単独生成を分担します。シード設定、進捗確認、停止に対応します。画像入力、参照画像、ディテーラーなどの後処理はこのモードの対象外です。
- VRSエンコーダーとSWEGCAのPython根拠判定コアを内蔵しました。キャプションのない画像や一部壊れたメタデータも処理し、同一画像に結び付く生成記録を保持します。
- エンコーダー再利用と段階的な索引保存、明示的な評価に基づく個人用の並び順を追加しました。VRSをオフにしても画像・索引・評価は残ります。ライブラリーの固定枚数制限を撤廃しました。

**source ZIP**を展開し、Python 3.10以降と依存関係を準備して上のコマンドで起動します。[画像生成ガイド](IMAGE_GENERATION_JA.md)と[初期設定](../SETUP.md)に従って、NAIトークンまたはAnimaモデルを準備してください。VRSには現在CUDA GPUと約320 MiBのビジョン重みが必要です。画像管理と基本CPU類似検索には不要です。

更新時は処理完了後に停止・バックアップし、**同じインストール先**のコードを更新します。モデル、入力、出力、環境、個人ファイルを保持し、`python -m pip install -e .`で依存関係を更新します。元画像のパスとホスト・ポートを維持してください。保存済みトークンはOSユーザーとインストール先に紐付きます。未保存のトークンは再入力します。

## Verification

Release checks cover the full CPU-safe regression suite, Python lint, JavaScript syntax, vendored-code integrity, isolated wheel install and source ZIP extraction. Browser checks cover setup, credentials, Barracks, library, generation, authoring and locales. The final public verification receipt records counts, source commit, artifact hashes and remote CI links.

The development checks additionally exercised local CUDA image generation and VRS retrieval. Automated Barracks and credential browser checks use mocked NAI transport and an isolated credential backend; they do not establish live multi-account throughput or every operating system's credential-store behavior. Packaging makes no paid NAI generation requests. Windows launcher CI checks launcher behavior, not Windows GPU execution.

The embedded SWEGCA component is the Python evidence accumulator, not the entire SWEGCA-bit C++ graph engine. Search scores describe visual neighbors; recorded artist tags are metadata, not an attribution inferred from an image. [Embedded retrieval contract](EMBEDDED_VRS_CONTRACT.md).

The source ZIP is built from a **clean committed checkout** using `scripts/source_archive.py --require-clean`. It includes app source, the vendored local runtime, browser assets, launcher, tests, guides and license notices. Python, installed dependencies, model weights, private image collections, embeddings, search/evaluation records and credentials are prepared locally and are not bundled. The wheel remains a verification artifact; use the source ZIP for local generation. [Artifact manifest](RELEASE_MANIFEST.md) · [Licenses and references](REFERENCES.md).
