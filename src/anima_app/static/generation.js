/* Arrange the existing generation controls without duplicating form state or actions. */
(() => {
  const $ = selector => document.querySelector(selector);
  const make = (tag, className = "", text = "") => {
    const node = document.createElement(tag);
    node.className = className;
    window.AppI18n.setText(node, () => text);
    return node;
  };
  const action = (text, handler, id) => {
    const node = make("button", "secondary-button", text);
    node.type = "button";
    if (id) node.id = id;
    node.addEventListener("click", handler);
    return node;
  };
  const fold = (node, title, id) => {
    const details = make("details", "generation-fold");
    details.id = id;
    details.append(make("summary", "", title));
    node.before(details);
    details.append(node);
    return details;
  };
  const reveal = node => {
    for (let parent = node.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    node.scrollIntoView({block: "nearest"});
    node.focus({preventScroll: true});
  };
  const shell = $(".app-shell");
  const controls = $(".control-frame");
  const workspace = $(".workspace-frame");
  const history = $(".history-frame");
  const form = $("#generate-form");
  shell.classList.add("generation-app");
  document.body.classList.add("generation-body");

  const header = make("header", "generation-header");
  const brand = make("div", "generation-brand");
  brand.append(make("span", "generation-mark", "A"), $(".control-frame h1"));
  const nav = make("nav", "generation-nav");
  window.AppI18n.setAttribute(nav, "aria-label", tr("작업 화면"));
  const current = make("span", "generation-current", tr("생성"));
  current.setAttribute("aria-current", "page");
  const library = $("#open-library");
  window.AppI18n.setText(library, () => tr("이미지 작업실"));
  window.AppI18n.setProperty(library, "title", () => tr("유사사례 · 작가 조합 · 프롬프트 찾기"));
  nav.append(current, library);
  const historyToggle = action(tr("최근 결과 접기"), () => {
    const collapsed = shell.classList.toggle("history-collapsed");
    history.hidden = collapsed;
    window.AppI18n.setText(historyToggle, () => collapsed ? tr("최근 결과 보기") : tr("최근 결과 접기"));
    historyToggle.setAttribute("aria-expanded", String(!collapsed));
  }, "toggle-history");
  history.id = "generation-history";
  historyToggle.setAttribute("aria-controls", history.id);
  historyToggle.setAttribute("aria-expanded", "true");
  header.append(brand, nav, $("#nai-language-panel"), historyToggle);
  shell.prepend(header);
  const tablet = window.matchMedia("(min-width:781px) and (max-width:1250px)");
  if (tablet.matches) historyToggle.click();
  tablet.addEventListener("change", event => {
    if (event.matches && !history.hidden) historyToggle.click();
  });

  const scroller = make("div", "generation-controls-scroll");
  scroller.append(...controls.childNodes);
  controls.append(scroller);
  const settings = $('[data-control-group="settings"] .control-group-body');
  settings.append($("#side-status-panel"));
  window.AppI18n.setText($('[data-control-group="settings"] > summary'), () => tr("프리셋 · 앱 설정"));
  window.AppI18n.setText($('[data-control-group="prompt-generate"] > summary'), () => tr("프롬프트"));
  window.AppI18n.setText($('[data-control-group="model-style"] > summary'), () => tr("모델 · 캐릭터 · 스타일"));
  window.AppI18n.setText($('[data-control-group="enhance"] > summary'), () => tr("참조 이미지 · 후처리"));
  // Essential inputs remain ordinary form-associated controls, including while folded.
  const promptSection = $("#prompt").closest("section");
  promptSection.querySelector("h2").remove();
  const promptLabel = $('label[for="prompt"]');
  window.AppI18n.setText(promptLabel, () => tr("그리고 싶은 장면"));
  window.AppI18n.setProperty($("#prompt"), "placeholder", () => tr("작가 조합, 인물, 장면, 빛과 색감을 적어 보세요."));
  const tools = fold($(".prompt-tools-block"), tr("와일드카드 · 프리셋 · 문법 변환"), "generation-prompt-tools");
  $(".prompt-tools-block h2").remove();
  tools.append($("#prompt-converter"));
  const metadata = fold($("#nai-metadata-drop-zone").closest("section"), tr("이미지에서 생성 조건 가져오기"), "generation-import");
  metadata.querySelector("h2").remove();
  const sizeGroup = $('[data-control-group="image-settings"]');
  sizeGroup.querySelector("h2").remove();
  sizeGroup.querySelector(".form-section").append($(".preset-strip"));
  $(".preset-strip h2").remove();
  const promptGroup = $('[data-control-group="prompt-generate"]');
  promptGroup.after(sizeGroup);
  fold($("#lora-import-form"), tr("LoRA 파일 가져오기"), "generation-lora-import");
  const modelGroup = $('[data-control-group="model-style"]');
  modelGroup.open = false;
  // Keep provider-specific guards and their controls in their original parent sections.
  const naiGuide = $("#nai-feature-guide");
  for (const warning of $("#novelai-settings").querySelectorAll(":scope > p.queue-status")) {
    if (warning.id !== "nai-effective") naiGuide.append(warning);
  }

  const queuePanel = $("#auto-queue-panel");
  const oldGenerationSection = queuePanel.parentElement;
  const queueDetails = fold(queuePanel, tr("연속 생성 · 시드 반복"), "generation-queue");
  queuePanel.querySelector("h2").remove();
  $("#control-groups").append(queueDetails);
  const footer = make("footer", "generation-dock");
  window.AppI18n.setAttribute(footer, "aria-label", tr("생성 실행과 진행 상태"));
  const dockInfo = make("div", "generation-dock-info");
  const summary = make("div", "generation-request-summary");
  summary.id = "generation-request-summary";
  const blocked = make("p", "generation-blocked");
  blocked.id = "generation-blocked";
  blocked.setAttribute("role", "status");
  dockInfo.append(summary, $("#queue-status"), blocked);
  const dockActions = make("div", "generation-dock-actions");
  dockActions.append(action(tr("연속 생성 설정"), () => reveal(queueDetails.querySelector("summary")), "open-queue-settings"),
    $("#stop-queue"), $("#generate-button"));
  footer.append(dockInfo, dockActions);
  shell.append(footer);
  $("#generate-button").setAttribute("aria-describedby", blocked.id);
  oldGenerationSection.remove();

  // The canvas leads with the image. Generation facts remain available below it.
  const resultPanel = $(".result-panel");
  const empty = make("div", "generation-empty");
  empty.id = "generation-empty";
  const illustration = make("div", "generation-empty-art");
  illustration.setAttribute("aria-hidden", "true");
  illustration.append(make("span", ""), make("span", ""), make("span", ""));
  empty.append(illustration, make("h2", "", tr("어떤 그림을 만들어 볼까요?")),
    make("p", "", tr("장면을 적거나, 이미지 작업실에서 마음에 드는 작가 조합을 찾아오세요.")));
  const emptyActions = make("div", "generation-empty-actions");
  emptyActions.append(action(tr("프롬프트 작성"), () => reveal($("#prompt"))),
    action(tr("그림에서 시작"), () => library.click()));
  empty.append(emptyActions);
  $("#preview").before(empty);
  $(".result-actions").after($("#result-summary"));
  $(".history-frame > .frame-title").remove();
  window.AppI18n.setText($(".history-header h2"), () => tr("최근 결과"));
  fold($("#history-storage"), tr("보관 공간"), "generation-storage");
  // Put usage details after the actual results, rather than above the first image.
  $(".history-panel").append($("#generation-storage"));

  const refreshCanvas = () => {
    const hasImage = !$("#preview").hidden || !$("#compare-grid").hidden;
    if (empty.hidden !== hasImage) empty.hidden = hasImage;
    resultPanel.classList.toggle("has-image", !$("#preview").hidden || !$("#compare-grid").hidden);
    const title = $("#result-title");
    window.AppI18n.setProperty(title, "title", () => title.textContent);
  };
  new MutationObserver(refreshCanvas).observe(resultPanel, {
    attributes: true, attributeFilter: ["hidden"], childList: true, characterData: true, subtree: true
  });
  refreshCanvas();

  const refreshRequest = () => {
    $("#generation-lora-import").hidden = $("#provider-select").value === "novelai";
    const engine = $("#provider-select").selectedOptions[0]?.textContent || "";
    const model = $("#provider-select").value === "novelai" ? $("#nai-model") : $("#checkpoint-select");
    const description = tr`${engine} · ${$("#width").value} × ${$("#height").value} · ${$("#steps").value} steps · 시드 ${$("#seed").value || tr("랜덤")}`;
    if (summary.textContent !== description) window.AppI18n.setText(summary, () => description);
    const reason = $("#generate-button").title;
    if (blocked.textContent !== reason) window.AppI18n.setText(blocked, () => reason);
    blocked.hidden = !reason;
    let modelName = modelGroup.querySelector(".generation-model-name");
    if (!modelName) {
      modelName = make("span", "generation-model-name");
      modelGroup.querySelector("summary").append(modelName);
    }
    const name = model.selectedOptions[0]?.textContent || tr("모델 선택");
    if (modelName.textContent !== name) window.AppI18n.setText(modelName, () => name);
    window.AppI18n.setProperty(modelName, "title", () => name);
  };
  document.addEventListener("input", refreshRequest);
  document.addEventListener("change", refreshRequest);
  window.addEventListener("generation-settings-applied", refreshRequest);
  window.addEventListener("anima-locale-change", refreshRequest);
  new MutationObserver(refreshRequest).observe($("#generate-button"), {
    attributes: true, attributeFilter: ["title", "disabled"]
  });
  for (const model of [$("#nai-model"), $("#checkpoint-select")]) {
    new MutationObserver(refreshRequest).observe(model, {childList: true});
  }
  refreshRequest();
  // Native validity must reveal the actual field even in an unopened accordion.
  document.addEventListener("invalid", event => {
    if (event.target.form === form || controls.contains(event.target)) reveal(event.target);
  }, true);
})();
