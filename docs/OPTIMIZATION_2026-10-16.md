# REA 분석 후 최적화 · 2026-10-16

기준 커밋: `5b3bf251eaeb48b55b160c1f797bc6cb1b256605`. 분석 보고서의 동작 문제, 조회·전송 비용, 런타임 재사용 순서로 수정했다. 라이브러리 총 등록 수는 제한하지 않는다. 개인 이미지·토큰·DB·생성 결과·벤치마크 원본은 공개 소스에 포함하지 않는다.

## 사용자가 확인할 변화

- 자동 메모리 설정이 해상도·업스케일 여부·배율·스텝을 바꾸지 않는다. 8GB급 또는 VRAM 정보가 없는 환경에서는 `low_vram`을 선택해 필요한 타일 처리만 적용한다. 기존 자동 판정 캐시는 버전을 올려 재판정한다.
- **저VRAM · 크기 유지**를 직접 선택할 수 있다. **저VRAM 고해상도**는 사용자가 명시적으로 선택할 때만 기존 고해상도 프리셋을 적용한다.
- 즐겨찾기·태그·메모를 바꾼 뒤에도 검색 행렬을 재사용한다. 이미지·벡터가 바뀌면 다시 만든다.
- NAI 단독 T2I는 로컬 GPU 잠금을 잡거나 VRS 인코더를 해제하지 않는다. 로컬 후처리·NAI 디테일러 등은 GPU 사용 보호를 유지한다.
- 큐·진행 상태는 이전 조회가 끝난 후 다시 확인한다. 이전 조회 세션의 응답과 이미 완료된 진행 ID를 통한 역행을 막는다.
- 이력 더 보기는 기존 카드 DOM을 유지하고 새 카드만 추가한다. 완료 결과를 불러올 때 모델 목록 전체를 재검사하지 않는다.
- 같은 모델·LoRA·프롬프트로 연속 생성할 때 준비 결과를 재사용한다. 모델·LoRA 파일, 순서·강도, 임베딩 또는 GPU가 달라지면 무효화한다. VRS 등 다른 GPU 사용자가 들어오면 로컬 캐시를 해제한다.
- PNG 생성 조건을 갱신할 때 압축된 픽셀을 다시 인코딩하지 않는다. 알파·다른 메타데이터와 IDAT 데이터는 보존한다.

## 분석 항목별 반영

| ID | 변경 |
|---|---|
| G3 | `auto → low_vram` 판정, 요청 재구성 후에도 작업 조건 보존, 기존 명시적 고해상도 프리셋 유지 |
| F1 | 큐·진행 조회 각각 단일 진행 요청, 조회 세션 번호, 완료 ID 보존 |
| L1 | 자산 UPDATE 트리거는 검색 벡터 관련 열 변경에만 행렬 무효화 |
| G2 | 순수 NAI T2I GPU 잠금 우회; 후처리·로컬 작업은 계속 보호 |
| L3 | 자산 최신순 목록 및 원본 경로의 자산 ID 인덱스 |
| L2 | 순위 계산 시 필요한 작은 열만 먼저 읽고, 선택된 결과의 상세 정보만 조회 |
| F3 | `GET /api/jobs?view=summary`에서 상태·단계 구성만 전송, 새 완료 결과는 상세 API로 한 번 조회 |
| F2 | 이력 카드 DOM 재사용과 추가분 렌더링 |
| F4 | 완료 시 저장 공간·이력만 갱신; 모델 상태 조회는 필요 시 유지 |
| L4 | 목록·상세 기록 묶음 조회, 평가 묶음 조회, revision 기반 통계 캐시 |
| G1 | 모델 컨텍스트 한 개, 텍스트 조건 최대 8개 재사용; 반환 조건은 소비자 변경에서 격리 |
| G4 | 로컬 디테일러 검출기 한 세트 재사용, 파일 변경·GPU 사용자 전환 시 무효화 |
| G5 | PNG 텍스트 청크만 교체하고 임시 파일을 원자적으로 대체; 중복 출력 검증 제거 |
| G6 | 서버·CLI에서 렌더러 및 근거 엔진을 필요할 때 불러오기 |
| F5 | 정적 JS/CSS gzip, 표현별 ETag·304, `Vary: Accept-Encoding`; API는 기존 비캐시 동작 |

`GET /api/jobs`의 기존 전체 응답과 개별 작업 API는 유지한다. 요약 모드는 요청 프롬프트·결과 본문을 생략하고 `has_result`를 제공한다. 브라우저가 상세 결과를 아직 받지 못한 경우 다음 조회에서 재시도할 수 있다.

## 측정

4,482장 메타데이터·벡터 DB 사본을 사용했다. 분석 중 만들었던 임시 인덱스는 양쪽 사본에서 제거했고, 수정 버전은 자체 마이그레이션으로 인덱스를 추가했다. NumPy 계산 스레드는 두 조건 모두 1개로 고정했다. 검색·목록·상태는 15회 중앙값이다.

