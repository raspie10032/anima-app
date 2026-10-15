/* One preparation screen. Existing form nodes retain their values and listeners. */
(() => {
  const $ = selector => document.querySelector(selector);
  const tr = (...args) => window.AppI18n.msg(...args);
  const node = (tag, text = '', cls = '') => {
    const result = document.createElement(tag); result.className = cls;
    if (text) window.AppI18n.setText(result, tr(text));
    return result;
  };
  const button = (text, action, id) => {
    const result = node('button', text, 'secondary-button'); result.type = 'button';
    if (id) result.id = id;
    result.addEventListener('click', () => Promise.resolve().then(action).catch(error => {
      feedback.textContent = error.message; feedback.setAttribute('role', 'alert');
    })); return result;
  };
  const request = async (route, data) => {
    const response = await fetch('/api/setup/' + route, data === undefined ? {cache: 'no-store'} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    const result = await response.json(); if (!response.ok) throw new Error(tr(result.error || String(response.status)));
    return result;
  };
  const css = node('style'); css.textContent = `
    #setup-dialog{width:min(970px,94vw);max-height:92vh;padding:24px;color:#eef1f7;background:#171d29;border:1px solid #485369;border-radius:16px;box-sizing:border-box;overflow:auto}
    #setup-dialog::backdrop{background:#080d18c9} .setup-top{display:flex;align-items:center;justify-content:space-between;gap:16px}.setup-top h2{margin:0;flex:1}.setup-top button{width:auto;min-width:80px}
    .setup-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:18px 0}.setup-card{min-width:0;padding:18px;border:1px solid #424b5c;border-radius:12px;background:#1c2432}
    .setup-card h3{margin:0 0 12px}.setup-card p{font-size:13px;line-height:1.6;overflow-wrap:anywhere}.setup-card input{box-sizing:border-box;width:100%}.setup-card button{margin:6px 0;width:100%;white-space:normal;min-height:42px}
    .setup-state{padding:8px 10px;border-radius:8px;background:#28374b;min-height:24px}.setup-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.setup-toolbar button{flex:1;min-height:38px}
    #setup-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}#setup-message{min-height:20px}#setup-banner{font-size:13px;padding:8px 0}
    .setup-size-presets{display:flex;gap:6px}.setup-size-presets button{flex:1;font-size:12px;min-width:0}
    .setup-nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}.setup-nav button{width:auto;flex:1;min-height:40px}.setup-nav button[aria-pressed="true"]{border-color:#94b9ff;background:#304568;color:#fff}
    .setup-models{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:16px 0}.setup-models[hidden]{display:none}
    .setup-file{margin:10px 0;padding:8px;background:#141d2a;border-radius:6px;font-size:12px;overflow-wrap:anywhere}.setup-file code{white-space:normal}.setup-file a{display:inline-block;margin:6px 0}
    .setup-card a{color:#b6d1ff;overflow-wrap:anywhere}.setup-switch{display:flex;gap:10px;align-items:center;font-weight:bold;padding:10px 0}.setup-card .setup-switch input{width:20px;height:20px;flex:none}.setup-models .setup-card{padding:14px}
    .setup-references{display:grid;gap:10px;margin:16px 0}.setup-references[hidden]{display:none}.setup-references p{margin:6px 0}
    body.setup-simple .setup-advanced{display:none!important}body.setup-simple [data-control-group="model-style"]>summary::after{content:' +'}
    @media(max-width:780px){.setup-grid,.setup-models{grid-template-columns:1fr}#setup-dialog{padding:16px}.setup-top{align-items:flex-start}}
  `; document.head.append(css);
  const modal = node('dialog'); modal.id = 'setup-dialog'; modal.setAttribute('aria-labelledby', 'setup-title');
  const heading = node('h2', '연결 · 준비'); heading.id = 'setup-title';
  const top = node('div', '', 'setup-top'); top.append(heading, button('닫기', () => modal.close(), 'setup-close'));
  const feedback = node('p'); feedback.id = 'setup-message'; feedback.setAttribute('role', 'status');
  const grid = node('div', '', 'setup-grid');
  const makeCard = (title, description) => {
    const card = node('section', '', 'setup-card'), state = node('p', '확인 중', 'setup-state');
    card.append(node('h3', title), node('p', description), state); grid.append(card); return {card, state};
  };
  const nai = makeCard('NAI로 생성', '토큰을 넣으면 NovelAI로 생성할 수 있습니다.');
  const token = node('input'); token.id = 'setup-nai-token'; token.type = 'password'; token.autocomplete = 'off'; token.maxLength = 4096;
  const tokenLabel = node('label', 'NAI 액세스 토큰'); tokenLabel.htmlFor = token.id;
  const persist = node('input'); persist.id = 'setup-persist-token'; persist.type = 'checkbox'; persist.style.width = 'auto';
  const persistLabel = node('label'); persistLabel.append(persist, node('span', '이 PC에 저장 (다음 실행에도 사용)'));
  let persistDirty = false;
  persist.addEventListener('change', () => {persistDirty = true;});
  const storageState = node('p'); storageState.id = 'setup-token-storage';
  const help = node('a', '토큰 발급 위치 열기'); help.href = 'https://novelai.net/'; help.target = '_blank'; help.rel = 'noopener noreferrer';
  nai.card.append(tokenLabel, token, node('p', 'NovelAI → User Settings → Account → Get Persistent API Token'), help, persistLabel, storageState,
    button('토큰 적용', async () => {
      const value = token.value; token.value = '';
      await request('nai', {...(value.trim() ? {token: value} : {use_current: true}), persist: persist.checked});
      persistDirty = false;
      window.AppI18n.setText(feedback, tr(persist.checked ? '토큰을 이 PC에 저장하고 적용했습니다.' : '토큰을 현재 앱에 적용했습니다.'));
      window.dispatchEvent(new Event('anima-setup-changed')); await refresh();
    }, 'setup-save-token'), button('토큰 지우기', async () => {
      token.value = ''; await request('nai', {token: ''}); persistDirty = false;
      window.AppI18n.setText(feedback, tr('토큰을 지웠습니다.'));
      window.dispatchEvent(new Event('anima-setup-changed')); await refresh();
    }, 'setup-clear-token'), node('p', '기본은 실행 PC의 휘발성 메모리에만 보관하며, 앱을 종료하면 사라집니다. 이 PC에 저장을 선택하면 운영체제 자격증명 저장소에 보관하고 다음 실행에 복원합니다.'),
    node('p', '토큰 지우기는 현재 연결과 이 화면에서 저장한 토큰을 함께 지웁니다. 배럭 계정은 배럭에서 별도로 관리합니다.'));
  const local = makeCard('Anima로 생성 · 보정', '로컬 모델을 준비하면 생성과 디테일러를 사용할 수 있습니다.');
  const modelButtons = [];
  for (const [profile, title] of [['anima-t2i','기본 모델 준비'],['anima-aesthetic-v1.1','Aesthetic 모델 준비'],['face-detailer-detectors','얼굴 검출 모델 준비']]) {
    const action = button(title, async () => {await request('anima/prepare', {profile}); await refresh();}, 'setup-' + profile);
    modelButtons.push(action); local.card.append(action);
  }
  local.card.append(node('p', '기존 모델을 먼저 확인하고, 없으면 다운로드합니다. 기본 모델은 수 GB가 필요합니다.'));
  const vision = makeCard('이미지로 유사사례 찾기', '캡션 없이 그림만 넣어도 검색할 수 있습니다.');
  const vrsToggle = node('input'); vrsToggle.type = 'checkbox'; vrsToggle.id = 'setup-vrs-enabled'; vrsToggle.setAttribute('role', 'switch');
  const vrsLabel = node('label', '', 'setup-switch'); vrsLabel.htmlFor = vrsToggle.id;
  vrsLabel.append(vrsToggle, node('span', 'VRS 이미지 검색 사용'));
  let changingVrs = false;
  vrsToggle.addEventListener('change', async () => {
    changingVrs = true; vrsToggle.disabled = true;
    try {
      const result = await request('vrs/settings', {enabled: vrsToggle.checked});
      snapshot.vrs.enabled = result.enabled;
      window.AppI18n.setText(feedback, tr(result.enabled ? 'VRS를 켰습니다. 준비된 색인을 그대로 사용합니다.' : 'VRS를 껐습니다. 이미지·색인·평가는 보존됩니다.'));
      window.dispatchEvent(new Event('anima-setup-changed'));
      await refresh();
    } catch (error) {feedback.textContent = error.message;}
    finally {changingVrs = false; render();}
  });
  vision.card.append(vrsLabel, node('p', '끄면 VRS 검색·색인·인코더 준비를 멈추고 대기 중인 인코더 메모리를 비웁니다. 기본 이미지 검색과 보관은 계속 사용할 수 있습니다. 선택은 다음 실행에도 유지됩니다.'));
  const coreState = node('p'); coreState.id = 'setup-core-state';
  const prepare = button('이미지 인코더 준비', async () => {await request('vrs/prepare', {}); await refresh();}, 'setup-vrs-prepare');
  const cancel = button('인코더 준비 취소', async () => {await request('vrs/cancel', {}); await refresh();}, 'setup-vrs-cancel');
  const index = button('등록한 이미지 색인', async () => {
    const response = await fetch('/api/library/import', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind:'vrs'})});
    const result = await response.json(); if (!response.ok) throw new Error(result.error); await refresh();
  }, 'setup-vrs-index');
  const stopIndex = button('색인 취소', async () => {
    await fetch('/api/library/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}); await refresh();
  }, 'setup-index-cancel');
  vision.card.append(coreState, prepare, cancel, index, stopIndex,
    node('p', '인코더 코드와 SWEGCA 코어가 포함되어 있습니다. 비전 가중치 약 320 MiB와 실행 패키지만 내려받습니다. VRS 인코딩에는 CUDA가 필요합니다.'));
  const diagnostic = node('details'), diagnosticText = node('pre');
  diagnostic.append(node('summary', '준비 상태 · 오류 진단'), diagnosticText,
    button('파일별 문제 확인', async () => {diagnosticText.textContent = JSON.stringify(await request('diagnostics'), null, 2);}, 'setup-diagnostics'));
  const connections = node('section'); connections.id = 'setup-connections'; connections.append(grid, diagnostic);
  const models = node('section', '', 'setup-models'); models.id = 'setup-models'; models.hidden = true;
  const references = node('section', '', 'setup-references'); references.id = 'setup-references'; references.hidden = true;
  const nav = node('nav', '', 'setup-nav'); window.AppI18n.setAttribute(nav, 'aria-label', tr('설정 항목'));
  let activePanel = 'connections', catalog = null;
  const panels = {connections, models, references}, panelButtons = {};
  const showPanel = async key => {
    activePanel = key;
    for (const [name, panel] of Object.entries(panels)) {panel.hidden = name !== key; panelButtons[name].setAttribute('aria-pressed', String(name === key));}
    if (key !== 'connections') {catalog = await request('catalog'); renderCatalog();}
  };
  for (const [key, label] of [['connections','연결 · 기능'],['models','필요 모델'],['references','레퍼런스']]) {
    const action = button(label, () => showPanel(key), 'setup-tab-' + key);
    action.setAttribute('aria-controls', panels[key].id); action.setAttribute('aria-pressed', String(key === activePanel));
    panelButtons[key] = action; nav.append(action);
  }
  const link = (label, url) => {const a = node('a', label); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;};
  const renderCatalog = () => {
    if (!catalog) return;
    models.replaceChildren(); references.replaceChildren();
    for (const group of catalog.groups) {
      const card = node('article', '', 'setup-card'); card.dataset.modelGroup = group.id;
      card.append(node('h3', group.title), node('p', group.description), node('p', group.ready ? '준비 완료' : '준비 필요', 'setup-state'));
      for (const file of group.files) {
        const row = node('div', '', 'setup-file');
        row.append(node('code', file.relative_path), node('p', ({ready:'파일 확인 완료',missing:'파일 없음',invalid:'파일 확인 필요',present:'파일 확인 필요'})[file.status]), link('모델 원본 보기', file.source));
        card.append(row);
      }
      if (group.action) card.append(button('준비 화면으로', async () => {
        await showPanel('connections');
        const target = group.action === 'nai' ? token : group.action === 'vrs' ? vrsToggle : $('#setup-' + group.action);
        target?.scrollIntoView({block:'center'}); target?.focus();
      }));
      models.append(card);
    }
    const location = node('p'); window.AppI18n.setText(location, tr`모델 저장 위치: ${catalog.model_root}`); models.append(location);
    models.append(node('p', 'LoRA는 화풍을 추가할 때만 필요합니다. WD/PixAI 태거는 태그 분석용이며 VRS 검색에 필요하지 않습니다.'));
    for (const item of catalog.references) {
      const card = node('article', '', 'setup-card'); card.append(link(item.title, item.url), node('p', item.description)); references.append(card);
    }
  };
  modal.append(top, node('p', '사용할 기능만 준비하세요. 프롬프트와 생성 설정은 그대로 유지됩니다.'), nav, connections, models, references, feedback);
  document.body.append(modal);
  let snapshot = null, fetching = false, opener;
  const refresh = async () => {
    if (fetching) return; fetching = true;
    try {snapshot = await request('status'); render(); if (activePanel === 'models') {catalog = await request('catalog'); renderCatalog();}} finally {fetching = false;}
  };
  const render = () => {
    if (!snapshot) return;
    const {vrs, core, library, model_job: modelJob} = snapshot;
    const enabled = vrs.enabled !== false;
    if (!changingVrs) vrsToggle.checked = enabled;
    vrsToggle.disabled = changingVrs;
    window.AppI18n.setText(nai.state, tr(snapshot.nai.configured ? '토큰 입력됨' : '토큰을 입력해 주세요.'));
    if (!persistDirty) persist.checked = Boolean(snapshot.credentials?.default_saved);
    persist.disabled = !snapshot.credentials?.available;
    window.AppI18n.setText(storageState, tr(snapshot.credentials?.error || (!snapshot.credentials?.available
      ? '이 PC의 자격증명 저장소를 사용할 수 없습니다. 잠금 해제 후 다시 시도해 주세요.'
      : snapshot.credentials.default_saved ? '이 PC에 저장됨' : '실행 중에만 보관')));
    window.AppI18n.setText(local.state, tr(modelJob.status === 'running' ? '모델 준비 중' : snapshot.anima.generation.ready ? '생성 준비 완료' : '모델 준비 필요'));
    modelButtons.forEach((b, i) => {
      const profile = ['anima-t2i','anima-aesthetic-v1.1','face-detailer-detectors'][i];
      const ready = snapshot.anima.profiles.find(p => (p.name || p.profile) === profile)?.ready;
      b.disabled = modelJob.status === 'running' || Boolean(ready);
      b.dataset.ready = String(Boolean(ready));
    });
    window.AppI18n.setText(coreState, tr(core.ready ? 'SWEGCA 코어 · 내장 / 실행 확인' : 'SWEGCA 코어 확인 필요'));
    const indexing = library.job.status === 'running';
    window.AppI18n.setText(vision.state, () => !enabled ? tr('VRS 꺼짐 · 기본 이미지 검색 사용 가능') : vrs.job.status === 'running'
      ? tr`인코더 준비 중 · ${Math.round(100*(vrs.job.received_bytes || 0)/(vrs.job.total_bytes || 1))}%`
      : !vrs.cuda ? tr('CUDA 없음 · 기본 이미지 검색을 사용할 수 있습니다.')
      : !vrs.ready ? tr('인코더 준비 필요')
      : tr`검색 가능 ${library.vrs_indexed}장 · 대기 ${library.vrs_pending}장`);
    prepare.disabled = !enabled || vrs.job.status === 'running' || indexing || modelJob.status === 'running';
    cancel.hidden = vrs.job.status !== 'running';
    index.disabled = !enabled || !vrs.ready || indexing || modelJob.status === 'running'; stopIndex.hidden = !indexing;
    const errors = [vrs.job.status === 'failed' ? vrs.job.error : '', modelJob.status === 'failed' ? modelJob.error : '', library.job.message].filter(Boolean);
    if (errors.length) feedback.textContent = errors.join('\n');
    diagnosticText.textContent = JSON.stringify({vrs, core, library, modelJob}, null, 2);
  };
  const open = () => {opener = document.activeElement; if (!modal.open) modal.showModal(); refresh().catch(e => {feedback.textContent=e.message;});};
  modal.addEventListener('close', () => {token.value=''; persistDirty=false; opener?.focus();});
  window.addEventListener('anima-setup-open', open);
  window.addEventListener('anima-locale-change', render);
  const toolbar = node('div', '', 'setup-toolbar');
  const launch = button('연결 · 준비', open, 'open-setup');
  let simple = true;
  try {simple = localStorage.getItem('anima.generation.view') !== 'advanced';} catch (_) { /* private mode */ }
  const toggle = button('고급 설정 보기', () => {
    simple = !simple; updateView(); try {localStorage.setItem('anima.generation.view', simple ? 'simple' : 'advanced');} catch (_) { /* private mode */ }
  }, 'setup-view-toggle');
  toolbar.append(launch, toggle); $('.generation-controls-scroll').prepend(toolbar);
  const size = $('[data-control-group="image-settings"] .form-section');
  const sizes = node('div', '', 'setup-size-presets');
  for (const [label, width, height] of [['세로',768,1024],['정사각',1024,1024],['가로',1024,768]]) {
    sizes.append(button(label, () => {
      for (const [id, value] of [['width',width],['height',height]]) {const input=$('#'+id);input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));}
    }, 'setup-size-' + width + '-' + height));
  } size.prepend(sizes);
  const promptTools = node('details'); promptTools.className='setup-prompt-tools';
  promptTools.append(node('summary', '가중치 · 작가 표기 · 초안'));
  const authoring = $('#authoring-panel'); authoring.before(promptTools); promptTools.append(authoring);
  for (const selector of ['#local-sampling-controls','#local-memory-controls','.preset-strip','#generation-queue']) $(selector)?.classList.add('setup-advanced');
  $('#steps').closest('.row').classList.add('setup-advanced');
  for (const n of [$('#seed'), $('label[for="seed"]')]) n.classList.add('setup-advanced');
  function updateView() {
    document.body.classList.toggle('setup-simple', simple);
    promptTools.open = !simple;
    window.AppI18n.setText(toggle, tr(simple ? '고급 설정 보기' : '간단히 보기'));
    toggle.setAttribute('aria-pressed', String(!simple));
  }
  updateView();
  // Never poll a closed dialog; opening it gives a fresh state.
  setInterval(() => {if (modal.open && !document.hidden) refresh().catch(e => {feedback.textContent=e.message;});}, 2500);
})();
