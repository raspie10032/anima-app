/* Preserve authoring intent while each engine receives its own prompt syntax. */
(() => {
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const make = (tag, text = "", id = "") => {
    const node = document.createElement(tag); window.AppI18n.setText(node, () => text); if (id) node.id = id; return node;
  };
  const button = (text, action, id = "") => {
    const node = make("button", text, id); node.type = "button"; node.className = "secondary-button";
    node.addEventListener("click", action); return node;
  };
  const key = "anima.authoring.v1";
  let sources = [], ready = false, restoring = false, dirty = false, timer = 0;
  const panel = make("div", "", "authoring-panel"); panel.className = "authoring-panel";
  const label = make("label", tr("입력 프롬프트 표기"));
  const format = make("select", "", "prompt-routing");
  for (const [value, name] of [["auto", tr("자동 감지 → 엔진에 맞춤")], ["comfyui", tr("Anima / ComfyUI (태그:가중치)")],
    ["naiv4", tr("NAI V4 / V5 가중치::태그::")], ["oldnai", tr("구형 NAI {태그}")], ["native", tr("변환 안 함 · 입력 그대로")]]) {
    const option = make("option", name); option.value = value; format.append(option);
  }
  label.append(format); panel.append(label);
  panel.append(make("p", tr("NAI에는 가중치::와 artist:, Anima에는 (태그:가중치)와 @를 전달합니다. 작성 원문은 유지합니다.")));
  panel.append(make("p", tr("접두사 없는 태그만 로컬 단보루 작가 목록과 정확히 대조합니다. 일치하지 않으면 그대로 둡니다.")));
  const actions = make("div"); actions.className = "authoring-actions";
  const status = make("span", tr("이 브라우저에 작업 초안 자동 저장"), "authoring-status"); status.setAttribute("role", "status");
  const sourceList = make("div", "", "authoring-sources");
  panel.append(actions, status, sourceList);
  $("prompt").after(panel);

  const dialog = make("dialog", "", "prompt-plan-dialog");
  const preview = make("div", "", "prompt-plan-content");
  const close = button(tr("닫기"), () => dialog.close());
  dialog.append(make("h2", tr("단계별 전달 프롬프트")), close, preview); document.body.append(dialog);
  let previewRevision = 0;
  async function previewPlan() {
    const ticket = ++previewRevision;
    preview.replaceChildren(make("p", tr("변환을 확인하고 있습니다…")));
    if (!dialog.open) dialog.showModal();
    try {
      const base = window.animaGenerationRequest();
      const request = window.animaWorkflow.decorate(base);
      const response = await fetch("/api/prompts/plan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(request)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || tr("미리보기를 불러오지 못했습니다."));
      if (ticket !== previewRevision) return;
      preview.replaceChildren(make("p", tr(result.note)));
      for (const stage of result.stages) {
        const section = make("section"); section.className = "prompt-plan-stage";
        section.append(make("h3", () => `${stage.index} · ${stage.provider === "local" ? "Anima" : "NAI"} · ${{generate:tr("생성"),detail:tr("디테일러"),upscale:tr("업스케일")}[stage.operation] || stage.operation}`));
        section.append(make("p", tr`출력 표기: ${stage.target} · 작성 원문은 그대로 보존됩니다.`));
        const catalog = stage.artist_catalog;
        section.append(make("p", catalog?.count ? tr`작가 목록 ${catalog.count.toLocaleString(window.AppI18n.locale)}개 · ${catalog.fetched_at?.slice(0, 10) || ""} · ${catalog.coverage === "nonempty-active" ? tr("활성 태그") : tr("일부 목록")}` : tr("저장된 작가 목록이 없어 접두사 없는 이름은 자동 인식하지 않습니다.")));
        for (const field of stage.fields.filter(f => f.original || f.field === "prompt")) {
          const name = {prompt:tr("프롬프트"),negative_prompt:tr("네거티브")}[field.field] || field.field;
          section.append(make("h4", name), make("pre", field.converted));
          if (field.recognized_artists?.length) section.append(make("p", () => tr("접두사 자동 인식: ") + field.recognized_artists.map(item => item.input).join(", ")));
        }
        for (const warning of stage.warnings) section.append(make("p", warning));
        preview.append(section);
      }
    } catch (error) { if (ticket === previewRevision) preview.replaceChildren(make("p", error.message)); }
  }
  actions.append(button(tr("단계별 전달 미리보기"), previewPlan, "preview-prompt-plan"));

  function renderSources(container = sourceList, items = sources, removable = true) {
    container.replaceChildren(); container.hidden = !items.length;
    if (items.length) container.append(make("p", tr`참고 사례 ${items.length}개 · 가져온 기록이며 작가 판정이 아닙니다.`));
    items.forEach((source, index) => {
      const row = make("div"); row.className = "authoring-source";
      row.append(button(() => `${index + 1}. ${{artists:tr("작가 조합"),prompt:tr("프롬프트"),all:tr("생성 조건")}[source.scope] || tr("사례")} · ${source.asset_id.slice(0, 8)}`,
        () => window.animaLibraryOpenItem?.(source.asset_id, source.record_id)));
      if (removable) row.append(button(tr("연결 해제"), () => {sources.splice(index, 1); renderSources(); changed();}));
      container.append(row);
    });
  }

  const restore = button(tr("저장된 작업 불러오기"), () => restoreSaved(), "restore-authoring");
  const forget = button(tr("저장 초안 삭제"), () => {
    clearTimeout(timer); dirty = false;
    try {localStorage.removeItem(key); restore.hidden = forget.hidden = true; window.AppI18n.setText(status, () => tr("저장 초안을 삭제했습니다. 다음 편집부터 다시 저장합니다."));}
    catch (_) {window.AppI18n.setText(status, () => tr("브라우저 저장소에 접근할 수 없습니다."));}
  }, "forget-authoring");
  actions.append(restore, forget); restore.hidden = forget.hidden = true;
  function readSaved() {
    try {const saved = JSON.parse(localStorage.getItem(key)); return saved?.version === 1 && saved.request && typeof saved.request === "object" ? saved : null;}
    catch (_) {return null;}
  }
  function save() {
    if (!ready || restoring || !dirty) return;
    try {
      const request = window.animaGenerationDraft();
      const engine_profiles = window.animaProviderSettings.snapshot();
      localStorage.setItem(key, JSON.stringify({version: 1, saved_at: Date.now(), request, engine_profiles}));
      window.AppI18n.setText(status, () => tr("작업 초안 저장됨 · 새로고침 후에도 복원"));
      restore.hidden = forget.hidden = false;
    } catch (_) {window.AppI18n.setText(status, () => tr("초안을 저장하지 못했습니다. 브라우저 저장 공간을 확인해 주세요."));}
  }
  function changed() {
    if (restoring) return;
    dirty = true; clearTimeout(timer); timer = setTimeout(save, 350);
  }
  function restoreSaved() {
    const saved = readSaved(); if (!saved) return;
    restoring = true;
    try {
      if (window.animaRestoreGeneration(saved.request, saved.engine_profiles) === false) return;
      window.AppI18n.setText(status, () => tr("이전 작업을 복원했습니다 · 실행 버튼을 눌러야 생성됩니다."));
      dirty = false;
    } catch (_) {window.AppI18n.setText(status, () => tr("저장된 초안을 불러오지 못했습니다."));}
    finally {restoring = false;}
  }
  document.addEventListener("input", event => {
    if (event.target.closest(".control-frame") && !event.target.closest("#lora-import-form")) changed();
  });
  document.addEventListener("change", event => {if (event.target.closest(".control-frame")) changed();});
  window.addEventListener("authoring-changed", changed);
  window.addEventListener("pagehide", save);
  window.addEventListener("generation-ready", () => {
    if (ready) return;
    ready = true; const saved = readSaved();
    restore.hidden = forget.hidden = !saved;
    if (saved && !dirty) restoreSaved();
    else if (dirty) save();
  });

  const resultSources = make("div", "", "result-sources"); resultSources.className = "authoring-result-sources"; resultSources.hidden = true;
  document.querySelector(".result-actions").after(resultSources);
  window.animaAuthoring = {
    context: () => ({prompt_routing: {source: format.value}, generation_sources: clone(sources)}),
    apply(request) {
      format.value = request.prompt_routing?.source || "auto";
      if (!format.value) format.value = "auto";
      sources = clone(request.generation_sources || []); renderSources();
    },
    showResult(manifest) {renderSources(resultSources, manifest.generation_sources || manifest.workflow_base_request?.generation_sources || [], false);},
    save,
  };
})();
