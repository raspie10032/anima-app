# 연결과 준비 / Connect and prepare / 接続・準備

These instructions describe Anima APP **v0.6.1**. See the [release notes](docs/RELEASE_0.6.1.md) for download and upgrade instructions.

## 한국어

앱을 열고 **연결 · 준비**를 누릅니다. 사용할 기능만 준비하면 됩니다.

위쪽 **연결 · 기능 / 필요 모델 / 레퍼런스**로 화면을 바꿉니다.
**필요 모델**에는 기능별 용도, 파일 이름, 준비 상태와 **모델 원본 보기** 링크가 나옵니다.
NAI만 쓸 때는 로컬 생성 모델이 필요 없습니다. Anima 생성에는 체크포인트·텍스트 인코더·VAE가 필요하고, 디테일러·SAM3·LoRA는 해당 기능을 쓸 때 준비합니다.
VRS에는 비전 인코더가 필요하며 WD/PixAI 태거와 캡션 모델은 필요하지 않습니다. SWEGCA 코어는 앱에 포함돼 있습니다.
**레퍼런스**에서 생성 가이드, Anima·NovelAI 공식 자료, NAI 연동 프로젝트와 VRS 가중치·전처리 원본을 엽니다.

**연결 · 기능 → VRS 이미지 검색 사용**으로 VRS를 켜고 끕니다. 이 선택은 다음 실행에도 유지됩니다.
끄면 VRS 검색·색인·인코더 준비가 차단되고 대기 중인 인코더 메모리를 비웁니다. 이미지·프롬프트·색인·평가는 지우지 않으며, 기본 이미지 검색·태그 검색·보관·생성은 계속 쓸 수 있습니다.
다시 켜면 같은 인코더의 기존 색인을 재사용합니다. 실행 중인 생성·검색·준비 작업은 먼저 완료하고, 색인은 취소한 뒤 설정을 바꿉니다.
이미지 작업실의 **검색 방식 · 라이브러리 관리 → VRS 켜기·끄기 / 필요 모델**에서도 설정 창으로 이동합니다.

1. **NAI로 생성:** NovelAI의 User Settings → Account → Get Persistent API Token에서 발급한 토큰을 **NAI 액세스 토큰**에 넣고 **토큰 적용**을 누릅니다. 입력 내용은 화면에서 지워지고 실행 PC의 휘발성 메모리에만 유지되며 앱을 종료하면 사라집니다. **이 PC에 저장 (다음 실행에도 사용)**을 선택하면 운영체제 자격증명 저장소에 저장하고 재실행 시 복원합니다. **토큰 지우기**로 연결을 해제합니다.
2. **Anima로 생성 · 보정:** **기본 모델 준비** 또는 **Aesthetic 모델 준비**를 누릅니다. 얼굴 보정을 쓸 때는 **얼굴 검출 모델 준비**도 누릅니다. 기존 파일을 확인하고 필요한 파일만 받습니다. 모델에 따라 수 GB를 다운로드합니다.
3. **비슷한 그림 찾기:** **이미지 인코더 준비**를 누릅니다. 약 320 MiB의 비전 가중치와 필요한 실행 패키지를 준비합니다. 현재 인코더는 CUDA GPU가 필요합니다. 이미지 작업실에서 폴더를 가져온 다음 **등록 이미지 색인 만들기**를 누릅니다.
4. **생성:** 준비 창을 닫고 엔진을 선택하고 프롬프트를 입력합니다. **세로 / 정사각 / 가로**로 크기를 고르고 **생성**을 누릅니다. **고급 설정 보기**는 입력값을 유지한 채 상세 샘플러·시드·프리셋·메모리 설정을 펼칩니다.

외부 이미지는 캡션 작업 없이 가져옵니다. 생성 정보가 없거나 깨졌어도 읽을 수 있는 그림은 등록됩니다. 생성 정보는 정제한 뒤 별도로 연결합니다. 원본이 사라진 항목은 **파일별 문제 확인**에서 확인합니다. 색인은 8장씩 저장하고, 취소해도 저장된 부분은 남습니다. 준비된 그림부터 검색할 수 있습니다.

인코더 코드와 SWEGCA 근거 누적 코어는 앱 안에 들어 있습니다. 외부 VRS 저장소나 별도 Python 경로를 지정하지 않습니다. 기존 벡터는 보존하며 처리 방식이 바뀌면 새 계약의 색인을 준비합니다. [이미지 작업실 자세히](docs/IMAGE_LIBRARY_KO.md) · [생성 과정](docs/IMAGE_GENERATION_KO.md).

## English

Open **Connect & prepare** and prepare the features you want to use.

