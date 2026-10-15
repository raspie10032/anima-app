"""Read-only setup inventory from the same profiles used by model preparation."""
from pathlib import Path

from anima_app.assets import ANIMA_T2I_HF_REPO, ANIMA_T2I_HF_SUBFOLDER, DETECTOR_REMOTE_ASSETS
from anima_app.embedded_vrs import MODEL


PROFILES = {
    'anima-t2i': ('Anima Base · 기본 생성', '기본 생성 모델과 공용 텍스트 인코더·VAE입니다. NAI만 사용하면 필요 없습니다.'),
    'anima-aesthetic-v1.1': ('Anima Aesthetic · 선택', '다른 화풍의 생성 모델입니다. 기본 모델의 텍스트 인코더·VAE를 함께 사용합니다.'),
    'face-detailer-detectors': ('얼굴·눈 디테일러 · 선택', '얼굴·눈 위치와 마스크를 찾습니다. 디테일러를 사용할 때 준비하세요.'),
    'sam3-detector': ('SAM3 · 선택', '텍스트로 지정한 대상을 분할할 때만 필요합니다. 고급 설정의 SAM3 준비에서 접근 권한과 실행 패키지를 확인하세요.'),
}

REFERENCES = [
    ('Anima APP · 사용 가이드', '생성부터 디테일러 연결까지 따라하기', 'https://github.com/raspie10032/anima-app#readme'),
    ('Anima · 모델 원본', '모델 파일·권장 설정·작가 표기', 'https://huggingface.co/circlestone-labs/Anima'),
    ('NovelAI · 공식 설명서', '이미지 생성·참조 이미지·프롬프트 가중치', 'https://docs.novelai.net/en/image/'),
    ('NAI 연동 · 원본 프로젝트', 'NAI 요청·변환·디테일러 구현 참고', 'https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request'),
    ('VRS · 비전 가중치 원본', '이미지 검색에 사용하는 비전 인코더 출처', f"https://huggingface.co/{MODEL['model']}/tree/{MODEL['model_revision']}"),
    ('VRS · 이미지 전처리 원본', '이미지를 인코더 입력으로 바꾸는 설정', f"https://huggingface.co/{MODEL['processor']}/tree/{MODEL['processor_revision']}"),
    ('WD Tagger · 선택 기능', '이미지 태그 분석 모델 원본', 'https://huggingface.co/SmilingWolf/wd-vit-tagger-v3'),
    ('PixAI Tagger · 선택 기능', '이미지 태그 분석 모델 원본', 'https://huggingface.co/pixai-labs/pixai-tagger-v1.0'),
    ('SWEGCA Architecture', 'SWEGCA · 내장 코어', 'https://github.com/raspie10032/SWEGCA-Architecture/tree/5901a5aa2dcbd0ac7ad12ac6dd745699f72288a8'),
]


def catalog(paths, snapshot):
    groups = [{
        'id': 'nai', 'title': 'NovelAI · 로컬 모델 불필요',
        'description': 'NAI 토큰만 연결하면 됩니다. Anima 디테일러를 붙일 때는 로컬 모델도 준비하세요.',
        'ready': snapshot['nai']['configured'], 'files': [], 'action': 'nai',
    }]
    for profile in snapshot['anima']['profiles']:
        name = profile['name']
        if name not in PROFILES:
            continue
        files = []
        for entry in profile['files']:
            remote = DETECTOR_REMOTE_ASSETS.get(Path(entry['relative_path']))
            if remote:
                source = remote.url or f'https://huggingface.co/{remote.repo_id}/blob/main/{remote.filename}'
            else:
                source = f"https://huggingface.co/{ANIMA_T2I_HF_REPO}/blob/main/{ANIMA_T2I_HF_SUBFOLDER}/{entry['relative_path']}"
            files.append({**entry, 'source': source})
        title, description = PROFILES[name]
        groups.append({'id': name, 'title': title, 'description': description,
                       'ready': profile['ready'], 'files': files,
                       'action': name if name != 'sam3-detector' else None})
    vision = snapshot['vrs']
    groups.append({
        'id': 'vrs', 'title': 'VRS · 이미지 인코더',
        'description': '이미지로 유사사례를 찾을 때 필요합니다. 비전 가중치 약 320 MiB, CUDA 필요. 캡션 모델은 필요 없습니다.',
        'ready': vision['ready'], 'action': 'vrs',
        'files': [{'relative_path': f'vrs/gemma4-vision/{name}', 'path': str(Path(vision['directory']) / name),
                   'status': 'ready' if vision['weights_ready'] else 'present' if (Path(vision['directory']) / name).is_file() else 'missing',
                   'source': REFERENCES[5 if name == 'preprocessor_config.json' else 4][2]} for name in MODEL['files']],
    })
    groups.append({
        'id': 'core', 'title': 'SWEGCA · 내장 코어',
        'description': '검색 사례와 명시적 사용자 평가의 근거를 처리합니다. 추가 모델 다운로드는 없습니다.',
        'ready': snapshot['core']['ready'], 'files': [], 'action': None,
    })
    return {'model_root': str(paths.model_root), 'groups': groups,
            'references': [{'title': title, 'description': description, 'url': url}
                           for title, description, url in REFERENCES]}
