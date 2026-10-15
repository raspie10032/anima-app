/* Keep each engine's controls separate while sharing the authored scene. */
(() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const shared = ["width", "height", "steps", "cfg", "seed"];
  const groups = {
    local: '#local-model-settings, #local-sampling-controls, #local-memory-controls, [data-control-group="enhance"]',
    novelai: '#novelai-settings'
  };
  // Capture only generation controls, never connection credentials or file inputs.
  const controls = Object.fromEntries(Object.entries(groups).map(([provider, selector]) => [provider,
    [...document.querySelectorAll(selector)].flatMap(group => [...group.querySelectorAll('input, select, textarea')])
      .filter(input => input.type !== 'file' && !input.closest('.lora-row, #nai-characters, #nai-vibes, #nai-references, #nai-detailer-panel')
        && (input.form === form || ['nai-character-count', 'nai-use-coords', 'nai-use-order', 'nai-normalize-vibes'].includes(input.id)))
  ]));
  let active = providerSelect.value, profiles = {}, initialized = false, switching = false;
  const hint = document.createElement('p');
  hint.id = 'provider-settings-status'; hint.className = 'queue-status'; hint.setAttribute('role', 'status');
  providerStatus.after(hint);
  const valueOf = input => input.type === 'checkbox' ? input.checked : input.value;
  function read(provider) {
    const fields = Object.fromEntries(controls[provider].map(input => [input.name || input.id, valueOf(input)]));
    for (const name of shared) fields[name] = form.elements[name].value;
    return {fields, ...(provider === 'local' ? {loras: selectedLoras()} : {
      characters: readNaiCharacterSlots(), detailer: readNaiDetailer(),
      vibes: readNaiReferences('vibe'), references: readNaiReferences('precise')
    })};
  }
  function defaults(provider) {
    const state = read(provider);
    const initial = provider === 'local' ? animaDefaults : {
      width: 832, height: 1216, steps: 28, cfg: 6,
      ...(providerCapabilities?.providers.find(item => item.id === 'novelai')?.defaults || {})
    };
    for (const name of shared) state.fields[name] = String(initial[name] ?? '');
    return state;
  }
  function remember() { profiles[active] = read(active); }
  function restore(provider, state, includeShared = true) {
    if (!state?.fields || typeof state.fields !== 'object') return;
    const previousInput = form.elements.input_image.value, previousMask = form.elements.mask_image.value;
    const previousReference = form.elements.i2i_image.value;
    const fields = [...controls[provider], ...(includeShared ? shared.map(name => form.elements[name]) : [])];
    // Operation must be selected before rebuilding NAI's model choices.
    if (provider === 'novelai' && ['generate', 'img2img', 'infill', 'focused_infill', 'detail'].includes(state.fields.operation)) {
      naiOperation.value = state.fields.operation; renderNovelAIOptions();
    }
    for (const input of fields) {
      const value = state.fields[input.name || input.id];
      if (input.type === 'checkbox') { if (typeof value === 'boolean') input.checked = value; }
      else if (typeof value === 'string' || typeof value === 'number') {
        if (input.tagName === 'SELECT') setSelectValue(input, String(value));
        else input.value = value;
      }
    }
    if (provider === 'local') {
      if (Array.isArray(state.loras) && !same(selectedLoras(), state.loras)) setLoraRows(state.loras);
      if (form.elements.i2i_image.value !== previousReference) {
        setManagedReferencePath(form.elements.i2i_image.value);
      }
      syncSam3DetailerControls();
    } else {
      if (Array.isArray(state.characters) && !same(readNaiCharacterSlots(), state.characters)) {
        setNaiCharacters(state.characters, Number(state.fields['nai-character-count'] || 0));
      }
      if (state.detailer && typeof state.detailer === 'object') setNaiDetailer(state.detailer);
      if (Array.isArray(state.vibes) && Array.isArray(state.references)
          && (!same(readNaiReferences('vibe'), state.vibes) || !same(readNaiReferences('precise'), state.references))) {
        setNaiReferences(state.vibes, state.references);
      }
      if (previousInput !== form.elements.input_image.value || previousMask !== form.elements.mask_image.value) resetNaiEditor();
    }
  }
  function report(isDefault = false) {
    window.AppI18n.setText(hint, () => isDefault
      ? tr('엔진 기본 설정 적용 · 이후에는 각 엔진에서 쓰던 설정을 복원합니다.')
      : tr('엔진별 마지막 설정 복원 · 프롬프트와 작업 순서는 이어서 사용합니다.'));
  }
  window.animaProviderSettings = {
    get switching() { return switching; },
    async switch() {
      const next = providerSelect.value;
      if (switching) { providerSelect.value = active; return; }
      if (next === active) { syncProviderControls(); return; }
      if (queueRunning || !uploadsAreIdle()) { providerSelect.value = active; return; }
      providerSelect.value = active;
      remember();
      const isDefault = !profiles[next];
      const state = profiles[next] || defaults(next);
      switching = true; providerSelect.disabled = true;
      window.AppI18n.setText(hint, () => tr('엔진에 맞춰 프롬프트 표기를 전환하고 있습니다…'));
      try {
        const applyPrompts = await window.animaPromptSwitch.prepare(
          window.animaPromptSwitch.target(active), window.animaPromptSwitch.target(next, state.fields.nai_model));
        if (queueRunning || !uploadsAreIdle()) { report(); return; }
        remember();
        active = next; providerSelect.value = next;
        restore(active, state); applyPrompts();
        syncProviderControls(); syncStartingPointSelectionFromInputs();
        loadReadiness().catch(error => setResultPayload({error: String(error)}));
        report(isDefault);
        window.dispatchEvent(new Event('generation-settings-applied'));
        window.dispatchEvent(new Event('authoring-changed'));
      } catch (error) {
        window.AppI18n.setText(hint, () => tr('엔진 전환을 멈췄습니다. 입력 내용은 유지됩니다.') + ' ' + error.message);
      } finally {
        switching = false; syncGenerationControls();
      }
    },
    beforeApply(next) {
      window.animaPromptSwitch?.reset();
      remember();
      const other = next === 'novelai' ? 'local' : 'novelai';
      if (!profiles[other]) profiles[other] = defaults(other);
      active = next;
    },
    afterApply() {
      const other = active === 'novelai' ? 'local' : 'novelai';
      restore(other, profiles[other], false);
      remember(); syncProviderControls(); report();
    },
    snapshot() {
      remember();
      const saved = clone(profiles);
      if (saved.novelai) {
        // Hidden slots also carry the current editor syntax while using Anima.
        saved.novelai.characters = readNaiCharacterSlots();
        saved.novelai.fields['nai-character-count'] = naiCharacterCount.value;
      }
      return saved;
    },
    restoreSaved(saved) {
      // The explicit draft is authoritative for its active engine.
      const other = active === 'novelai' ? 'local' : 'novelai';
      if (saved?.[other]?.fields && typeof saved[other].fields === 'object') {
        restore(other, saved[other], false);
        profiles[other] = {...read(other), fields: {...read(other).fields,
          ...Object.fromEntries(shared.filter(name => typeof saved[other].fields[name] === 'string')
            .map(name => [name, saved[other].fields[name]]))}};
      }
      remember(); syncProviderControls();
    }
  };
  window.addEventListener('generation-ready', () => {
    if (initialized) return;
    initialized = true; report(true);
  });
})();
