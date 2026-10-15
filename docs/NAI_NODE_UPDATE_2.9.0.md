# RS NAI 2.9.0 compatibility and workflow update

Source: [ComfyUI_RS_NAI_API_Request `a1c7d40bd40598665ab52d869968ccfe3fe1a07a`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/tree/a1c7d40bd40598665ab52d869968ccfe3fe1a07a), version 2.9.0. App baseline: v0.6.1, `0e8cd9cc6e5f3cfef607749396f0a3923e290110`. This document describes the subsequent development changes; the published v0.6.1 ZIP does not contain them.

## 사용 방법

1. 생성 화면에서 **이미지에서 생성 조건 가져오기**를 열고 PNG 또는 WebP를 넣습니다.
2. 원본 그림의 공통·네거티브 프롬프트, 모델, 캐릭터별 프롬프트와 좌표를 확인합니다. RS NAI 디테일러 파일은 원본 생성 조건과 **얼굴별 보정 기록**을 따로 표시합니다.
3. **적용할 항목**에서 필요한 항목만 체크하고 **생성 조건 적용**을 누릅니다. 예를 들어 프롬프트·캐릭터만 가져오려면 크기와 시드 등을 해제합니다. 체크하지 않았거나 파일에 없는 항목과 Opus 보호 설정은 현재 값을 유지합니다. 적용할 때 생성 엔진은 NAI로 전환됩니다.
4. **작업 순서**에서 NAI 디테일러를 추가합니다. **첫 단계 프롬프트 · 캐릭터 사용**을 켜면 첫 NAI 생성의 캐릭터별 프롬프트와 좌표까지 전달합니다. 중간에 Anima 보정을 넣어도 처음의 NAI 조건을 유지합니다.
5. **첫 NAI 단계에서 이어받기**에서 모델·CFG·스텝·샘플러 등을 선택합니다. 선택한 항목만 첫 단계의 조건을 쓰고 나머지는 해당 보정 단계의 값을 씁니다. 첫 생성이 Anima라면 NAI 조건을 이어받는 체크는 사용하지 않습니다.
6. 여러 캐릭터는 **캐릭터 연결 → 자동**에서 WD 태그 연결을 사용합니다. 태거 준비가 필요하며, 설정에서 직접 WD 연결 또는 공통 조건을 고를 수 있습니다. **얼굴·눈·손 검출기**도 자동 또는 준비된 모델을 선택할 수 있습니다. 지정한 모델이 없으면 해당 모델을 준비하라는 오류를 표시합니다.
7. NAI 설정 및 각 NAI 작업 단계에서 **저장 형식**을 PNG·WebP 무손실·WebP 손실로 선택합니다. WebP 품질은 1–100, **응답 대기 시간**은 30–1,800초(기본 300초)입니다. 대기 시간은 개별 원격 요청에 적용하며 재시도 규칙은 그대로입니다. WebP도 생성 조건을 포함하고 PNG 원본을 함께 보존합니다. 변환 실패 시 PNG를 결과로 사용합니다.

원본 조건이 없는 구형 디테일러 파일은 얼굴 프롬프트를 그림 전체의 조건으로 가져오지 않습니다. 이미지 라이브러리 등록·유사 이미지 검색은 계속 가능합니다. 새 해석은 새로 가져오는 파일에 적용합니다. 기존 라이브러리 기록은 자동으로 다시 쓰지 않으며, 변경되지 않은 파일의 폴더 재가져오기는 건너뛰므로 기존 자료의 일괄 재해석은 별도 작업입니다.

## Implemented scope

| Area | Behavior |
|---|---|
| Metadata | Read `rs_nai` version 1, `base_generation`, `edits`, legacy `rs_detailer_regions` and WebP EXIF tag 37395. Validate model/operation/character fields through the existing metadata normalizer. |
| Provenance | Original full-image generation settings take precedence over stale last-crop `Comment`. Malformed/unknown records do not fall back to crop prompts. API responses return allowlisted settings and edit summaries, not raw embedded records. |
| Import | Select prompt, negative, character slots/coordinates, model/operation, size, seed, sampling and app detailer groups. Disabled restoration when no full-image context is available. |
| Library | PNG and both WebP formats supply full-image prompts and artist tags; crop-only records remain visually searchable without false full-image prompt metadata. |
| Workflow | First NAI prompt inheritance includes characters, active slots, positions and resolved wildcards across intermediate Anima stages. Optional model/sampling inheritance is validated and persisted. Multi-character matching defaults to WD when not overridden. |
| Output | PNG default; lossless/lossy WebP with retained metadata and PNG source. Atomic WebP write and PNG fallback. Output format/quality/timeouts persist through presets and workflows. |
| Detection | Explicit face/eye/hand detector selection in standalone and workflow detailers, preserving automatic selection. Workflow preparation checks the selected NAI detector and mask dependencies before the first paid generation. |
| UI | Korean, English and Japanese controls, warnings and restoration preview. Current user prompts and chosen checkboxes survive locale changes. |

NAI request timeout covers generation, reference encoding and region correction requests. Opus limits and existing retry/cancellation behavior remain in effect. WebP saving applies to NAI output; local Anima output keeps its existing behavior. This does not add RS NAI reference-inset generation, portable character asset management or every upstream graph node. Inset metadata can be inspected but cannot be applied without the original reference canvas.

## Verification

- Full Python suite: **1,236 passed, 1 skipped**, including 35 new cases over v0.6.1.
- Synthetic upstream-writer audit: 12 combinations of regular generation, detailer with original context, current crop-only output and legacy last-crop metadata, each in PNG/lossless WebP/lossy WebP. Full-image context restores two characters; crop-only context is kept separate.
- Focused request tests cover WebP metadata round trips, conversion failure preserving PNG without another generation request, per-request timeout forwarding, detector selection, invalid input rejection and mixed-engine workflow inheritance.
- `browser_nai29_smoke.py` uses an isolated temporary app with synthetic images and blocks external requests/generation. It verifies selective import, missing-context handling, all three locales, workflow settings restoration and narrow/wide layouts. Firefox manual inspection also exercises the actual WebP upload and selective restoration.
- No live NAI generation or paid request is part of this update's acceptance. Detector inference quality with actual weights is not re-evaluated by these mock tests.

Reproduce from a prepared project environment:

```bash
python -m pytest -q
python -m ruff check src tests scripts
python scripts/verify_vendor.py
PYTHONPATH=src python scripts/browser_nai29_smoke.py
PYTHONPATH=src python scripts/browser_generation_smoke.py
PYTHONPATH=src python scripts/browser_locale_smoke.py
python scripts/package_dry_run.py
```

Browser artifacts go under `outputs/nai29-browser/` by default and stay outside distribution. The original baseline audit is private/local under `outputs/nai-2.9.0-audit/`; keep its baseline results distinct from verification of these changes. The source license and attribution are recorded in [NOTICE](../NOTICE.md) and [references](REFERENCES.md).
