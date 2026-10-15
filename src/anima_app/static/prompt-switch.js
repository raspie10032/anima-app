/* Engine switches change displayed syntax; an untouched round trip restores exact text. */
(() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const formats = new Set(['auto', 'native', 'comfyui', 'naiv4', 'oldnai']);
  let versions = {}, revision = 0;
  const fields = () => [form.elements.prompt, form.elements.negative_prompt,
    ...[...naiCharacters.children].flatMap(row => [row.querySelector('.character-prompt'), row.querySelector('.character-negative')])];
  const read = () => ({texts: fields().map(input => input.value), source: document.getElementById('prompt-routing').value});
  const valid = value => value && formats.has(value.source) && Array.isArray(value.texts)
    && value.texts.length >= 2 && value.texts.length <= 46 && value.texts.length % 2 === 0
    && value.texts.every(text => typeof text === 'string' && text.length <= 32768);
  window.animaPromptSwitch = {
    target(provider, model = form.elements.nai_model.value) {
      return provider === 'local' ? 'comfyui' : /^nai-diffusion-(?:furry-)?3(?:$|-)/.test(model) ? 'oldnai' : 'naiv4';
    },
    reset() { revision++; versions = {}; },
    snapshot() { return clone(versions); },
    restore(saved) {
      versions = {};
      for (const target of ['comfyui', 'naiv4', 'oldnai']) {
        if (valid(saved?.[target])) versions[target] = clone(saved[target]);
      }
    },
    async prepare(from, to) {
      const original = read(), ticket = revision;
      // Editing or importing changes the shared scene; never resurrect an old
      // engine-specific prompt after the user has written something new.
      const nextVersions = same(versions[from], original) ? clone(versions) : {};
      nextVersions[from] = original;
      let result = nextVersions[to], warnings = [];
      if (!result) {
        const response = await fetch('/api/prompts/adapt-editor', {method: 'POST',
          headers: {'Content-Type': 'application/json'}, signal: AbortSignal.timeout(10000),
          body: JSON.stringify({...original, target: to})});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || tr('프롬프트 표기를 전환하지 못했습니다.'));
        result = {texts: payload.texts, source: payload.source}; warnings = payload.warnings || [];
        if (!valid(result) || result.texts.length !== original.texts.length) throw new Error(tr('프롬프트 표기를 전환하지 못했습니다.'));
      }
      if (ticket !== revision || !same(original, read())) throw new Error(tr('변환 중 초안이 바뀌었습니다. 다시 전환해 주세요.'));
      return () => {
        fields().forEach((input, index) => { if (index < result.texts.length) input.value = result.texts[index]; });
        document.getElementById('prompt-routing').value = result.source;
        nextVersions[to] = result; versions = nextVersions;
        invalidateConversion();
        window.AppI18n.setText(document.getElementById('prompt-switch-status'), () =>
          warnings.length ? warnings.map(warning => tr(warning)).join(' ')
            : result.source === 'native' ? tr('변환 안 함 · 입력 그대로')
            : tr('프롬프트·네거티브·캐릭터 표기 전환 완료 · 수정 없이 돌아가면 원문을 복원합니다.'));
      };
    }
  };
  const status = document.createElement('p'); status.id = 'prompt-switch-status';
  status.setAttribute('role', 'status'); document.getElementById('authoring-panel').append(status);
})();
