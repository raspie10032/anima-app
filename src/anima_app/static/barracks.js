/* A finite NAI T2I batch; token inputs never touch drafts or browser storage. */
(() => {
  const tr = (...args) => window.AppI18n.msg(...args);
  const node = (tag, text = '') => {
    const el = document.createElement(tag);
    if (text) window.AppI18n.setText(el, tr(text));
    return el;
  };
  const call = async (route, data) => {
    const response = await fetch('/api/barracks/' + route, data === undefined ? {cache:'no-store'} : {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const value = await response.json();
    if (!response.ok) throw new Error(tr(value.error || '배럭 설정을 확인해 주세요.'));
    return value;
  };
  const message = node('p'); message.id = 'barracks-message'; message.setAttribute('role','status');
  const button = (text, id, action) => {
    const el = node('button', text); el.id = id; el.type = 'button'; el.className = 'secondary-button';
    el.addEventListener('click', async () => {
      el.disabled = true; message.textContent = '';
      try {await action();} catch (error) {message.textContent = error.message;}
      finally {el.disabled = false; syncDisabled();}
    }); return el;
  };
  const css = node('style'); css.textContent = `
    #barracks-dialog{width:min(900px,94vw);max-height:92vh;padding:24px;box-sizing:border-box;overflow:auto;background:#171d29;color:#eef1f7;border:1px solid #485369;border-radius:16px}
    #barracks-dialog::backdrop{background:#080d18c9}#barracks-dialog h2{margin:0}
    #barracks-dialog .barracks-top,#barracks-dialog .barracks-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
    #barracks-dialog .barracks-top{justify-content:space-between}#barracks-dialog button{width:auto;min-height:40px;white-space:normal}
    #barracks-dialog input,#barracks-dialog select{box-sizing:border-box;max-width:100%}#barracks-dialog label{margin:0}
    #barracks-dialog input[type=checkbox]{width:auto;margin-right:8px}#barracks-dialog p{overflow-wrap:anywhere;line-height:1.6}
    #barracks-dialog .barracks-field{flex:1;min-width:180px}#barracks-dialog .barracks-field input{width:100%}
    #barracks-accounts>div{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid #485369}
    #barracks-accounts label{overflow-wrap:anywhere;min-width:0}#barracks-preview{white-space:pre-wrap;overflow-wrap:anywhere;max-height:140px;overflow:auto}
    #barracks-results{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}#barracks-results img{width:100%;height:170px;object-fit:contain}
    #barracks-results article{padding:10px;border:1px solid #485369;border-radius:8px;min-width:0}#barracks-results p{font-size:12px;margin:4px 0}
    @media(max-width:480px){#barracks-dialog{padding:14px}.barracks-field{min-width:0!important;flex-basis:100%!important}}
  `; document.head.append(css);
  const dialog = node('dialog'); dialog.id = 'barracks-dialog'; dialog.setAttribute('aria-labelledby','barracks-title');
  const heading = node('h2', '배럭'); heading.id = 'barracks-title';
  const top = node('div'); top.className = 'barracks-top';
  top.append(heading, button('닫기','barracks-close', () => dialog.close()));
  const accounts = node('div'); accounts.id = 'barracks-accounts';
  const accountName = node('input'); accountName.id = 'barracks-account-name'; accountName.maxLength = 48; accountName.autocomplete = 'off';
  const token = node('input'); token.id = 'barracks-token'; token.type = 'password'; token.maxLength = 4096; token.autocomplete = 'off';
  const persist = node('input'); persist.id = 'barracks-persist-token'; persist.type = 'checkbox';
  const persistLabel = node('label'); persistLabel.append(persist, node('span','이 PC에 저장 (다음 실행에도 사용)'));
  const storageState = node('p'); storageState.id = 'barracks-storage-state';
  const field = (title, control) => {
    const wrap = node('div'); wrap.className = 'barracks-field'; const label = node('label', title); label.htmlFor = control.id;
    wrap.append(label, control); return wrap;
  };
  const row = (...items) => {const el = node('div'); el.className = 'barracks-row'; el.append(...items); return el;};
  const add = button('계정 추가','barracks-add-account', async () => {
    const value = token.value; token.value = '';
    state = await call('accounts', {name:accountName.value, token:value, persist:persist.checked}); accountName.value = ''; render();
  });
  const useCurrent = button('현재 NAI 토큰 추가','barracks-use-current', async () => {
    state = await call('accounts', {name:accountName.value || tr('주계정'), use_current:true, persist:persist.checked}); accountName.value = ''; render();
  });
  const count = node('input'); count.id = 'barracks-count'; count.type = 'number'; count.min = 1; count.max = 100; count.value = 4;
  const seeds = node('select'); seeds.id = 'barracks-seed-mode';
  for (const [value,label] of [['increment','시드 증가'],['random','매번 무작위'],['fixed','같은 시드']]) {
    const option = node('option',label); option.value = value; seeds.append(option);
  }
  const preview = node('pre'); preview.id = 'barracks-preview';
  const scope = '배럭은 NAI 텍스트→이미지 단독 생성만 지원합니다.';
  function requestFromForm() {
    const request = window.animaGenerationRequest();
    if (request.provider !== 'novelai' || (request.operation && request.operation !== 'generate') ||
        window.animaWorkflow?.snapshot().length || request.nai_detailer?.enabled ||
        request.nai_vibes?.length || request.nai_references?.length || request.input_image || request.mask_image) {
      throw new Error(tr(scope));
    }
    return request;
  }
  const start = button('배럭 시작','barracks-start', async () => {
    if (!count.checkValidity()) {count.reportValidity(); return;}
    const request = requestFromForm();
    const selected = Array.from(accounts.querySelectorAll('input:checked'), el => el.value);
    state = await call('start', {request, count:Number(count.value), seed_mode:seeds.value, account_ids:selected}); render();
  });
  const cancel = button('배럭 중지','barracks-stop', async () => {state = await call('cancel',{}); render();});
  const progress = node('p'); progress.id = 'barracks-progress'; progress.setAttribute('role','status');
  const accountProgress = node('p'); accountProgress.id = 'barracks-account-progress';
  const results = node('div'); results.id = 'barracks-results';
  dialog.append(top, node('p',scope), node('p','메인 화면의 NAI 프롬프트와 생성 조건을 사용합니다. 계정마다 한 장씩 나누어 생성합니다.'),
    node('h3','배럭 계정'), accounts,
    row(field('계정 이름',accountName), field('NAI 액세스 토큰',token)), persistLabel, row(add,useCurrent), storageState,
    node('p','기본은 실행 PC의 휘발성 메모리에만 보관하며, 앱을 종료하면 사라집니다. 이 PC에 저장을 선택하면 운영체제 자격증명 저장소에 보관하고 다음 실행에 복원합니다.'),
    node('p','저장 해제는 다음 실행부터 복원하지 않습니다. 삭제는 현재 계정과 저장된 토큰을 함께 지웁니다.'),
    node('h3','현재 생성 조건'), preview, row(field('생성 장수',count),field('시드 방식',seeds)),
    row(start,cancel), message, progress, accountProgress,
    node('p','중지하면 다음 전송을 멈추고, 이미 요청한 결과는 도착하는 대로 저장합니다. 결과는 생성 이력에서도 볼 수 있습니다.'), results);
  document.body.append(dialog);
  let state = null, roster = '', resultVersion = '', polling = false, opener;
  function syncDisabled() {
    const busy = state?.batch?.status === 'running';
    start.disabled = busy || !state?.accounts.length;
    cancel.disabled = !busy;
    for (const el of [add,useCurrent,token,accountName,count,seeds,...accounts.querySelectorAll('input,button')]) el.disabled = busy;
    persist.disabled = busy || !state?.credentials?.available;
    for (const el of accounts.querySelectorAll('[data-storage]')) el.disabled = busy || !state?.credentials?.available;
    if (!busy) useCurrent.disabled = !state?.current_token_available;
  }
  const statuses = {queued:'대기',running:'진행 중',ready:'대기',completed:'완료',failed:'실패',paused:'계정 확인 필요',cancelled:'취소됨',blocked:'실행할 계정 없음'};
  function render() {
    if (!state) return;
    const newRoster = JSON.stringify(state.accounts);
    if (newRoster !== roster) {
      const previous = new Map(Array.from(accounts.querySelectorAll('input'), e => [e.value,e.checked]));
      accounts.replaceChildren();
      for (const account of state.accounts) {
        const wrap = node('div'), label = node('label'), check = node('input'); check.type = 'checkbox'; check.value = account.id;
        check.checked = previous.get(account.id) ?? true;
        label.append(check, document.createTextNode(account.name + ' · ' + tr(account.saved ? '이 PC에 저장됨' : '실행 중에만 보관')));
        const remove = button('삭제','barracks-remove-'+account.id,async () => {state = await call('accounts/remove',{id:account.id});render();});
        const storage = button(account.saved ? '저장 해제' : '이 PC에 저장','barracks-storage-'+account.id,async () => {
          state = await call('accounts/storage',{id:account.id,persist:!account.saved});render();
        }); storage.dataset.storage = 'true';
        wrap.append(label,remove,storage); accounts.append(wrap);
      }
      if (!state.accounts.length) accounts.append(node('p','사용할 NAI 계정을 추가해 주세요.'));
      roster = newRoster;
    }
    const batch = state.batch;
    window.AppI18n.setText(storageState, tr(state.credentials?.error || (!state.credentials?.available
      ? '이 PC의 자격증명 저장소를 사용할 수 없습니다. 잠금 해제 후 다시 시도해 주세요.' : '')));
    if (batch) {
      const s = batch.summary;
      progress.textContent = `${tr(statuses[batch.status])} · ${tr('완료')} ${s.completed}/${batch.count} · ${tr('실패')} ${s.failed} · ${tr('대기')} ${s.queued} · ${tr('취소됨')} ${s.cancelled} · ${tr('실행할 계정 없음')} ${s.blocked}`;
      accountProgress.textContent = batch.accounts.map(a => `${a.name}: ${tr(statuses[a.status])}`).join(' / ');
      const version = JSON.stringify(batch.jobs.map(j => [j.id,j.status]));
      if (version !== resultVersion) {
        results.replaceChildren();
        for (const job of batch.jobs.filter(j => j.status !== 'queued')) {
          const card = node('article');
          const title = node('p'); title.textContent = `#${job.index+1} · ${job.account_name || ''} · ${tr(statuses[job.status])}`;
          card.append(title);
          const seed = node('p'); seed.textContent = 'Seed: '+job.seed; card.append(seed);
          const result = job.result;
          if (result?.output_url) {
            const link = node('a'); link.href = result.output_url; link.target = '_blank'; link.rel = 'noopener';
            const image = node('img'); image.src = result.output_url; image.loading = 'lazy'; image.alt = `#${job.index+1}`;
            link.append(image); card.append(link);
          }
          if (result?.error) {const error = node('p'); error.textContent = result.error_detail?.messages?.[window.AppI18n.language]?.message || tr(result.error); card.append(error);}
          if (result?.remote_outcome_unknown) card.append(node('p','결과 확인이 필요합니다. 자동으로 다시 생성하지 않습니다.'));
          if (result?.dry_run) card.append(node('p','드라이런'));
          results.append(card);
        }
        if (batch.status !== 'running') window.dispatchEvent(new Event('anima-barracks-finished'));
        resultVersion = version;
      }
    }
    syncDisabled();
  }
  async function refresh() {
    if (polling) return; polling = true;
    try {state = await call('status'); render();} finally {polling = false;}
  }
  const launch = button('배럭','open-barracks',async () => {
    opener = document.activeElement; message.textContent = ''; preview.textContent = '';
    dialog.showModal();
    try {
      const request = requestFromForm();
      preview.textContent = `${request.nai_model} · ${request.width}×${request.height} · Steps ${request.steps} · CFG ${request.cfg}\nSeed: ${request.seed ?? tr('매번 무작위')}\n${request.prompt}`;
    } catch(error) {message.textContent=error.message;}
    await refresh();
  });
  document.querySelector('.setup-toolbar').append(launch);
  dialog.addEventListener('close',() => {token.value='';opener?.focus();});
  window.addEventListener('anima-locale-change',() => {roster='';resultVersion='';render();});
  setInterval(() => {if (dialog.open && !document.hidden) refresh().catch(error => {message.textContent=error.message;});},1200);
})();