Use **Connections & features / Required models / References** at the top.
Required models shows each feature's purpose, filenames, readiness and original download links. NAI alone needs no local generation model; Anima needs a checkpoint, text encoder and VAE. Detailer, SAM3 and LoRA files are optional for their respective features. VRS needs the vision encoder, not a caption model or WD/PixAI tagger. SWEGCA is bundled.
References links to the app guide, Anima/NovelAI documentation, NAI integration project and pinned vision/preprocessing sources.

**Connections & features → Enable VRS image search** persists across restart.
Disabling blocks VRS retrieval, indexing and encoder preparation and releases idle encoder memory. Images, prompts, vectors and ratings remain intact. Basic image search, metadata search, storage and generation remain available. Re-enabling reuses the existing matching encoder index. Finish active work first, or cancel indexing before changing the switch.
Image Workspace also offers **VRS on/off / Required models** under library management.

1. **Generate with NAI:** Obtain a persistent API token from NovelAI's User Settings → Account. Enter it in **NAI access token**, then **Apply token**. By default it stays in volatile memory on the PC running the app until exit. Select **Save on this PC (use after restart)** to save it in the operating system credential store and restore it at the next launch. **Clear token** disconnects it.
2. **Generate & refine with Anima:** Choose **Prepare base model** or **Prepare Aesthetic model**. Use **Prepare face detector** for face detailing. Existing files are checked first; models may require several GB.
3. **Find similar images:** Choose **Prepare image encoder**, then import a folder in Image Workspace and **Index imported images**. The pinned vision weights are about 320 MiB, plus runtime packages. This encoder requires CUDA; basic CPU similarity remains available.
4. **Generate:** Close the dialog, select an engine, enter a prompt, choose **Portrait / Square / Landscape**, and generate. **Show advanced settings** exposes the detailed controls without resetting values.

Caption-free images are accepted. Malformed metadata is separated from image errors. Indexing commits eight images at a time, survives cancellation and allows searching the prepared subset. **Check file issues** identifies missing originals or failures. The encoder and SWEGCA evidence code ship inside the app; no separate repository or Python path is required. [Image library](docs/IMAGE_LIBRARY_EN.md).

## 日本語

アプリで **接続・準備** を開き、使う機能を準備します。

上部の **接続・機能 / 必要なモデル / 参考資料** で切り替えます。
必要なモデルには機能ごとの用途・ファイル名・準備状態・配布元リンクを表示します。NAIだけならローカル生成モデルは不要です。Animaにはチェックポイント・テキストエンコーダー・VAEが必要で、ディテーラー・SAM3・LoRAは使う場合のみ準備します。VRSにはビジョンエンコーダーが必要ですが、キャプションモデルやWD/PixAIタガーは不要です。SWEGCAは同梱されています。
参考資料から生成ガイド・Anima/NovelAI公式資料・NAI連携プロジェクト・VRSの重みと前処理の出典を開けます。

**接続・機能 → VRS画像検索を使う** の設定は次回起動時も保持されます。
オフにするとVRS検索・インデックス作成・エンコーダー準備を無効にし、待機中のエンコーダーのメモリを解放します。画像・プロンプト・インデックス・評価は削除せず、基本検索・タグ検索・保管・生成は引き続き使えます。再びオンにすると同じエンコーダーの既存インデックスを再利用します。実行中の処理は完了を待ち、インデックス作成は先に中止してください。
画像ワークスペースの **VRSオン・オフ / 必要なモデル** からも設定画面に移動できます。

1. **NAIで生成:** NovelAIのUser Settings → AccountでPersistent API Tokenを発行し、**NAIアクセストークン → トークンを適用**から入力します。通常は実行PCの揮発性メモリだけに保持し、アプリ終了時に消えます。**このPCに保存（次回起動時も使用）**を選ぶとOSの資格情報ストアに保存し、次回起動時に復元します。
2. **Animaで生成・補正:** 基本モデルまたはAestheticモデルを準備します。顔補正には顔検出モデルも必要です。既存ファイルを確認して不足分を取得します。数GBの空き容量が必要な場合があります。
3. **似た画像を探す:** 画像エンコーダーを準備し、画像ワークスペースにフォルダーを取り込んでから画像インデックスを作成します。ビジョン重みは約320 MiBで、実行パッケージも必要です。このエンコーダーはCUDAを使用します。基本のCPU検索も使えます。
4. **生成:** 準備画面を閉じ、エンジン、プロンプト、縦・正方形・横を選んで生成します。詳細設定は現在の入力を保ったまま開けます。

キャプションのない画像も取り込めます。不正な生成情報と画像自体のエラーを分けて処理します。インデックスは8枚ずつ保存し、中止後も完了分を維持します。準備済みの画像から検索できます。元画像の欠落などはファイル別の問題一覧で確認します。エンコーダーとSWEGCAの根拠蓄積コードはアプリに同梱しています。
