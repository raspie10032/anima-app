// SPDX-License-Identifier: GPL-3.0-only
// Guidance adapted from raspie10032/ComfyUI_RS_NAI_API_Request,
// locales/{ko,ja}/nodeDefs.json at 4de914676de8ca313b8389f4303754045a6a9cfb.
// App-specific controls retain their API values; only UI text is translated.
(() => {
  "use strict";
  const messages = {
    language: ["앱 언어", "アプリの言語"],
    scope: ["화면 언어는 이 브라우저에 저장됩니다. 프롬프트·작가 태그·파일명·기록 원문은 바꾸지 않습니다.", "表示言語をこのブラウザーに保存します。プロンプト・作家タグ・ファイル名・記録の原文は変更しません。"],
    storageUnavailable: ["이 브라우저에서는 언어를 저장할 수 없습니다. 현재 화면에만 적용합니다.", "このブラウザーでは言語を保存できません。現在の画面にのみ適用します。"],
    help: ["NAI 기능 사용 안내", "NAI機能の使い方"],
    generationTitle: ["생성·비용·중단", "生成・費用・停止"],
    generationHelp: ["한 번에 한 장을 생성합니다. 시드 -1은 무작위, 0은 고정 시드입니다. Opus 보호는 일반 Img2Img·인페인트와 Vibe·Precise를 차단합니다. 보호를 해제하면 Anlas 비용이 발생할 수 있습니다. 작은 Focused 크롭도 전송 직전 계정·영역 조건을 확인합니다. 이미 전송한 요청은 중단 후에도 완료·과금될 수 있으며 도착한 결과는 저장합니다.", "1回につき1枚生成します。シード -1 はランダム、0 は固定シードです。Opus保護は通常のImg2Img・インペイントとVibe・Preciseをブロックします。保護を解除するとAnlasを消費する場合があります。小さいFocusedクロップも送信直前にアカウントと領域の条件を確認します。送信済みのリクエストは停止後も完了・課金される場合があり、届いた結果は保存します。"],
    medium: ["Medium Effort: 14스텝 · Euler Ancestral · CFG Rescale 0 · Heavy 네거티브 고정. 입력한 기본/캐릭터 네거티브는 전송에 사용하지 않습니다. CFG와 시드는 유지합니다. 다른 모델용 입력값은 보존합니다.", "Medium Effort: 14ステップ・Euler Ancestral・CFGリスケール0・Heavyネガティブに固定。入力した共通／キャラクターのネガティブは送信しません。CFGとシードは維持し、他モデル用の入力値も保持します。"],
    routing: ["V5 Curated의 인페인트는 V4.5 Curated로 전환됩니다. 현재 보정 모델: nai-diffusion-4-5-curated-inpainting.", "V5 CuratedのインペイントはV4.5 Curatedに切り替わります。補正モデル: nai-diffusion-4-5-curated-inpainting。"],
    charactersTitle: ["캐릭터·접기·복원", "キャラクター・折りたたみ・復元"],
    charactersHelp: ["표시 슬롯은 0~22개입니다. 활성 캐릭터는 V5 최대 22명, V4/V4.5 최대 6명, V3는 미지원입니다. V5 Curated 인페인트는 V4.5의 6명 제한을 사용합니다. 숨김·사용 해제는 전송에서 제외하고 입력값을 보존합니다. 개별 접기만으로는 전송에서 제외되지 않습니다. X/Y는 0~1 위치 유도값입니다. 프리셋·히스토리·설정 PNG에는 숨김/비활성 입력도 저장되므로 공유 시 함께 전달됩니다.", "表示スロットは0～22件です。有効なキャラクターはV5で最大22人、V4/V4.5で最大6人、V3は非対応です。V5 CuratedのインペイントはV4.5の6人制限を使います。非表示・無効のスロットは送信せず、入力内容を保持します。折りたたむだけでは送信から除外されません。X/Yは0～1の位置の目安です。プリセット・履歴・設定PNGには非表示／無効の入力も保存され、共有時に含まれます。"],
    inputTitle: ["입력·마스크·Focused", "入力・マスク・Focused"],
    inputHelp: ["이미지 한 장을 입력하세요. Img2Img는 생성 크기로 Lanczos 리사이즈합니다. 일반/Focused 인페인트는 입력·마스크·생성 크기가 같아야 합니다. 흰색은 수정, 검정은 보존하며 비어 있지 않은 마스크를 저장해야 합니다. Focused는 마스크 주변을 크롭해 보정하고 밖의 픽셀을 보존합니다. 인페인트는 전용 모델을 사용합니다.", "画像を1枚入力してください。Img2Imgは生成サイズにLanczosでリサイズします。通常／Focusedインペイントでは入力・マスク・生成サイズを一致させてください。白は編集、黒は保持し、空でないマスクを保存する必要があります。Focusedはマスク周辺をクロップして補正し、外側の画素を保持します。インペイントは専用モデルを使用します。"],
    referencesTitle: ["Vibe·Precise Reference", "Vibe・Precise Reference"],
    referencesHelp: ["참조 카드를 추가해 여러 이미지를 지정합니다. Vibe는 V3/V4/V4.5 지원이며 V4/V4.5 인페인트에서는 사용할 수 없습니다. V4/V4.5는 이미지·정보 추출량의 첫 인코딩에 비용이 들고 같은 조건이면 캐시를 재사용합니다. 정규화는 강도 합이 1을 넘을 때 비례 축소합니다. Precise는 V4.5에서 인페인트도 지원하며 참조마다 생성 비용이 추가됩니다. 여러 캐릭터 참조는 특징이 섞이며 캐릭터 슬롯별 대응이 아닙니다. Vibe와 Precise는 함께 사용할 수 없습니다.", "参照カードを追加して複数の画像を指定します。VibeはV3/V4/V4.5に対応し、V4/V4.5のインペイントでは使えません。V4/V4.5では画像と情報抽出量の組み合わせを初めてエンコードする際に費用がかかり、同じ条件ならキャッシュを再利用します。正規化は強度の合計が1を超える場合に比例して下げます。PreciseはV4.5のインペイントにも対応し、参照ごとに生成費用が加算されます。複数のキャラクター参照は特徴が混ざり、個別スロットには対応しません。VibeとPreciseは併用できません。"],
    detailerTitle: ["디테일러·태거", "ディテーラー・タガー"],
    detailerHelp: ["얼굴·눈·손 영역을 첫 영역 또는 모두 순차 보정합니다. YOLO+SAM B 또는 SAM3를 선택하세요. WD 매칭은 선택한 태거 점수로 원본 캐릭터 프롬프트를 고르며 추론 태그를 추가하지 않습니다. 불확실한 영역은 건너뛰고 최신 점수와 이유를 기록합니다. 기존 이미지에서 미리보기는 검출·매칭만 수행합니다. 새 이미지 생성 후 미리보기는 기본 이미지 생성 요청이 먼저 발생합니다.", "顔・目・手の領域を、最初の1領域または全領域について順番に補正します。YOLO+SAM BまたはSAM3を選択してください。WD対応付けは選択したタガーのスコアで元のキャラクタープロンプトを選び、推論したタグを追加しません。不確かな領域はスキップし、最新のスコアと理由を記録します。既存画像のプレビューは検出・対応付けのみです。新規生成後のプレビューでは、先に元画像を生成するリクエストが発生します。"],
    taggerHelp: ["태거 준비는 WD ViT / EVA02 / PixAI 중 선택 모델만 내려받아 로딩을 검사하고 파일별 진행률을 표시합니다. 생성 시에는 로컬 캐시를 사용합니다. WD는 흰 정사각 패딩·BGR, PixAI는 전용 RGB 전처리를 사용합니다. 자동 장치는 사용 가능한 CUDA 또는 CPU이며 CPU를 직접 선택할 수 있습니다. 모델별 의존성을 설치하고 메모리가 부족하면 배치 1부터 시작하세요. 모델에 따라 점수가 달라집니다.", "タガー準備ではWD ViT / EVA02 / PixAIから選択したモデルだけをダウンロードして読み込みを確認し、ファイルごとの進捗を表示します。生成時はローカルキャッシュを使います。WDは白い正方形パディングとBGR、PixAIは専用のRGB前処理を使用します。自動デバイスは利用可能なCUDAまたはCPUで、CPUを直接選択することもできます。モデル別の依存パッケージを導入し、メモリが不足する場合はバッチ1から始めてください。モデルによってスコアが変わります。"],
    metadataTitle: ["기존 이미지의 생성 조건", "既存画像の生成条件"],
    metadataHelp: ["PNG/WebP를 읽고 미리보기에서 확인한 뒤 적용합니다. 모델 해시와 생성 방식으로 일반/인페인트 모델을 구분하며 알 수 없는 해시는 직접 선택합니다. 참조 이미지 원본은 메타데이터만으로 복원할 수 없습니다. 언어 선택은 브라우저에만 저장되며 프롬프트·프리셋·큐·PNG 설정을 바꾸지 않습니다.", "PNG/WebPを読み込み、プレビューで確認してから適用します。モデルハッシュと生成方式で通常／インペイントモデルを区別し、不明なハッシュは手動で選びます。参照画像の元データはメタデータだけでは復元できません。言語設定はブラウザーにのみ保存し、プロンプト・プリセット・キュー・PNG設定は変更しません。"],
    converterTitle: ["가중치 변환", "重みの変換"],
    converterHelp: ["적용할 공통/활성 캐릭터 프롬프트와 원본·변환 문법을 고르고 미리보기 후 적용하세요. 잘못된 ComfyUI 가중치 그룹은 생략되며 경고합니다. 일반 괄호는 이스케이프하세요. NAI V4/V5의 닫는 :: 뒤 텍스트는 쉼표로 구분해야 합니다. 구형 NAI 변환은 1.05/0.95배 괄호로 근사하며 0·음수 가중치는 표현할 수 없습니다. 구형 문법에서 나오는 변환은 소수 둘째 자리 반올림을 유지하고 짝 없는 닫는 괄호가 앞 태그에 영향을 줍니다. 변환 결과와 손실 안내를 확인하세요.", "共通／有効なキャラクタープロンプト、元の構文、変換先を選び、プレビューを確認して適用してください。不正なComfyUIの重みグループは省略して通知します。文字として使う括弧はエスケープしてください。NAI V4/V5の閉じる :: の後のテキストはカンマで区切ります。旧NAIへの変換は1.05/0.95倍の括弧で近似し、0・負の重みは表現できません。旧構文からの変換は小数点以下2桁に丸め、対応する開き括弧のない閉じ括弧は前のタグに影響します。変換結果と損失の通知を確認してください。"],
    taggerWD: ["WD: wd-matching 선택 의존성이 필요합니다. 기존에 준비한 모델 파일은 재사용합니다.", "WD: 追加パッケージ wd-matching が必要です。準備済みのモデルファイルは再利用します。"],
    taggerPixAI: ["PixAI: pixai-matching 선택 의존성이 필요합니다. 메모리 사용량이 크므로 배치 크기 1부터 시작하세요.", "PixAI: 追加パッケージ pixai-matching が必要です。メモリ使用量が多いためバッチサイズ1から始めてください。"],
    character: ["캐릭터 {number}", "キャラクター {number}"],
    characterEnabled: ["이 캐릭터 사용", "このキャラクターを有効にする"],
    characterFold: ["프롬프트·네거티브·좌표 접기 / 펼치기", "プロンプト・ネガティブ・座標を折りたたむ／開く"],
    characterRemove: ["캐릭터 삭제", "キャラクターを削除"],
    prompt: ["프롬프트", "プロンプト"],
    negative: ["네거티브", "ネガティブ"],
    commonPrompt: ["공통 프롬프트", "共通プロンプト"],
    commonNegative: ["공통 네거티브", "共通ネガティブ"],
    characterField: ["캐릭터 {number} {field}", "キャラクター {number} {field}"],
    characterCountInvalid: ["보관한 슬롯 수 이하의 정수를 지정해 주세요.", "保存済みのスロット数以下の整数を指定してください。"],
    characterOverflow: ["현재 모델은 활성 캐릭터 {limit}명까지 지원합니다 ({active}명 선택됨). 슬롯 수를 줄이거나 사용을 해제하세요. 입력값은 보존됩니다.", "現在のモデルは有効なキャラクターを最大{limit}人までサポートします（{active}人選択中）。スロット数を減らすか無効にしてください。入力内容は保持します。"],
    characterStatus: ["{model}: 활성 {active} / 최대 {limit}명 · 보관 {stored}슬롯 · 숨김 {hidden}슬롯{warning}", "{model}: 有効 {active} / 最大{limit}人・保存 {stored}スロット・非表示 {hidden}スロット{warning}"],
    modelSelect: ["모델 선택", "モデルを選択"],
    uploadReference: ["이미지를 업로드하세요.", "画像をアップロードしてください。"],
    strength: ["강도", "強度"],
    information: ["정보 추출량", "情報抽出量"],
    fidelity: ["Fidelity", "参照忠実度"],
    referenceRemove: ["참조 삭제", "参照を削除"],
    referenceType: ["참조 종류", "参照タイプ"],
    referenceCharacter: ["캐릭터", "キャラクター"],
    referenceStyle: ["스타일", "スタイル"],
    referenceBoth: ["캐릭터 + 스타일", "キャラクター + スタイル"],
    inputImg2img: ["입력 이미지를 생성 크기로 Lanczos 리사이즈합니다. Opus 보호 모드를 직접 해제해야 합니다.", "入力画像を生成サイズにLanczosでリサイズします。Opus保護を手動で解除する必要があります。"],
    inputDetail: ["입력 이미지와 생성 크기를 같게 지정하세요. 검출 영역을 순차 보정합니다.", "入力画像と生成サイズを一致させてください。検出した領域を順番に補正します。"],
    inputInfill: ["입력·마스크·생성 크기는 같아야 합니다. 그린 마스크를 저장하세요. 일반 인페인트는 Opus 보호에서 차단하며 Focused는 작은 크롭만 허용합니다.", "入力・マスク・生成サイズを一致させ、描いたマスクを保存してください。Opus保護は通常のインペイントをブロックし、Focusedの小さいクロップのみ許可します。"],
    op_infill: ["인페인트", "インペイント"],
    op_img2img: ["Img2Img", "Img2Img"],
    op_detail: ["자동 디테일러", "自動ディテーラー"],
    op_focused_infill: ["Focused Inpainting", "Focused Inpainting"],
    modelCheck: ["인페인트 모델 확인 필요", "インペイントモデルを確認してください"],
    effectiveEdit: ["{operation}: {model} · 원본 {width}x{height}{medium} · {cost}", "{operation}: {model}・元画像 {width}x{height}{medium}・{cost}"],
    mediumSteps: [" · Medium 14스텝", "・Medium 14ステップ"],
    previewFree: ["원격 요청 없는 미리보기", "リモートリクエストなしのプレビュー"],
    cropCheck: ["작은 크롭 (각 축 1024 이하 / {steps}스텝) 자격 확인", "小さいクロップ（各辺1024以下／{steps}ステップ）の条件を確認"],
    blockedOpus: ["Opus 보호로 전송 차단", "Opus保護で送信をブロック"],
    mayCost: ["Anlas 비용 가능", "Anlasを消費する可能性あり"],
    effectiveGenerate: ["전송 설정: {width}x{height} · {steps}스텝 · {cost}", "送信設定: {width}x{height}・{steps}ステップ・{cost}"],
    opusLimit: ["Opus 요청 한도", "Opusリクエスト上限"],
    accountCost: ["계정 비용이 발생할 수 있음", "アカウントへの課金の可能性あり"],
    providerDry: ["NovelAI 드라이런 · 네트워크 요청 없음", "NovelAIドライラン・ネットワークリクエストなし"],
    providerReady: ["NovelAI · 토큰 설정됨", "NovelAI・トークン設定済み"],
    providerToken: ["NAI_ACCESS_TOKEN 환경변수를 설정하고 서버를 시작하세요.", "環境変数 NAI_ACCESS_TOKEN を設定してサーバーを起動してください。"],
    maskSaved: ["그린 마스크를 저장했습니다. 전송 설정과 비용 한도를 확인하세요.", "描いたマスクを保存しました。送信設定と費用の上限を確認してください。"],
    maskChanged: ["마스크를 수정했습니다. 그린 마스크 저장을 눌러주세요.", "マスクを変更しました。「描いたマスクを保存」を押してください。"],
    metadataApplied: ["NAI 생성 조건을 적용했습니다. 전송 설정을 확인하고 생성하기를 누르세요.", "NAI生成条件を適用しました。送信設定を確認して生成を押してください。"]
  };

  const ui = window.AppI18n;
  const text = (key, params = {}) => ui.render(Object.hasOwn(messages, key) ? messages[key][0] : key, params);
  function bind(element, key, params = {}) {
    element.dataset.naiI18n = key;
    ui.setText(element, () => text(key, params));
    element.lang = ui.language;
    return element;
  }
  window.NaiI18n = Object.freeze({text, bind, setLanguage: ui.setLanguage, normalize: ui.normalize,
    get language() { return ui.language; }});
  for (const element of document.querySelectorAll("[data-nai-i18n]")) bind(element, element.dataset.naiI18n);
  const setLang = () => {
    for (const element of document.querySelectorAll("#novelai-settings,[data-nai-i18n]")) element.lang = ui.language;
  };
  window.addEventListener("nai-language-change", setLang);
  setLang();
})();
