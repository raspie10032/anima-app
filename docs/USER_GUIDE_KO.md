# Anima APP 상세 사용 가이드 (한국어)

이 문서는 Windows/PowerShell을 중심으로 Anima APP을 설치하고, 모델을 준비하고, 브라우저 GUI·CLI·AI 에이전트 API로 사용하는 전체 흐름을 설명합니다.

Anima APP은 프로젝트 내부의 `models` 폴더를 사용하는 로컬 이미지 생성 앱입니다. 일반 생성 과정에서 별도의 ComfyUI 서버를 실행하지 않습니다. AI 에이전트 API도 외부 서비스가 아니라 같은 로컬 Anima APP 서버에서 제공됩니다.

## 문서 바로가기

- [1. 가장 빠른 시작](#1-가장-빠른-시작)
- [2. 모델과 선택 기능 준비](#2-모델과-선택-기능-준비)
- [3. GUI 사용법](#3-gui-사용법)
- [4. CLI 사용법](#4-cli-사용법)
- [5. 프로젝트 데이터 위치](#5-프로젝트-데이터-위치)
- [6. 주요 환경 변수](#6-주요-환경-변수)
- [7. AI 에이전트 API 사용법](#7-ai-에이전트-api-사용법)
- [8. 오류와 해결 방법](#8-오류와-해결-방법)
- [9. 보안과 운영 경계](#9-보안과-운영-경계)
- [10. 종료 전 확인](#10-종료-전-확인)

관련 문서: [README](../README.md), [소스와 모델 참조](REFERENCES.md), [기능 수용 기준](ACCEPTANCE.md), [현재 릴리스 안내](RELEASE_0.6.1.md), [NovelAI 엔진 안내](NOVELAI_PROVIDER.md), [제3자 구성요소 고지](../NOTICE.md)

v0.6.1의 NovelAI 엔진은 공통 큐·프리셋·히스토리에서 T2I·Img2Img·일반 / Focused 인페인트·Vibe·Precise·자동 디테일러를 제공합니다. 캐릭터 슬롯 최대 22개(V5 활성 22명, V4/V4.5 활성 6명)·숨기기/사용 해제/접기·가중치 변환 6종·선택 WD/PixAI 매칭도 지원합니다. 숨긴 슬롯도 프리셋·히스토리·앱 PNG에 보존합니다. Opus 보호는 계정 자격과 요청 조건을 확인하며, 참조·Img2Img·일반 인페인트는 사용자가 보호를 직접 해제해야 합니다. 선택 모델 준비와 검증 범위는 [NovelAI 엔진 안내](NOVELAI_PROVIDER.md)를 참고하세요.

화면 상단 **앱 언어**에서 English / 한국어 / 日本語를 선택합니다. 메인 화면과 이미지 작업실 문구를 즉시 바꾸며 작성 중인 프롬프트·작업 순서·초안은 유지합니다. 원문 프롬프트와 기술 오류 상세는 번역 대상이 아닙니다. [언어 설정](LOCALES.md)을 참고하세요.

**처음 생성한다면 [이미지 생성 따라하기](IMAGE_GENERATION_KO.md)부터 보세요.** 현재 화면의 버튼 순서, NAI 한 장 생성, Anima 모델 준비, 양방향 디테일러, 원본/중간 결과 비교와 사례 재사용을 자세히 설명합니다. [English](IMAGE_GENERATION_EN.md)와 [日本語](IMAGE_GENERATION_JA.md)도 제공합니다.

v0.6.1은 **연결 · 준비 → NAI로 생성 → NAI 액세스 토큰 → 토큰 적용**에서 입력합니다. 재시작 없이 적용하고 기본은 실행 PC의 휘발성 메모리에만 보관하며 앱 종료 시 사라집니다. **이 PC에 저장 (다음 실행에도 사용)**을 선택하면 운영체제 자격증명 저장소에 보관하고 다음 실행에 복원합니다. [터미널 방식](NAI_TOKEN_SETUP.md)도 사용할 수 있습니다. [처음 설정 안내](../SETUP.md).

## 1. 가장 빠른 시작

### 1.1 요구 사항

- Python 3.10 이상
- 실제 이미지 생성을 위한 PyTorch 및 GPU 런타임
- 모델을 저장할 충분한 디스크 공간
- 모델 다운로드를 사용할 경우 인터넷 연결

아래 명령은 Anima APP 프로젝트 루트에서 실행합니다.

```powershell
python -m pip install -e .
```

얼굴 보정 기능까지 사용할 경우 선택 의존성을 함께 설치합니다.

```powershell
python -m pip install -e ".[face-detailer]"
```

### 1.2 기본 모델 준비

다음 명령은 프로젝트 내부 `models` 폴더에 기본 Anima T2I 모델 구성을 준비합니다. 로컬 원본이 없으면 큰 파일을 다운로드할 수 있습니다.

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli models copy-profile anima-t2i --source download
```

권장 체크포인트도 준비하려면 다음 명령을 추가로 실행합니다.

```powershell
python -m anima_app.cli models copy-profile anima-aesthetic-v1.1 --source download
```

`--source auto`를 사용하면 유효한 로컬 원본을 찾지 못했을 때 다운로드로 전환됩니다. 예상하지 않은 대용량 다운로드를 피하려면 CLI에서는 `--source local` 또는 `--source download`를 명시합니다.

### 1.3 GUI 실행

Windows 탐색기에서 `Run-AnimaAPP-GUI.cmd`를 더블클릭하거나 PowerShell에서 실행합니다.

```powershell
.\Run-AnimaAPP-GUI.cmd
```

런처는 사용 가능한 로컬 포트를 자동으로 선택하고 기본 브라우저를 엽니다. 터미널에서 직접 실행하려면 다음과 같이 입력합니다.

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open
```

서버를 종료하려면 실행 중인 터미널에서 `Ctrl+C`를 누릅니다.

## 2. 모델과 선택 기능 준비

### 2.1 모델 프로필

| 프로필 | 용도 | 필요성 |
|---|---|---|
| `anima-t2i` | 기본 diffusion 모델, 공유 텍스트 인코더, VAE | 기본 구성을 가장 간단히 준비할 때 사용 |
| `anima-aesthetic-v1.1` | 권장 Anima Aesthetic 체크포인트 | 선택 사항 |
| `face-detailer-detectors` | SAM-B 기반 얼굴 검출·마스크 | 얼굴 보정 시 필요 |
| `sam3-detector` | 텍스트 개념 기반 SAM3 마스크 | 선택 사항, Hugging Face 접근 권한 필요 |

얼굴 보정 모델을 준비합니다.

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli models copy-profile face-detailer-detectors --source download
```

SAM3는 gated 모델이므로 먼저 Hugging Face 계정에서 모델 접근 권한을 받은 뒤 로그인해야 합니다.

```powershell
hf auth login
$env:PYTHONPATH = 'src'
python -m anima_app.cli models copy-profile sam3-detector --source download
```

### 2.2 로컬 모델 원본 사용

기존 ComfyUI 형식의 모델 폴더에서 파일을 복사하려면 원본 경로를 환경 변수로 지정합니다. 이 경로는 복사 원본일 뿐이며, 실제 생성은 프로젝트 내부 `models` 파일을 사용합니다.

```powershell
$env:ANIMA_APP_MODEL_SOURCE = 'D:\path\to\comfyui\models'
$env:PYTHONPATH = 'src'
python -m anima_app.cli models copy-profile anima-t2i --source local
```

얼굴 검출 모델의 별도 로컬 원본은 `ANIMA_APP_FACE_DETECTOR_SOURCE`로 지정합니다.

```powershell
$env:ANIMA_APP_FACE_DETECTOR_SOURCE = 'D:\path\to\detectors'
python -m anima_app.cli models copy-profile face-detailer-detectors --source local
```

GUI에서 모델 준비 버튼을 누르면 실제 사용할 원본이 먼저 표시됩니다. 다운로드 또는 복사를 확인한 뒤 실행할 수 있으며, 준비가 끝난 프로필은 `준비됨`으로 표시됩니다.

`anima-t2i` 프로필 전체가 유일한 실행 조건은 아닙니다. 유효한 커스텀 diffusion 체크포인트와 공유 텍스트 인코더·VAE가 있으면 기본 체크포인트가 없어도 선택한 커스텀 모델로 생성할 수 있습니다. 최종 판단은 GUI의 선택 체크포인트 준비 상태 또는 API의 `generation.ready`를 따릅니다.

### 2.3 현재 모델 확인

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli health --json
python -m anima_app.cli models checkpoints
python -m anima_app.cli models loras
```

`health --json`은 런타임과 파일 상태를 JSON으로 출력합니다. 체크포인트 목록에는 프로젝트 내부 `models\diffusion_models` 아래에서 발견된 `.safetensors` 파일이 표시됩니다. 목록에 보인다는 사실만으로 유효성이 보장되지는 않으므로 실제 사용 가능 여부는 선택 체크포인트의 `generation.ready`로 판단합니다.

## 3. GUI 사용법

### 3.1 첫 생성

1. GUI의 `런타임 상태`에서 선택한 체크포인트의 생성 준비 상태를 확인합니다.
2. 프롬프트에 원하는 장면을 입력합니다.
3. 필요하면 네거티브 프롬프트를 입력합니다.
4. 체크포인트, 크기, 스텝, CFG, seed를 확인합니다.
5. `생성하기`를 누릅니다.
6. 실행 단계와 진행률을 확인하고 결과가 나타날 때까지 기다립니다.

기본 설정은 현재 앱과 OpenAPI 문서에서 확인할 수 있습니다. 오래 유지하는 자동화는 숫자를 자체적으로 복사해 두기보다 실행 중인 서버의 `GET /api/openapi.json`에서 기본값과 제한값을 읽는 편이 안전합니다.

### 3.2 프롬프트, 와일드카드, 자동완성

- `__name__`은 `wildcards\name.txt`에서 한 줄을 선택합니다.
- `__presets/name__`은 `wildcards\presets\name.txt`를 삽입합니다.
- `{red|blue|green}`은 중괄호 안의 선택지 중 하나를 무작위로 선택합니다.
- 와일드카드 모드는 `random`, `sequential`, `reverse` 중 하나입니다.
- `확장 미리보기`는 GPU 생성을 시작하지 않고 최종 확장 프롬프트만 확인합니다.

자동완성 데이터는 기본적으로 프로젝트 루트의 `autocomplete.txt`를 사용합니다. 다른 파일을 사용하려면 서버 시작 전에 다음 변수를 설정합니다.

```powershell
$env:ANIMA_APP_AUTOCOMPLETE_SOURCE = 'D:\path\to\autocomplete.txt'
```

### 3.3 참조 이미지로 i2i 생성

1. 참조 이미지 선택 영역에 PNG, JPEG 또는 WebP 파일을 놓거나 파일 선택기를 엽니다.
2. 업로드가 끝나고 미리보기와 관리 경로가 표시되는지 확인합니다.
3. i2i를 활성화합니다.
4. denoise를 조절합니다. 값이 낮을수록 원본 구성이 더 많이 유지됩니다.
5. 생성합니다.

브라우저로 업로드한 참조 이미지는 검증 후 `inputs\references`에 저장됩니다. 같은 내용은 다시 복사하지 않고 기존 파일을 재사용합니다.

### 3.4 LoRA 사용

GUI에서 LoRA 파일을 선택하거나 끌어다 놓을 수 있습니다. 업로드된 파일은 `models\loras`에 저장되며 기존 파일을 조용히 덮어쓰지 않습니다.

각 LoRA 행에서 다음 값을 설정합니다.

- 모델 강도: diffusion 모델에 적용할 강도
- CLIP 강도: 텍스트 인코더에 적용할 강도
- 여러 LoRA: 최대 8개까지 행을 추가해 순서대로 적용

CLI로 미리 가져올 수도 있습니다.

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli models import-lora 'D:\path\to\style.safetensors'
python -m anima_app.cli models loras
```

### 3.5 업스케일과 저VRAM 모드

- 일반 업스케일은 기본 생성 뒤 고해상도 단계를 추가합니다.
- `low_vram_highres`는 업스케일, 타일 업스케일, 타일 VAE 디코드를 활성화하고 고해상도 단계를 10스텝으로 고정해 VRAM 부담을 줄입니다.
- `auto`는 로컬 런타임을 확인한 뒤 적합한 메모리 프로필을 선택하고 결과를 캐시합니다.

메모리가 부족하면 먼저 다음 순서로 조정합니다.

1. `VRAM 프로필`을 `저VRAM 고해상도`로 변경합니다.
2. 시작 해상도나 업스케일 배율을 낮춥니다.
3. 동시에 직접 생성 요청을 보내지 말고 서버 큐를 사용합니다.

### 3.6 얼굴 보정, SAM3, 마스크 인페인트

SAM-B 얼굴 보정은 검출된 얼굴 영역을 후처리합니다. SAM3를 준비한 경우 `face`, `eyes`, `hands`, `hair`, `dress` 같은 텍스트 개념으로 마스크를 만들 수 있습니다.

결과 화면에서 마스크를 선택한 뒤 다음 조정을 적용할 수 있습니다.

- `마스크 확장`: 마스크 범위를 바깥쪽으로 확장
- `경계 부드럽게`: 경계를 부드럽게 처리
- Noise mask: 기존 latent를 유지하며 마스크 영역만 샘플링
- VAE inpaint: 마스크 영역을 비운 뒤 VAE 인코딩
- Crop i2i: 잘라낸 영역을 다시 생성한 뒤 원본에 합성

SAM3 또는 인페인트가 원하는 영역을 잡지 못하면 먼저 mask/overlay 결과를 확인한 뒤 `마스크 확장`과 `경계 부드럽게`를 조정합니다.

### 3.7 큐, 중지, 무한 생성

- 일반 `생성하기`도 서버 내부에서는 한 작업짜리 큐로 실행됩니다.
- 여러 장을 만들 때는 개수, seed 방식, 작업 간 지연을 설정하고 큐를 시작합니다.
- `증가` 방식에서 시드를 비우면 큐 시작 시 한 번 정한 시드부터 작업마다 1씩 증가합니다. 무한 모드의 후속 작업도 같은 시작 시드를 사용하며, 해당 엔진의 최대 시드 다음에는 0으로 돌아갑니다. 입력한 시드 `0`도 시작값으로 유지됩니다.
- `현재 작업 정지`는 대기 작업을 즉시 취소하고, 실행 중인 작업에는 협력적 중단을 요청합니다.
- 브라우저를 새로고침해도 Python 서버가 살아 있으면 진행 중인 큐에 다시 연결합니다.
- Python 서버를 종료하면 메모리에 있던 큐 상태는 복구되지 않습니다.
- 무한 모드는 직전 작업이 성공한 경우에만 다음 작업을 예약합니다.

### 3.8 설정 저장, 내보내기, 가져오기

1. `설정 이름`을 입력하고 `설정 저장`을 누르면 현재 생성 설정이 `outputs\presets`에 저장됩니다.
2. 저장된 항목을 선택하고 `설정 불러오기`를 누르면 폼에 적용됩니다.
3. `설정 내보내기`는 전체 설정을 `anima-app/presets.v1` JSON 묶음으로 내려받습니다.
4. `설정 가져오기`는 내보낸 JSON을 검증한 뒤 저장합니다.

가져오기는 묶음 구조, 각 생성 요청, 중복 이름을 먼저 검사합니다. 일부 항목만 조용히 적용하지 않으며, 실패하면 화면의 설정 상태 메시지에서 원인을 확인할 수 있습니다.

### 3.9 결과, 기록, 비교

- 최종 PNG: `outputs\images`
- 생성 정보 JSON: `outputs\manifests`
- 저장 설정: `outputs\presets`

기록에서 항목을 선택하면 결과를 다시 볼 수 있습니다. 중간 단계가 있으면 `원본`, `업스케일`, `페이스 디테일러` 등의 이미지를 비교할 수 있습니다.

- 검색창은 프롬프트, 모델, LoRA를 대상으로 전체 기록을 검색합니다.
- `전체`, `이미지`, `드라이런` 필터는 페이지를 나누기 전에 서버에서 적용됩니다.
- 처음에는 최신 8개가 표시되고, 이전 결과가 있으면 `더 보기`가 나타납니다.
- 기록 상단에서 관리 중인 이미지·manifest 용량과 남은 디스크 공간을 확인할 수 있습니다.
- 삭제는 항목별 확인을 거치며 자동 정리나 자동 용량 삭제는 수행하지 않습니다.

## 4. CLI 사용법

편집 설치가 끝나고 Python의 Scripts 경로가 `PATH`에 있으면 `anima-app` 명령을 사용할 수 있습니다. 소스 체크아웃에서 확실하게 실행하려면 다음처럼 `PYTHONPATH`와 모듈 진입점을 사용합니다.

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli --help
```

### 4.1 GPU 없이 요청 확인

`--dry-run`은 요청을 검증하고 manifest를 만들지만 실제 렌더러를 실행하지 않습니다.

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli t2i --prompt 'anime portrait, soft light' --dry-run
```

dry-run 성공은 요청·manifest 경로가 동작한다는 뜻이며, 모델 로딩·GPU 생성·화질까지 검증한 것은 아닙니다.

### 4.2 기본 실제 생성

```powershell
$env:PYTHONPATH = 'src'
python -m anima_app.cli t2i `
  --prompt 'anime portrait, detailed eyes, soft lighting' `
  --negative 'low quality, blurry'
```

### 4.3 seed와 크기 지정

```powershell
python -m anima_app.cli t2i `
  --prompt 'anime character, city at night' `
  --width 832 `
  --height 1216 `
  --steps 20 `
  --cfg 3.5 `
  --seed 12345
```

이 숫자는 현재 기본값을 보여 주는 예시입니다. 자동화에서는 OpenAPI 스키마의 현재 기본값과 최대값을 읽어 사용합니다.

### 4.4 LoRA 적용

`--lora`는 `경로`, `경로|공통 강도`, `경로|모델 강도|CLIP 강도` 형식을 지원합니다. 최대 8개까지 반복할 수 있고 각 강도 범위는 0부터 10까지입니다.

```powershell
python -m anima_app.cli t2i `
  --prompt 'anime portrait' `
  --lora 'style.safetensors|0.8|0.8' `
  --lora 'detail.safetensors|0.5|0.5'
```

### 4.5 i2i와 업스케일

직접 CLI는 명시적인 절대 참조 이미지 경로도 허용합니다.

```powershell
python -m anima_app.cli t2i `
  --prompt 'anime illustration, refined line art' `
  --image 'D:\path\to\reference.png' `
  --denoise 0.35 `
  --upscale `
  --upscale-scale 1.5 `
  --upscale-tiled `
  --vae-decode tiled
```

### 4.6 저VRAM과 얼굴 보정

```powershell
python -m anima_app.cli t2i `
  --prompt 'anime portrait, detailed face' `
  --memory-profile low_vram_highres `
  --face-detailer `
  --face-mask-backend sam_b
```

모든 CLI 옵션은 다음 명령으로 현재 설치본에서 확인합니다.

```powershell
python -m anima_app.cli t2i --help
```

## 5. 프로젝트 데이터 위치

기본 프로젝트 루트는 명령을 실행한 현재 폴더입니다. `ANIMA_APP_ROOT`를 설정하면 다른 루트를 사용할 수 있습니다.

```text
<project-root>/
├─ models/
│  ├─ diffusion_models/
│  ├─ text_encoders/
│  ├─ vae/
│  ├─ loras/
│  └─ detectors/
├─ inputs/
│  └─ references/
├─ outputs/
│  ├─ images/
│  ├─ manifests/
│  ├─ presets/
│  ├─ runtime_profile_cache.json
│  └─ wildcard_state.json
└─ wildcards/
```

다른 프로젝트 데이터 루트를 지정하는 예시입니다.

```powershell
$env:ANIMA_APP_ROOT = 'D:\AnimaWorkspace'
$env:PYTHONPATH = 'src'
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open
```

`ANIMA_APP_ROOT`를 바꾸면 모델, 입력, 출력, 와일드카드 위치도 함께 바뀝니다.

## 6. 주요 환경 변수

| 변수 | 용도 |
|---|---|
| `ANIMA_APP_ROOT` | 모델·입력·출력의 프로젝트 루트 변경 |
| `ANIMA_APP_MODEL_SOURCE` | 모델 복사용 로컬 원본 경로 |
| `ANIMA_APP_FACE_DETECTOR_SOURCE` | 얼굴 검출 모델 복사용 원본 경로 |
| `ANIMA_APP_FACE_DETECTOR_FALLBACKS` | 여러 얼굴 검출 모델 후보 경로 |
| `ANIMA_APP_AUTOCOMPLETE_SOURCE` | 자동완성 파일 경로 |
| `ANIMA_APP_CUDA_VISIBLE_DEVICES` | GUI 런처가 사용할 CUDA 장치 선택 |
| `CUDA_VISIBLE_DEVICES` | 직접 CLI 실행 시 사용할 CUDA 장치 선택 |
| `ANIMA_LLM_RUNTIME_URL` | 별도로 실행 중인 선택적 LLM worker 주소 |

환경 변수는 서버나 Python 프로세스를 시작하기 전에 설정해야 합니다.

## 7. AI 에이전트 API 사용법

### 7.1 에이전트 테스트용 서버 시작

에이전트가 안정적인 주소를 사용해야 한다면 사용 가능한 로컬 포트를 하나 선택해 명시합니다. 아래 `8765`는 예시값이며 고정 요구사항이 아닙니다.

터미널 A:

```powershell
$port = 8765
$env:PYTHONPATH = 'src'
python -m anima_app.cli serve `
  --host 127.0.0.1 `
  --port $port `
  --dry-run-default
```

`--dry-run-default`는 첫 연동 시험에서 실수로 GPU 생성을 시작하지 않도록 합니다. 실제 생성 서버에서는 이 옵션을 빼거나 요청마다 `dry_run: false`를 명시합니다.

터미널 B:

```powershell
$port = 8765
$baseUrl = "http://127.0.0.1:$port"
```

### 7.2 OpenAPI 계약 읽기

```powershell
$spec = Invoke-RestMethod "$baseUrl/api/openapi.json"
$spec.info
$spec.paths.PSObject.Properties.Name
```

에이전트 또는 OpenAPI 도구에는 다음 URL을 계약 주소로 제공합니다.

```text
http://127.0.0.1:<실행 중인 포트>/api/openapi.json
```

서버가 제공하는 계약에는 다음 정보가 포함됩니다.

- OpenAPI 3.1 및 JSON Schema 2020-12
- 현재 앱 버전
- 정규 `T2IRequest` 필드
- 기본값, enum, 최대값
- 생성·큐·취소·진행률·manifest 경로
- 정상 요청과 대표 오류 예제
- 로컬 전용 및 비멱등성 주의사항

### 7.3 핵심 엔드포인트

| 메서드와 경로 | 용도 |
|---|---|
| `GET /api/openapi.json` | 기계 판독 계약 조회 |
| `GET /api/version` | 앱 버전 조회 |
| `GET /api/health` | 런타임·저장소·모델 상태 조회 |
| `GET /api/readiness` | 선택 체크포인트의 생성 준비 상태 조회 |
| `GET /api/checkpoints` | 체크포인트 목록과 기본값 조회 |
| `GET /api/loras` | LoRA 목록 조회 |
| `POST /api/generate` | 동기식 생성, 호환용 |
| `POST /api/jobs` | 취소 가능한 생성 작업 등록 |
| `GET /api/jobs` | 보존 중인 큐 작업 목록 조회 |
| `GET /api/jobs/{job_id}` | 한 작업의 상태 조회 |
| `POST /api/jobs/{job_id}/cancel` | 작업 취소 또는 중단 요청 |
| `GET /api/progress/{progress_id}` | 실행 단계 진행률 조회 |
| `GET /api/manifests/{manifest_name}` | 완료 결과 manifest 조회 |

에이전트는 `POST /api/generate`보다 `POST /api/jobs`를 우선 사용하는 것이 좋습니다. 큐 경로는 폴링과 취소가 가능하며 긴 GPU 작업 중 연결을 계속 유지할 필요가 없습니다.

### 7.4 준비 상태 확인

```powershell
$readiness = Invoke-RestMethod "$baseUrl/api/readiness"
$readiness.generation
```

특정 체크포인트를 확인하려면 URL 인코딩한 상대 경로를 전달합니다.

```powershell
$checkpointInfo = Invoke-RestMethod "$baseUrl/api/checkpoints"
$checkpoint = $checkpointInfo.default
$encodedCheckpoint = [Uri]::EscapeDataString($checkpoint)
$readiness = Invoke-RestMethod "$baseUrl/api/readiness?checkpoint=$encodedCheckpoint"
$readiness.generation
```

실제 생성 가능 여부는 응답 전체의 `ready`가 아니라 `generation.ready`를 기준으로 판단합니다. dry-run은 모델 준비 검사를 우회할 수 있으므로 `generation.dry_run`이 `true`인 결과를 실제 모델 준비 증거로 사용하지 않습니다.

### 7.5 동기식 dry-run

```powershell
$requestJson = @{
  prompt = 'anime portrait, soft light'
  dry_run = $true
} | ConvertTo-Json -Depth 20 -Compress
$body = [Text.UTF8Encoding]::new($false).GetBytes($requestJson)

$result = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/api/generate" `
  -ContentType 'application/json; charset=utf-8' `
  -Body $body

$result
```

성공하면 `status`는 `dry_run`이고 `manifest_path`와 `manifest_name`이 반환됩니다. `output_path`는 실제 이미지가 없으므로 `null`입니다.

### 7.6 권장 큐 생성 흐름

작업을 등록합니다.

```powershell
$enqueueJson = @{
  count = 1
  infinite = $false
  seed_mode = 'fixed'
  delay_seconds = 0
  request = @{
    prompt = 'anime portrait, cinematic light'
    dry_run = $true
  }
} | ConvertTo-Json -Depth 20 -Compress
$enqueueBody = [Text.UTF8Encoding]::new($false).GetBytes($enqueueJson)

$batch = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/api/jobs" `
  -ContentType 'application/json; charset=utf-8' `
  -Body $enqueueBody

$jobId = $batch.jobs[0].id
$jobId
```

작업이 끝날 때까지 폴링합니다.

```powershell
$terminalStates = @('completed', 'failed', 'cancelled')

do {
  $job = Invoke-RestMethod "$baseUrl/api/jobs/$jobId"
  if ($job.status -eq 'running' -and $job.progress_id) {
    $progressId = [Uri]::EscapeDataString($job.progress_id)
    try {
      $progress = Invoke-RestMethod "$baseUrl/api/progress/$progressId"
      $progress.summary
    } catch {
      $statusCode = [int]$_.Exception.Response.StatusCode
      if ($statusCode -ne 404) { throw }
    }
  }
  if ($job.status -notin $terminalStates) {
    Start-Sleep -Milliseconds 500
  }
} while ($job.status -notin $terminalStates)

$job
```

작업 시작 직후의 짧은 구간에는 progress가 아직 없어 HTTP 404가 반환될 수 있으므로 위 예제는 404만 무시합니다. 권위 있는 작업 상태는 항상 `GET /api/jobs/{job_id}`입니다.

완료된 manifest를 읽습니다.

```powershell
if ($job.status -eq 'completed') {
  $manifestName = [Uri]::EscapeDataString($job.result.manifest_name)
  $manifest = Invoke-RestMethod "$baseUrl/api/manifests/$manifestName"
  $manifest
}
```

실제 생성 이미지가 있으면 서버가 반환한 `output_url`을 그대로 기본 URL과 결합합니다. `output_path`는 호스트의 로컬 파일 경로이므로 HTTP URL로 변환해 추측하지 않습니다.

```powershell
if ($job.status -eq 'completed' -and $job.result.output_url) {
  Invoke-WebRequest `
    -Uri "$baseUrl$($job.result.output_url)" `
    -OutFile '.\anima-result.png'
}
```

실제 생성을 하려면 모델 준비를 확인한 뒤 요청의 `dry_run`을 `$false`로 설정합니다.

등록 응답을 받지 못했을 때는 같은 POST를 바로 다시 보내지 말고 `GET /api/jobs`에서 먼저 확인합니다. 여러 작업을 등록하면 최초 `jobs` 배열의 모든 ID를 각각 추적해야 합니다. 무한 큐는 새 작업이 나중에 추가되고 배치 전체 취소 엔드포인트도 없으므로 무인 에이전트의 기본 모드로 사용하지 않는 편이 안전합니다.

### 7.7 작업 취소

```powershell
$emptyBody = [Text.UTF8Encoding]::new($false).GetBytes('{}')
$cancelled = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/api/jobs/$jobId/cancel" `
  -ContentType 'application/json' `
  -Body $emptyBody

$cancelled
```

대기 작업은 바로 취소됩니다. 이미 GPU에서 실행 중인 작업은 취소 응답 직후에도 `running`이면서 `cancel_requested: true`일 수 있습니다. 이 경우 `completed`, `failed`, `cancelled` 중 하나가 될 때까지 계속 폴링합니다.

### 7.8 정규 생성 요청 예제

모든 필드를 보낼 필요는 없습니다. 에이전트는 OpenAPI 기본값을 확인한 뒤 필요한 필드만 보내는 편이 안전합니다.

```powershell
$generationRequest = @{
  prompt = 'anime portrait, detailed eyes'
  negative_prompt = 'blurry, low quality'
  memory_profile = 'auto'
  seed = 12345
  loras = @(
    @{
      path = 'style.safetensors'
      model_strength = 0.8
      clip_strength = 0.8
    }
  )
  i2i = @{
    enabled = $false
  }
  upscale = @{
    enabled = $true
    scale = 1.5
    tiled = $true
  }
  face_detailer = @{
    enabled = $true
    mask_backend = 'sam_b'
  }
  vae_decode = @{
    mode = 'auto'
  }
  wildcard_mode = 'random'
  dry_run = $false
}
```

정규 객체는 OpenAPI에서 `additionalProperties: false`입니다. 현재 서버의 호환 파서는 일부 알 수 없는 필드를 무시할 수 있지만, 에이전트는 전송 전에 반드시 계약 기준으로 필드를 검증해야 합니다.

### 7.9 에이전트에서 참조 이미지 업로드

HTTP i2i는 앱이 관리하는 상대 경로만 허용합니다. 아래 업로드 경로는 GUI와 에이전트가 사용할 수 있지만 현재 핵심 OpenAPI 경로에는 포함되지 않은 확장 경로입니다. PNG 업로드 예제입니다.

```powershell
$imageFile = Get-Item 'D:\path\to\reference.png'
$encodedName = [Uri]::EscapeDataString($imageFile.Name)

$uploadedReference = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/api/inputs/reference?filename=$encodedName" `
  -ContentType 'image/png' `
  -InFile $imageFile.FullName

$uploadedReference.relative_path
```

반환된 `relative_path`를 그대로 사용합니다.

```powershell
$generationRequest.i2i = @{
  enabled = $true
  image_path = $uploadedReference.relative_path
  denoise = 0.35
}
```

JPEG은 `image/jpeg`, WebP는 `image/webp`를 사용합니다. 파일 확장자, Content-Type, 실제 이미지 형식이 서로 일치해야 합니다.

### 7.10 에이전트에서 LoRA 업로드

```powershell
$loraFile = Get-Item 'D:\path\to\style.safetensors'
$encodedName = [Uri]::EscapeDataString($loraFile.Name)

$uploadedLora = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/api/loras/upload?filename=$encodedName" `
  -ContentType 'application/octet-stream' `
  -InFile $loraFile.FullName

$uploadedLora.relative_path
```

HTTP 생성 요청의 `loras[].path`에는 응답의 `relative_path`를 사용합니다. 같은 이름의 다른 내용은 해시 접미사가 붙은 별도 파일로 보존됩니다.

### 7.11 에이전트 동작 정책 권장안

에이전트 도구 설명이나 정책에는 다음 순서를 넣는 것이 좋습니다.

1. 시작할 때 OpenAPI 문서를 읽고 지원 경로와 현재 제한을 갱신한다.
2. 실제 생성 전에 readiness를 확인한다.
3. 새 요청은 큐에 한 번만 등록한다.
4. 네트워크 응답이 불확실하면 동일 POST를 즉시 재전송하지 않고 먼저 `GET /api/jobs`를 확인한다.
5. `queued`, `waiting`, `running` 동안 상태를 폴링한다.
6. 사용자가 중지를 요청하면 cancel 엔드포인트를 호출한다.
7. `completed`일 때 `manifest_name`으로 manifest를 읽는다.
8. `failed` 또는 HTTP 오류에서는 `error_code`, `error`, `http_status`를 보존해 사용자에게 보고한다. NAI의 `error_detail`이 있으면 원인·단계·원격 HTTP 코드·언어별 다음 조치도 함께 사용한다. `remote_outcome_unknown`이면 자동 재전송하지 않는다.

현재 POST 요청은 `Idempotency-Key`를 지원하지 않습니다. 동일한 등록 요청을 재전송하면 중복 생성될 수 있습니다.

현재 OpenAPI에서 health, readiness, progress, manifest 같은 일부 조회 응답은 `GenericObject`로 표현됩니다. 클라이언트는 응답에 새 필드가 추가될 수 있다고 가정하고 필요한 키만 읽어야 합니다.

## 8. 오류와 해결 방법

메인 화면의 **작업 순서**에서 NAI와 Anima의 생성·디테일러를 연결하고 후처리 순서를 바꿀 수 있습니다. 단계별 설정, 모델 준비, 크롭 오류와 부분 결과 보존은 [생성 작업실 가이드](GENERATION_WORKSPACE_KO.md)를 참고하세요.

| 증상 또는 코드 | 의미 | 조치 |
|---|---|---|
| `ModuleNotFoundError: anima_app` | 소스 경로 또는 설치가 잡히지 않음 | 프로젝트 루트에서 editable install을 하거나 `PYTHONPATH=src` 설정 |
| `models_not_ready` / HTTP 409 | 필수 모델이 없거나 손상됨 | `missing_files`, `invalid_files` 확인 후 모델 프로필 준비 |
| `generation_input_missing` / HTTP 400 | 참조 이미지 등 요청 파일이 없음 | 관리 경로와 실제 파일 확인 |
| `generation_busy` / HTTP 409 | 다른 GPU 작업이 잠금을 사용 중 | 직접 생성 대신 `/api/jobs` 큐 사용 |
| `queue_full` / HTTP 429 | 활성 큐 제한 초과 | 기존 작업이 끝난 뒤 다시 등록 |
| `generation_failed` / HTTP 500 | 런타임 또는 GPU 생성 실패 | `error`와 manifest, 터미널 로그 확인; OOM이면 저VRAM 모드 사용 |
| `request_host_untrusted` / HTTP 403 | Host가 현재 loopback 포트와 불일치 | 서버가 출력한 정확한 주소와 포트 사용 |
| `request_origin_untrusted` / HTTP 403 | 다른 Origin의 변경 요청 | 로컬 클라이언트는 Origin을 생략하거나 같은 로컬 Origin 사용 |
| 포트 사용 중 | 선택한 고정 포트를 다른 프로세스가 사용 | 다른 로컬 포트를 선택하거나 GUI처럼 `--port 0` 사용 |
| SAM3 다운로드 실패 | gated 모델 권한 또는 인증 부족 | Hugging Face 권한과 `hf auth login` 확인 |

JSON POST 요청은 `Content-Type: application/json`이어야 하며 최상위 값은 객체여야 합니다. 문자열 형태의 `"true"`가 아니라 JSON boolean인 `true` 또는 `false`를 사용합니다. 중첩 설정이 잘리지 않도록 PowerShell의 `ConvertTo-Json`에는 충분한 `-Depth`를 지정하고, 한국어 프롬프트는 위 예제처럼 BOM 없는 UTF-8 바이트로 보내는 것이 안전합니다.

## 9. 보안과 운영 경계

- 서버는 `localhost` 또는 IPv4 loopback 주소에만 바인딩됩니다.
- `0.0.0.0`, LAN 주소, 공개 인터넷에 직접 노출하지 않습니다.
- 모델·LoRA·입력·출력은 로컬 파일이며 공개 릴리스에 포함되지 않습니다.
- 큐는 메모리에만 있으므로 Python 서버 재시작 뒤 복원되지 않습니다.
- 알 수 없는 POST 결과를 자동 재시도하지 않습니다.
- 에이전트에게 임의 절대 경로나 파일 삭제 권한을 주지 않습니다.
- HTTP i2i와 LoRA는 서버가 검증한 관리 상대 경로를 사용합니다.
- dry-run 결과와 실제 GPU 생성 성공을 구분해 기록합니다.

## 10. 종료 전 확인

1. 진행 중인 작업이 없는지 `GET /api/jobs` 또는 GUI 큐 상태를 확인합니다.
2. 필요한 결과와 manifest가 `outputs` 아래에 있는지 확인합니다.
3. 서버 터미널에서 `Ctrl+C`를 누릅니다.
4. 별도 LLM worker를 실행했다면 해당 프로세스도 별도로 종료합니다.

OpenAPI가 현재 앱 계약의 기준이며, 이 가이드의 예시보다 실행 중인 `GET /api/openapi.json`의 스키마와 제한값을 우선합니다.