| 항목 | 수정 전 | 수정 후 | 범위 |
|---|---:|---:|---|
| 48개 목록 조회 | 18.80ms | 1.02ms | 같은 DB 사본 |
| VRS 준비 후 검색 | 21.87ms | 11.04ms | 등록 이미지 질의, 인코더 실행 제외 |
| 즐겨찾기 수정 직후 검색 | 604.04ms | 10.35ms | 5회 중앙값 |
| 라이브러리 상태 조회 | 8.30ms | 0.17ms | revision이 동일한 통계 재사용 |
| 큐 JSON 크기 | 2,005,853 bytes | 28,343 bytes | 긴 프롬프트의 합성 128개 작업 |
| PNG 생성 조건 기록 | 334.36ms | 5.25ms | 2048² 합성 이미지, 5회; 최초 이미지 저장 제외 |
| Anima 두 번째 생성 | 2.19초 | 0.55초 | 512²·4스텝·고정 시드, 각 1회 관찰 |

등록 질의 12개 × 유사도/다양성 정렬 2종 = 24개 비교에서 질의 ID를 제외한 전체 결과 JSON 해시가 일치했다. 사용자 평가·다른 DB 연결에서의 변경 반영은 회귀 검사로 별도 확인했다.

프로세스 최초 VRS 검색은 0.615초에서 1.164초로 늘었다. 서버 import 때 하던 근거 엔진 초기화를 최초 사용 시점으로 옮긴 영향이 포함되므로, 준비 후 검색 시간과 구분한다. 파일 캐시·GPU 초기화가 포함된 첫 생성도 일반적인 속도 향상 수치로 쓰지 않는다.

실제 GPU 검증은 기본 모델 두 번, 설치된 스타일 LoRA 두 번, 기본 모델 복귀 한 번을 수행했다. 수정 전 코드로 기본 모델을 두 번 더 생성해 총 7회 비교했다. 고정 시드의 기본 모델 결과는 수정 전·후·LoRA 제거 후 픽셀 SHA-256이 일치하고, LoRA 반복 결과도 일치했다. 이는 짧은 smoke 조건이며 모든 모델·해상도·GPU 조합의 속도나 동일성을 보증하지 않는다.

검출기 재사용과 GPU 사용자 전환 시 캐시 해제는 모의 객체를 사용한 회귀 검사로 확인했다. 이번에는 디테일러 실생성이나 NAI 유료 API 생성을 반복하지 않았다.

## 재현과 검증 자료

프로젝트 Python 환경에서 실행한다.

```bash
.venv/bin/python -m ruff check src tests scripts
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python scripts/browser_optimization_smoke.py
PYTHONPATH=src .venv/bin/python scripts/browser_queue_seed_smoke.py
PYTHONPATH=src .venv/bin/python scripts/browser_generation_smoke.py
PYTHONPATH=src .venv/bin/python scripts/browser_library_smoke.py
PYTHONPATH=src .venv/bin/python scripts/browser_provider_settings_smoke.py
PYTHONPATH=src .venv/bin/python scripts/browser_locale_smoke.py
PYTHONPATH=src .venv/bin/python scripts/verify_vendor.py
```

로컬 결과: `outputs/rea-optimization-20261016/`. 성능 비교 JSON, 픽셀 비교, 브라우저 검사, 전체 회귀 로그와 완료 기록을 보관한다. 라이브러리 원본을 성능 실험에 직접 수정하지 않는다.

전체 Python 회귀 검사 1,274개 통과·1개 건너뜀, 기능별 브라우저 검사 66개 통과. 실행 앱 재시작 전 DB를 백업하고 이미지 4,482장과 기존 벡터·기록 테이블의 행 수·내용 해시를 비교한다. 로컬 앱의 최신 스크립트와 gzip·ETag·304 응답도 별도로 확인한다.

## English

Automatic memory selection now preserves the requested workload. The new `low_vram` profile tiles existing work without enabling upscale or changing size/steps; the explicit high-resolution preset remains available. Retrieval matrices survive annotations, database indexes and batched queries reduce lookup costs, and revision-keyed counts avoid repeated statistics scans. Queue/progress polling rejects stale responses and uses compact summaries with a separate result fetch. History appends retain existing DOM nodes.

One local model context and up to eight isolated conditioning entries are reused. Model/LoRA/embedding changes invalidate reuse, and another GPU owner releases the local context. PNG metadata updates preserve the original compressed pixel data. Static assets support gzip and ETag revalidation. Pure NAI T2I does not reserve the local GPU; mixed/local workflows still do.

The table above reports local measurements, not general GPU performance guarantees. Twenty-four retrieval comparisons returned identical result JSON, and seven real short Anima generations verified pixel equivalence across old/new code, repeated runs and LoRA removal. Detector reuse/GPU handoff used mocks; no new paid NAI generation was performed.

## 日本語

自動メモリ設定は解像度・アップスケールの有効状態・倍率・ステップを維持します。新しい「低VRAM・サイズ維持」は既存処理のタイル化だけを調整し、高解像度プリセットは明示的な選択時に適用します。お気に入り変更後の検索キャッシュ、まとめたDB取得、キュー応答、履歴表示、連続生成時のモデル再利用を改善しました。別のGPU処理に切り替えるとローカルキャッシュを解放します。PNGの圧縮済み画素と他のメタデータは保持します。上記の測定値は限定条件のローカル検証です。
