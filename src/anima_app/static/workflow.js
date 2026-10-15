/* Each post-processing step owns its settings; images always flow in visible order. */
(() => {
  const $ = id => document.getElementById(id);
  const make = (tag, text = "", className = "") => {
    const node = document.createElement(tag); window.AppI18n.setText(node, () => text); node.className = className; return node;
  };
  const button = (text, callback, title = text) => {
    const node = make("button", text, "secondary-button"); node.type = "button"; window.AppI18n.setProperty(node, "title", () => title);
    window.AppI18n.setAttribute(node, "aria-label", title); node.addEventListener("click", callback); return node;
  };
  const clone = value => JSON.parse(JSON.stringify(value));
  let steps = [];
  const panel = make("details", "", "generation-fold workflow-panel");
  panel.id = "generation-workflow";
  const title = make("summary", tr("작업 순서"));
  const count = make("span", "", "generation-model-name"); title.append(count); panel.append(title);
  const body = make("div", "", "workflow-body"); panel.append(body);
  document.querySelector('[data-control-group="image-settings"]').after(panel);
  const presets = make("div", "", "workflow-presets");
  body.append(presets, make("p", tr("앞 단계의 결과를 다음 단계에 넘깁니다. 순서와 단계별 조건은 프리셋에 함께 저장됩니다."), "queue-status"));
  const list = make("ol", "", "workflow-list"); body.append(list);
  const controls = make("div", "", "workflow-add");
  const choice = make("select"); choice.id = "workflow-add-type"; window.AppI18n.setAttribute(choice, "aria-label", tr("추가할 작업"));
  for (const [value, text] of [["local:detail", tr("Anima 디테일러")], ["novelai:detail", tr("NAI 디테일러")], ["local:upscale", tr("Anima 업스케일")]]) {
    const option = make("option", text); option.value = value; choice.append(option);
  }
  const error = make("p", "", "workflow-error"); error.setAttribute("role", "status");
  const report = text => { window.AppI18n.setText(error, () => text); };
  const getCurrent = () => { try { return window.animaGenerationRequest(); } catch (_) { return null; } };
  const defaults = (provider, operation) => {
    const request = provider === "local" ? {
      checkpoint: $("checkpoint-select").value, cfg: 4, steps: 20,
      face_detailer: {enabled: true, steps: 10, denoise: .28},
      upscale: {enabled: operation === "upscale", scale: 1.5, steps: 10, denoise: .35}
    } : {nai_model: $("nai-model").value || "nai-diffusion-5-curated", cfg: 6, steps: 28,
      nai_limit_opus_free: true, nai_detailer: {enabled: true, preview_only: false, steps: 28, strength: .55}};
    return {provider, operation, inherit_prompt: true, request};
  };
  const disableInline = () => {
    const ids = $("provider-select").value === "novelai"
      ? ["nai-detailer-enabled"] : ["upscale-enabled", "face-detailer-enabled"];
    for (const id of ids) {
      if ($(id)) { $(id).checked = false; $(id).dispatchEvent(new Event("change", {bubbles: true})); }
    }
  };
  const setDirection = (provider, target) => {
    $("provider-select").value = provider;
    $("provider-select").dispatchEvent(new Event("change", {bubbles: true}));
    $("nai-operation").value = "generate";
    $("nai-operation").dispatchEvent(new Event("change", {bubbles: true}));
    disableInline();
    steps = [defaults(target, "detail")]; panel.open = true; report(""); render();
  };
  presets.append(button("NAI → Anima", () => setDirection("novelai", "local"), tr("NAI 생성 → Anima 디테일러")),
    button("Anima → NAI", () => setDirection("local", "novelai"), tr("Anima 생성 → NAI 디테일러")),
    button(tr("생성만"), () => { steps = []; report(""); render(); }));
  const add = button(tr("단계 추가"), () => {
    if (steps.length >= 6) return report(tr("후처리는 최대 6단계까지 추가할 수 있습니다."));
    const [provider, operation] = choice.value.split(":");
    steps.push(defaults(provider, operation)); panel.open = true; report(""); render();
  });
  add.id = "workflow-add";
  controls.append(choice, add); body.append(controls, error);

  function labelControl(parent, text, control) {
    window.AppI18n.setAttribute(control, "aria-label", text);
    const label = make("label", text); label.append(control); parent.append(label); return control;
  }
  function number(parent, text, value, min, max, step, set) {
    const input = make("input"); input.type = "number";
    Object.assign(input, {min, max, step, value});
    input.required = true;
    input.addEventListener("input", () => set(Number(input.value)));
    return labelControl(parent, text, input);
  }
  function select(parent, text, values, value, set) {
    const input = make("select");
    for (const [v, t] of values) { const option = make("option", t); option.value = v; input.append(option); }
    input.value = value;
    input.addEventListener("change", () => set(input.value));
    return labelControl(parent, text, input);
  }
  function stageLabel(stage) {
    return `${stage.provider === "local" ? "Anima" : "NAI"} ${stage.operation === "upscale" ? tr("업스케일") : tr("디테일러")}`;
  }
  function updateFirst() {
    for (const fields of list.querySelectorAll(".workflow-nai-inheritance")) fields.disabled = $("provider-select").value !== "novelai";
    const first = list.querySelector(".workflow-first");
    if (first) {
      const engine = $("provider-select").value === "novelai" ? "NAI" : "Anima";
      const inline = engine === "NAI" ? $("nai-detailer-enabled").checked : $("face-detailer-enabled").checked || $("upscale-enabled").checked;
      window.AppI18n.setText(first, () => `1 · ${engine} ${engine === "NAI" && $("nai-operation").value !== "generate" ? tr("이미지 편집") : tr("생성")}${inline ? tr(" + 기존 후처리") : ""}`);
    }
    window.AppI18n.setText(count, () => steps.length ? tr`${steps.length + 1}단계` : tr("1단계"));
  }
  function render() {
    window.dispatchEvent(new Event("authoring-changed"));
    list.replaceChildren();
    list.append(make("li", "", "workflow-first")); updateFirst();
    steps.forEach((stage, index) => {
      const row = make("li", "", "workflow-step"); row.dataset.index = index;
      const head = make("div", "", "workflow-step-head");
      head.append(make("strong", () => `${index + 2} · ${stageLabel(stage)}`));
      const actions = make("div", "", "workflow-step-actions");
      const up = button("↑", () => { [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]]; render(); }, tr`${index + 2}단계 위로`);
      const down = button("↓", () => { [steps[index + 1], steps[index]] = [steps[index], steps[index + 1]]; render(); }, tr`${index + 2}단계 아래로`);
      up.disabled = index === 0; down.disabled = index === steps.length - 1;
      actions.append(up, down, button("×", () => { steps.splice(index, 1); render(); }, tr`${index + 2}단계 삭제`));
      head.append(actions); row.append(head);
      const details = make("details"); details.append(make("summary", tr("단계 조건"))); row.append(details);
      const grid = make("div", "", "workflow-fields"); details.append(grid);
      select(grid, tr("엔진 · 기능"), [["local:detail", tr("Anima 디테일러")], ["novelai:detail", tr("NAI 디테일러")], ["local:upscale", tr("Anima 업스케일")]],
        `${stage.provider}:${stage.operation}`, value => { const [p, op] = value.split(":"); steps[index] = defaults(p, op); render(); });
      const request = stage.request;
      const modelKey = stage.provider === "local" ? "checkpoint" : "nai_model";
      const source = stage.provider === "local" ? $("checkpoint-select") : $("nai-model");
      const modelOptions = [...source.options].map(option => [option.value, option.textContent]);
      if (!modelOptions.some(([value]) => value === request[modelKey]) && request[modelKey]) modelOptions.push([request[modelKey], request[modelKey]]);
      select(grid, tr("모델"), modelOptions, request[modelKey], value => { request[modelKey] = value; });
      let settings, strength;
      if (stage.provider === "novelai") { settings = request.nai_detailer ||= {}; strength = "strength"; }
      else if (stage.operation === "upscale") { settings = request.upscale ||= {}; strength = "denoise"; }
      else { settings = request.face_detailer ||= {}; strength = "denoise"; }
      number(grid, tr("보정 스텝"), settings.steps ?? 10, 1, stage.provider === "novelai" ? 50 : 100, 1, value => { settings.steps = value; });
      number(grid, tr("변경 강도"), settings[strength] ?? .3, 0, 1, .01, value => { settings[strength] = value; });
      number(grid, "CFG", request.cfg ?? 4, 0, 20, .1, value => { request.cfg = value; });
      if (stage.operation === "upscale") number(grid, tr("배율"), settings.scale ?? 1.5, 1, 4, .1, value => { settings.scale = value; });
      else {
        const key = stage.provider === "novelai" ? "backend" : "mask_backend";
        select(grid, tr("검출 · 마스크"), [["sam_b", tr("얼굴 · 눈 / SAM")], ["sam3", "SAM3"]], settings[key] || "sam_b", value => { settings[key] = value; });
        const cropKey = stage.provider === "novelai" ? "crop_factor" : "crop_scale";
        number(grid, tr("크롭 범위 배율"), settings[cropKey] ?? (stage.provider === "novelai" ? 2 : 1.5), 1, 4, .1, value => { settings[cropKey] = value; });
        number(grid, tr("크롭 여백(px)"), settings.padding ?? 32, 0, 256, 1, value => { settings.padding = value; });
      }
      if (stage.provider === "novelai") {
        select(grid, tr("캐릭터 연결"), [["auto", tr("자동 (여러 캐릭터: WD)")], ["shared", tr("공통 / 단일 캐릭터")], ["wd14", tr("WD 태그로 캐릭터 연결")]],
          settings.matching || "auto", value => { if (value === "auto") delete settings.matching; else settings.matching = value; });
        for (const [key, label, names] of [["face_detector", tr("얼굴 검출기"), ["face_yolov8n.pt", "face_yolov8m.pt"]],
          ["eyes_detector", tr("눈 검출기"), ["full_eyes_detect_v1.pt"]], ["hands_detector", tr("손 검출기"), ["hand_yolov8n.pt", "hand_yolov8s.pt"]]]) {
          select(grid, label, [["auto", tr("자동")], ...names.map(name => [name, name])], settings[key] || "auto", value => { settings[key] = value; });
        }
        select(grid, tr("저장 형식"), [["png", "PNG"], ["webp_lossless", tr("WebP 무손실")], ["webp_lossy", tr("WebP 손실")]], request.nai_save_format || "png", value => { request.nai_save_format = value; });
        number(grid, tr("WebP 품질"), request.nai_webp_quality ?? 90, 1, 100, 1, value => { request.nai_webp_quality = value; });
        number(grid, tr("응답 대기 시간 (초)"), request.nai_request_timeout ?? 300, 30, 1800, 1, value => { request.nai_request_timeout = value; });
        const inheritFields = make("fieldset", "", "workflow-nai-inheritance");
        inheritFields.disabled = $("provider-select").value !== "novelai";
        inheritFields.append(make("legend", tr("첫 NAI 단계에서 이어받기")));
        for (const [key, label] of [["nai_model", tr("모델")], ["cfg", "CFG"], ["steps", tr("보정 스텝")],
          ["nai_sampler", tr("샘플러")], ["nai_scheduler", tr("스케줄러")], ["nai_cfg_rescale", "CFG rescale"],
          ["nai_prefer_brownian", "Brownian"], ["nai_variety_boost", "Variety boost"]]) {
          const input = make("input"); input.type = "checkbox"; input.checked = stage.inherit_settings?.includes(key) || false;
          input.addEventListener("change", () => { stage.inherit_settings = [...new Set([...(stage.inherit_settings || []).filter(k => k !== key), ...(input.checked ? [key] : [])])]; });
          labelControl(inheritFields, label, input);
        }
        details.append(inheritFields);
        details.append(make("p", tr("체크한 조건은 첫 NAI 단계에서 가져옵니다. 나머지는 이 단계의 설정을 사용합니다."), "queue-status"));
        const guard = make("input"); guard.type = "checkbox"; guard.checked = request.nai_limit_opus_free !== false;
        guard.addEventListener("change", () => { request.nai_limit_opus_free = guard.checked; });
        labelControl(details, tr("Opus 무료 범위 보호"), guard).parentElement.className = "workflow-check";
        details.append(make("p", tr("얼굴이 큰 그림에서는 크롭 범위·여백을 줄여 주세요. 보호 모드에서는 원본 전체를 덮는 크롭을 전송하지 않습니다."), "queue-status"));
      }
      const inherit = make("input"); inherit.type = "checkbox"; inherit.checked = stage.inherit_prompt;
      labelControl(details, tr("첫 단계 프롬프트 · 캐릭터 사용"), inherit).parentElement.className = "workflow-check";
      const prompts = make("div", "", "workflow-prompts"); prompts.hidden = stage.inherit_prompt;
      select(prompts, tr("이 단계 입력 표기"), [["auto", tr("자동 감지")], ["comfyui", "Anima / ComfyUI"], ["naiv4", "NAI V4 / V5"], ["oldnai", tr("구형 NAI")], ["native", tr("변환 안 함")]],
        request.prompt_routing?.source || "auto", value => { request.prompt_routing = {source: value}; });
      for (const [key, text] of [["prompt", tr("이 단계 프롬프트")], ["negative_prompt", tr("네거티브")]]) {
        const field = make("textarea"); field.rows = 3; field.value = request[key] || "";
        field.addEventListener("input", () => { request[key] = field.value; }); labelControl(prompts, text, field);
      }
      inherit.addEventListener("change", () => { stage.inherit_prompt = inherit.checked; prompts.hidden = inherit.checked; });
      details.append(prompts, button(tr("현재 엔진의 상세 설정 복사"), () => {
        const current = getCurrent(); if (!current) return report(tr("프롬프트와 현재 생성 조건을 먼저 확인해 주세요."));
        if ((current.provider || "local") !== stage.provider) return report(tr("위쪽 생성 엔진을 이 단계의 엔진으로 선택한 뒤 복사해 주세요."));
        stage.request = clone(current); delete stage.request.dry_run; delete stage.request.progress_id;
        report(tr("LoRA·캐릭터·참조·디테일러 설정을 이 단계에 복사했습니다. 첫 단계 엔진은 다시 선택할 수 있습니다.")); render();
      }));
      list.append(row);
    });
  }
  window.animaWorkflow = {
    decorate(request) {
      if (!steps.length) return request;
      for (const input of panel.querySelectorAll("input[type=number]")) {
        if (!input.checkValidity()) { panel.open = true; input.closest("details").open = true; input.reportValidity(); throw new Error(tr("작업 단계의 조건을 확인해 주세요.")); }
      }
      const effectiveSteps = clone(steps);
      if (request.provider !== "novelai") for (const step of effectiveSteps) delete step.inherit_settings;
      return {...request, workflow: {version: 1, steps: effectiveSteps}};
    },
    apply(workflow) { steps = clone(workflow?.steps || []); panel.open = steps.length > 0; report(""); render(); },
    snapshot() { return clone(steps); }
  };
  document.addEventListener("change", updateFirst);
  window.addEventListener("generation-settings-applied", updateFirst);
  render();
})();
