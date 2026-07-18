    const animaDefaults = JSON.parse(document.getElementById("anima-defaults").textContent);
    const form = document.getElementById("generate-form");
    const sam3DetailerControls = document.getElementById("sam3-detailer-controls");
    const loraImportForm = document.getElementById("lora-import-form");
    const generateButton = document.getElementById("generate-button");
    const autoQueuePanel = document.getElementById("auto-queue-panel");
    const queueCountInput = document.getElementById("queue-count");
    const queueInfiniteInput = document.getElementById("queue-infinite");
    const queueSeedMode = document.getElementById("queue-seed-mode");
    const queueDelayInput = document.getElementById("queue-delay");
    const startQueueButton = document.getElementById("start-queue");
    const stopQueueButton = document.getElementById("stop-queue");
    const queueStatus = document.getElementById("queue-status");
    const result = document.getElementById("result");
    const resultTitle = document.getElementById("result-title");
    const resultStatus = document.getElementById("result-status");
    const resultSummary = document.getElementById("result-summary");
    const compareToolbar = document.getElementById("compare-toolbar");
    const toggleCompareButton = document.getElementById("toggle-compare");
    const compareGrid = document.getElementById("compare-grid");
    const preview = document.getElementById("preview");
    const outputLink = document.getElementById("output-link");
    const statusPanel = document.getElementById("status-panel");
    const readinessPanel = document.getElementById("readiness-panel");
    const updateStatus = document.getElementById("update-status");
    const checkUpdateButton = document.getElementById("check-update");
    const updateLink = document.getElementById("update-link");
    const generationStages = document.getElementById("generation-stages");
    const generationStageList = document.getElementById("generation-stage-list");
    const generationStageSummary = document.getElementById("generation-stage-summary");
    const history = document.getElementById("history");
    const historyCount = document.getElementById("history-count");
    const historyFilters = [...document.querySelectorAll("[data-history-filter]")];
    const checkpointSelect = document.getElementById("checkpoint-select");
    const loraList = document.getElementById("lora-list");
    const addLoraButton = document.getElementById("add-lora");
    const presetName = document.getElementById("preset-name");
    const presetSelect = document.getElementById("preset-select");
    const savePresetButton = document.getElementById("save-preset");
    const applyPresetButton = document.getElementById("apply-preset");
    const exportPresetsButton = document.getElementById("export-presets");
    const importPresetsButton = document.getElementById("import-presets");
    const presetImportFile = document.getElementById("preset-import-file");
    const applyManifestButton = document.getElementById("apply-manifest");
    const sam3Prompt = document.getElementById("sam3-prompt");
    const sam3SegmentButton = document.getElementById("sam3-segment");
    const sam3CompareButton = document.getElementById("sam3-compare");
    const sam3Presets = document.getElementById("sam3-presets");
    const sam3Results = document.getElementById("sam3-results");
    const sam3Status = document.getElementById("sam3-status");
    const maskDilationInput = document.getElementById("mask-dilation");
    const maskFeatherInput = document.getElementById("mask-feather");
    const maskAdjustButton = document.getElementById("mask-adjust");
    const inpaintPromptInput = document.getElementById("inpaint-prompt");
    const inpaintNegativeInput = document.getElementById("inpaint-negative");
    const inpaintMethodSelect = document.getElementById("inpaint-method");
    const inpaintDenoiseInput = document.getElementById("inpaint-denoise");
    const inpaintStepsInput = document.getElementById("inpaint-steps");
    const inpaintCfgInput = document.getElementById("inpaint-cfg");
    const inpaintSeedInput = document.getElementById("inpaint-seed");
    const maskedInpaintButton = document.getElementById("masked-inpaint");
    const autocompleteMenu = document.getElementById("autocomplete-menu");
    const wildcardSelect = document.getElementById("wildcard-select");
    const insertWildcardButton = document.getElementById("insert-wildcard");
    const presetWildcardSelect = document.getElementById("preset-wildcard-select");
    const insertPresetWildcardButton = document.getElementById("insert-preset-wildcard");
    const previewWildcardsButton = document.getElementById("preview-wildcards");
    const llmRefinePromptButton = document.getElementById("llm-refine-prompt");
    const llmRefinePrioritySelect = document.getElementById("llm-refine-priority");
    const llmPromptStatus = document.getElementById("llm-prompt-status");
    const wildcardPreview = document.getElementById("wildcard-preview");
    const startingSizeButtons = Array.from(document.querySelectorAll("[data-size-preset]"));
    const orientationButtons = Array.from(document.querySelectorAll("[data-orientation]"));
    const lowVramHighresPresetButton = document.getElementById("low-vram-highres-preset");
    const referenceImageSection = document.getElementById("reference-image-section");
    const faceDetailerSection = document.getElementById("face-detailer-section");
    let presets = [];
    let currentManifest = null;
    let currentOutputUrl = "";
    let currentMaskUrl = "";
    const sam3PromptPresets = [
      "white dress",
      "sleeveless white dress",
      "white bodysuit",
      "upper body clothing",
      "torso clothing",
      "one-piece outfit",
      "sleeveless outfit",
      "outfit",
      "shirt",
      "skirt",
      "hair",
      "bangs",
      "face",
      "eyes"
    ];
    const sam3ClothingComparePrompts = [
      "white dress",
      "sleeveless white dress",
      "white bodysuit",
      "upper body clothing",
      "torso clothing",
      "one-piece outfit",
      "sleeveless outfit",
      "outfit",
      "shirt",
      "skirt"
    ];
    let compareVisible = false;
    let historyItems = [];
    let historyFilter = "all";
    let loraCatalog = [];
    let stageTimer = null;
    let stageHideTimer = null;
    let progressPollTimer = null;
    let activeProgressId = "";
    let activeStageItems = [];
    let activeStageIndex = 0;
    let queueRunning = false;
    let serverQueuePollTimer = null;
    let activeQueueBatchId = "";
    let lastQueueResultManifest = "";
    let autocompleteTimer = null;
    let autocompleteActiveInput = null;
    let autocompleteItems = [];
    let autocompleteIndex = -1;
    let autocompleteFragment = null;
    const stageStateLabels = {
      pending: "대기",
      active: "진행 중",
      completed: "완료",
      skipped: "건너뜀",
      failed: "실패"
    };
    const stageVisibleStateLabels = {
      pending: "",
      active: "진행 중",
      completed: "",
      skipped: "",
      failed: "실패"
    };
    const startingSizePresets = {
      square: {width: 1024, height: 1024},
      portrait_2x3: {width: 832, height: 1216},
      portrait_3x4: {width: 896, height: 1152}
    };
    let startingOrientation = "portrait";
    let selectedStartingSize = "portrait_2x3";
    function statusCard(label, value) {
      const card = document.createElement("div");
      card.className = "status-item";
      const title = document.createElement("strong");
      title.textContent = label;
      const body = document.createElement("span");
      body.textContent = value;
      card.append(title, body);
      return card;
    }
    function updateStatusText(payload) {
      if (!payload) {
        return "확인 전";
      }
      if (payload.status === "update_available") {
        return `새 버전 있음: ${payload.latest_version}`;
      }
      if (payload.status === "up_to_date") {
        return `최신 상태: ${payload.current_version}`;
      }
      if (payload.status === "update_check_failed") {
        return "업데이트 확인 실패";
      }
      if (payload.version) {
        return `현재: ${payload.version}`;
      }
      return payload.error || "알 수 없음";
    }
    function renderUpdateStatus(payload) {
      updateStatus.textContent = updateStatusText(payload);
      const href = payload?.latest_url || payload?.repository_url || "https://github.com/raspie10032/anima-app";
      updateLink.href = href;
      updateLink.textContent = payload?.status === "update_available" ? "릴리스" : "GitHub";
    }
    async function checkForUpdates() {
      const previousText = checkUpdateButton.textContent;
      checkUpdateButton.disabled = true;
      checkUpdateButton.textContent = "확인 중...";
      updateStatus.textContent = "GitHub 확인 중...";
      try {
        const response = await fetch("/api/update-check");
        const payload = await response.json();
        renderUpdateStatus(payload);
        setResultPayload(payload);
      } catch (error) {
        renderUpdateStatus({status: "update_check_failed", error: String(error)});
        setResultPayload({error: String(error)});
      } finally {
        checkUpdateButton.textContent = previousText;
        checkUpdateButton.disabled = false;
      }
    }
    function readinessActionLabel(profile) {
      if (profile.ready) {
        return "준비됨";
      }
      return "복사 / 다운로드";
    }
    function renderReadiness(payload) {
      const profiles = payload.profiles || [];
      readinessPanel.replaceChildren(...profiles.map((profile) => {
        const card = document.createElement("article");
        card.className = "readiness-card";
        card.dataset.ready = String(Boolean(profile.ready));
        const title = document.createElement("strong");
        title.textContent = profile.label || profile.name;
        const summary = document.createElement("span");
        summary.textContent = profile.ready ? "준비됨" : `${profile.missing_count}개 누락`;
        const files = document.createElement("ul");
        files.className = "readiness-files";
        for (const item of profile.files || []) {
          const file = document.createElement("li");
          file.textContent = `${item.exists ? "확인됨" : "누락"} ${item.relative_path}`;
          files.append(file);
        }
        const action = document.createElement("button");
        action.type = "button";
        action.className = "secondary-button readiness-action";
        action.dataset.profile = profile.name;
        action.textContent = readinessActionLabel(profile);
        action.disabled = Boolean(profile.ready);
        card.append(title, summary, files, action);
        return card;
      }));
    }
    async function prepareModelProfile(profile, button) {
      const previousText = button.textContent;
      button.disabled = true;
      button.textContent = "준비 중...";
      try {
        const response = await fetch("/api/models/prepare", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({profile, source: "auto"})
        });
        const payload = await response.json();
        setResultPayload({status: response.ok ? "profile_prepared" : "profile_prepare_failed", ...payload});
        await loadStatus();
      } catch (error) {
        setResultPayload({error: String(error)});
      } finally {
        button.textContent = previousText;
        button.disabled = false;
      }
    }
    function summaryItem(label, value) {
      const item = document.createElement("div");
      item.className = "summary-item";
      const title = document.createElement("strong");
      title.textContent = label;
      const body = document.createElement("span");
      body.textContent = value;
      item.append(title, body);
      return item;
    }
    function resultMode(payload) {
      if (payload?.error) {
        return "실패";
      }
      if (payload?.dry_run || payload?.status === "dry_run") {
        return "드라이런";
      }
      if (payload?.status) {
        return statusLabel(payload.status);
      }
      return "준비됨";
    }
    function statusLabel(status) {
      const labels = {
        generated: "생성됨",
        dry_run: "드라이런",
        manifest_exported: "생성 정보 내보냄",
        settings_exported: "설정 내보냄",
        settings_saved: "설정 저장됨",
        profile_prepared: "모델 준비 완료",
        profile_prepare_failed: "모델 준비 실패",
        lora_imported: "LoRA 가져오기 완료",
        lora_import_failed: "LoRA 가져오기 실패",
        deleted: "삭제됨",
        unknown: "알 수 없음"
      };
      return labels[status] || status;
    }
    function renderResultSummary(payload = null) {
      if (!payload) {
        resultTitle.textContent = "현재 결과";
        resultStatus.textContent = "준비됨";
        resultSummary.replaceChildren(summaryItem("상태", "준비됨"));
        return;
      }
      if (payload.error) {
        resultTitle.textContent = "요청 실패";
        resultStatus.textContent = "실패";
        resultSummary.replaceChildren(summaryItem("오류", payload.error));
        return;
      }
      const size = payload.width && payload.height ? `${payload.width}x${payload.height}` : "알 수 없음";
      const seed = payload.seed ?? "랜덤";
      const upscale = payload.upscale?.enabled ? `${payload.upscale.scale || 1}x${payload.upscale.tiled ? " 타일" : ""}` : "꺼짐";
      const faceTargets = payload.face_detailer?.mask_backend === "sam3"
        ? [payload.face_detailer?.sam3_face_eyes !== false ? "얼굴+눈" : "", payload.face_detailer?.sam3_hands ? "손" : ""].filter(Boolean).join(" / ")
        : "얼굴";
      const face = payload.face_detailer?.enabled ? `${faceTargets || "선택 없음"} · ${payload.face_detailer.steps || "자동"} 스텝` : "꺼짐";
      resultTitle.textContent = payload.prompt || "현재 결과";
      resultStatus.textContent = resultMode(payload);
      const items = [
        summaryItem("상태", resultMode(payload)),
        summaryItem("크기", size),
        summaryItem("스텝 / CFG", `${payload.steps ?? "?"} / ${payload.cfg ?? "?"}`),
        summaryItem("샘플러", payload.sampler || "?"),
        summaryItem("시드", seed)
      ];
      if (payload.upscale?.enabled) {
        items.push(summaryItem("업스케일", upscale));
      }
      if (payload.face_detailer?.enabled) {
        items.push(summaryItem("페이스 디테일러", face));
      }
      resultSummary.replaceChildren(...items);
    }
    function variantEntries(payload = currentManifest) {
      const variants = payload?.variants || {};
      const slots = [
        {key: "original", label: "원본"},
        {key: "upscale", label: "업스케일"},
        {key: "face_eye_detailer", label: "얼굴 + 눈"},
        {key: "hand_detailer", label: "손"}
      ];
      if (variants.face_detailer && !variants.face_eye_detailer && !variants.hand_detailer) {
        slots.push({key: "face_detailer", label: "페이스 디테일러"});
      }
      return slots.map((slot) => {
        const variant = variants[slot.key] || {};
        return {
          ...variant,
          ...slot,
          output_url: variant.output_url || "",
          output_path: variant.output_path || ""
        };
      });
    }
    function hasCompareVariants(payload = currentManifest) {
      return variantEntries(payload).filter((item) => item.output_url).length >= 2;
    }
    function renderCompareGrid(payload = currentManifest) {
      const entries = variantEntries(payload);
      if (!compareVisible || !hasCompareVariants(payload)) {
        compareGrid.hidden = true;
        compareGrid.replaceChildren();
        return;
      }
      compareGrid.hidden = false;
      compareGrid.replaceChildren(...entries.map((entry) => {
        const cell = document.createElement("div");
        cell.className = "compare-cell";
        const title = document.createElement("strong");
        title.textContent = entry.label;
        cell.append(title);
        if (entry.output_url) {
          const image = document.createElement("img");
          image.src = entry.output_url + "?t=" + Date.now();
          image.alt = entry.label;
          cell.append(image);
        } else {
          const empty = document.createElement("div");
          empty.className = "compare-empty";
          empty.textContent = "생성 안 됨";
          cell.append(empty);
        }
        return cell;
      }));
    }
    function syncCompareControls(payload = currentManifest) {
      const canCompare = hasCompareVariants(payload);
      compareToolbar.hidden = !canCompare;
      toggleCompareButton.hidden = !canCompare;
      if (!canCompare) {
        compareVisible = false;
      }
      toggleCompareButton.textContent = compareVisible ? "비교 숨기기" : "단계 비교";
      renderCompareGrid(payload);
    }
    function setResultPayload(payload) {
      result.textContent = JSON.stringify(payload, null, 2);
      renderResultSummary(payload);
      syncCompareControls(payload);
    }
    function setResultMessage(message) {
      result.textContent = message;
      resultTitle.textContent = "현재 결과";
      resultStatus.textContent = message;
      resultSummary.replaceChildren(summaryItem("상태", message));
      compareVisible = false;
      syncCompareControls(null);
    }
    function buildGenerationStages(data) {
      return [
        {key: "request", label: "요청"},
        {key: "wildcards", label: "프롬프트 / 와일드카드"},
        {key: "text_encode", label: "텍스트 인코드"},
        {key: "base_t2i", label: "기본 렌더"},
        {key: "high_res_fix", label: "고해상도 / 업스케일", optional: !data.upscale?.enabled},
        {key: "vae_decode", label: "VAE 디코드"},
        ...(data.face_detailer?.mask_backend === "sam3"
          ? [
              {key: "face_eye_detailer", label: "얼굴 + 눈 보정", optional: !data.face_detailer?.enabled || data.face_detailer?.sam3_face_eyes === false},
              {key: "hand_detailer", label: "손 보정", optional: !data.face_detailer?.enabled || !data.face_detailer?.sam3_hands}
            ]
          : [{key: "face_detailer", label: "페이스 디테일러", optional: !data.face_detailer?.enabled}]),
        {key: "metadata", label: "메타데이터 저장"}
      ];
    }
    function nextRunnableStageIndex(items, index) {
      for (let next = index + 1; next < items.length; next += 1) {
        if (!items[next].optional) {
          return next;
        }
      }
      return index;
    }
    function stageStateFromManifest(item, manifestStages, finalState) {
      if (finalState === "failed") {
        return item.optional ? "skipped" : "failed";
      }
      if (["request", "wildcards", "text_encode", "metadata"].includes(item.key)) {
        return "completed";
      }
      const stage = manifestStages[item.key] || {};
      if (stage.status === "completed") {
        return "completed";
      }
      if (stage.status === "disabled" || stage.status === "skipped" || stage.method === "not_run" || item.optional) {
        return "skipped";
      }
      if (stage.status) {
        return stage.status;
      }
      return "completed";
    }
    function renderGenerationStages(items, activeIndex, manifestStages = null, finalState = "running", message = "") {
      if (finalState === "running") {
        clearGenerationStageHide();
      }
      generationStages.hidden = false;
      generationStages.setAttribute("aria-busy", finalState === "running" ? "true" : "false");
      generationStageSummary.textContent = finalState === "running" ? "작업 중" : (finalState === "failed" ? (message ? `실패: ${message}` : "실패") : "");
      generationStageList.replaceChildren(...items.map((item, index) => {
        let state = "pending";
        if (manifestStages) {
          state = stageStateFromManifest(item, manifestStages, finalState);
        } else if (item.optional) {
          state = "skipped";
        } else if (index < activeIndex) {
          state = "completed";
        } else if (index === activeIndex) {
          state = "active";
        }
        const row = document.createElement("li");
        row.className = "stage-item";
        row.setAttribute("data-stage-key", item.key);
        row.setAttribute("data-state", state);
        row.setAttribute("aria-label", `${item.label}: ${stageStateLabels[state] || state}`);
        const marker = document.createElement("span");
        marker.className = "stage-marker";
        marker.setAttribute("aria-hidden", "true");
        const label = document.createElement("span");
        label.textContent = item.label;
        const status = document.createElement("span");
        status.className = "stage-state";
        status.textContent = stageVisibleStateLabels[state] ?? stageStateLabels[state] ?? state;
        row.append(marker, label, status);
        return row;
      }));
    }
    function stopStageProgress() {
      if (stageTimer) {
        window.clearInterval(stageTimer);
        stageTimer = null;
      }
    }
    function clearGenerationStageHide() {
      if (stageHideTimer) {
        window.clearTimeout(stageHideTimer);
        stageHideTimer = null;
      }
    }
    function scheduleGenerationStageHide(finalState) {
      clearGenerationStageHide();
      if (finalState !== "completed") {
        return;
      }
      stageHideTimer = window.setTimeout(() => {
        generationStages.hidden = true;
        stageHideTimer = null;
      }, 1200);
    }
    function createProgressId() {
      if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
      }
      return `progress-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
    function stopProgressPolling() {
      if (progressPollTimer) {
        window.clearInterval(progressPollTimer);
        progressPollTimer = null;
      }
      activeProgressId = "";
    }
    async function pollGenerationProgress(progressId) {
      const response = await fetch("/api/progress/" + encodeURIComponent(progressId), {cache: "no-store"});
      if (progressId !== activeProgressId || response.status === 404) {
        return;
      }
      const payload = await response.json();
      if (!response.ok) {
        return;
      }
      const finalState = payload.status === "failed" ? "failed" : (payload.status === "completed" ? "completed" : "running");
      renderGenerationStages(activeStageItems, activeStageItems.length, payload.stages || {}, finalState, payload.summary || payload.error || "");
      if (finalState !== "running") {
        stopProgressPolling();
      }
    }
    function startProgressPolling(progressId) {
      stopProgressPolling();
      activeProgressId = progressId;
      pollGenerationProgress(progressId).catch(() => {});
      progressPollTimer = window.setInterval(() => {
        pollGenerationProgress(progressId).catch(() => {});
      }, 700);
    }
    function startStageProgress(items) {
      stopStageProgress();
      clearGenerationStageHide();
      activeStageItems = items;
      activeStageIndex = 0;
      renderGenerationStages(activeStageItems, activeStageIndex);
      generationStages.scrollIntoView({block: "nearest", behavior: "smooth"});
    }
    function finishGenerationStages(manifestStages, finalState = "completed", message = "") {
      stopProgressPolling();
      stopStageProgress();
      if (!activeStageItems.length) {
        activeStageItems = buildGenerationStages({});
      }
      renderGenerationStages(activeStageItems, activeStageItems.length, manifestStages, finalState, message);
      scheduleGenerationStageHide(finalState);
    }
    function clearOutputPreview() {
      currentOutputUrl = "";
      currentMaskUrl = "";
      preview.removeAttribute("src");
      preview.hidden = true;
      outputLink.removeAttribute("href");
      outputLink.hidden = true;
      sam3Status.textContent = "결과 이미지를 선택하면 마스크를 만들 수 있습니다.";
    }
    function showOutputPreview(url) {
      currentOutputUrl = url;
      currentMaskUrl = "";
      preview.src = url + "?t=" + Date.now();
      preview.hidden = false;
      outputLink.href = url;
      outputLink.hidden = false;
      sam3Status.textContent = "SAM3 마스크를 만들 수 있습니다.";
    }
    function setCurrentMaskFromPayload(payload) {
      currentMaskUrl = payload.mask_url || currentMaskUrl;
      if (payload.overlay_url) {
        preview.src = payload.overlay_url + "?t=" + Date.now();
        preview.hidden = false;
      }
    }
    async function segmentCurrentImageWithSam3() {
      if (!currentOutputUrl) {
        sam3Status.textContent = "먼저 결과 이미지를 선택하세요.";
        return;
      }
      const prompt = sam3Prompt.value.trim();
      if (!prompt) {
        sam3Status.textContent = "마스크 프롬프트를 입력하세요.";
        return;
      }
      sam3SegmentButton.disabled = true;
      sam3Status.textContent = "SAM3 마스크 생성 중...";
      try {
        const response = await fetch("/api/sam3/segment", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({image_path: currentOutputUrl, prompt, threshold: 0.25})
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          sam3Status.textContent = payload.error || "SAM3 마스크 생성 실패";
          return;
        }
        setCurrentMaskFromPayload(payload);
        sam3Status.textContent = `마스크 생성 완료: ${payload.boxes?.length || 0}개 영역`;
      } catch (error) {
        sam3Status.textContent = String(error);
        setResultPayload({error: String(error)});
      } finally {
        sam3SegmentButton.disabled = false;
      }
    }
    function renderSam3Presets() {
      sam3Presets.replaceChildren(...sam3PromptPresets.map((prompt) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "sam3-preset";
        button.textContent = prompt;
        button.addEventListener("click", () => {
          sam3Prompt.value = prompt;
        });
        return button;
      }));
    }
    function renderSam3CompareResults(items) {
      sam3Results.replaceChildren(...items.map((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "sam3-result";
        const bestScore = Math.max(...(item.scores || [0]));
        const boxCount = item.boxes?.length || 0;
        button.dataset.hasMask = String(boxCount > 0);
        button.textContent = `${item.prompt}: ${boxCount} / ${bestScore.toFixed(2)}`;
        button.addEventListener("click", () => {
          sam3Prompt.value = item.prompt;
          setCurrentMaskFromPayload(item);
          setResultPayload({status: "sam3_selected", ...item});
        });
        return button;
      }));
    }
    async function compareCurrentImageWithSam3() {
      if (!currentOutputUrl) {
        sam3Status.textContent = "먼저 결과 이미지를 선택하세요.";
        return;
      }
      sam3CompareButton.disabled = true;
      sam3SegmentButton.disabled = true;
      sam3Status.textContent = "SAM3 후보 비교 중...";
      try {
        const response = await fetch("/api/sam3/compare", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({image_path: currentOutputUrl, prompts: sam3ClothingComparePrompts, threshold: 0.15})
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          sam3Status.textContent = payload.error || "SAM3 후보 비교 실패";
          return;
        }
        renderSam3CompareResults(payload.results || []);
        if (payload.best?.overlay_url) {
          sam3Prompt.value = payload.best.prompt || sam3Prompt.value;
          setCurrentMaskFromPayload(payload.best);
        }
        const bestCount = payload.best?.boxes?.length || 0;
        sam3Status.textContent = `후보 비교 완료: ${payload.count || 0}개, 최고 ${bestCount}개 영역`;
      } catch (error) {
        sam3Status.textContent = String(error);
        setResultPayload({error: String(error)});
      } finally {
        sam3CompareButton.disabled = false;
        sam3SegmentButton.disabled = false;
      }
    }
    async function adjustCurrentMask() {
      if (!currentOutputUrl || !currentMaskUrl) {
        sam3Status.textContent = "먼저 SAM3 마스크를 생성하거나 후보를 선택하세요.";
        return;
      }
      maskAdjustButton.disabled = true;
      sam3Status.textContent = "마스크 조정 중...";
      try {
        const response = await fetch("/api/masks/adjust", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            image_path: currentOutputUrl,
            mask_path: currentMaskUrl,
            dilation: Number(maskDilationInput.value || 0),
            feather: Number(maskFeatherInput.value || 0)
          })
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          sam3Status.textContent = payload.error || "마스크 조정 실패";
          return;
        }
        setCurrentMaskFromPayload(payload);
        sam3Status.textContent = `마스크 조정 완료: 확장 ${payload.dilation}px, 페더 ${payload.feather}px`;
      } catch (error) {
        sam3Status.textContent = String(error);
        setResultPayload({error: String(error)});
      } finally {
        maskAdjustButton.disabled = false;
      }
    }
    async function runMaskedInpaint() {
      if (!currentOutputUrl || !currentMaskUrl) {
        sam3Status.textContent = "먼저 조정할 마스크를 선택하세요.";
        return;
      }
      const prompt = inpaintPromptInput.value.trim();
      if (!prompt) {
        sam3Status.textContent = "바꿀 내용을 입력하세요.";
        return;
      }
      maskedInpaintButton.disabled = true;
      sam3SegmentButton.disabled = true;
      sam3CompareButton.disabled = true;
      maskAdjustButton.disabled = true;
      sam3Status.textContent = "인페인트 생성 중...";
      const seedValue = inpaintSeedInput.value.trim();
      try {
        const response = await fetch("/api/inpaint/masked", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            image_path: currentOutputUrl,
            mask_path: currentMaskUrl,
            prompt,
            checkpoint: checkpointSelect.value,
            negative_prompt: inpaintNegativeInput.value,
            method: inpaintMethodSelect.value || "noise_mask",
            denoise: Number(inpaintDenoiseInput.value || 0.65),
            steps: Number(inpaintStepsInput.value || 20),
            cfg: Number(inpaintCfgInput.value || 3.5),
            seed: seedValue ? Number(seedValue) : null
          })
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          sam3Status.textContent = payload.error || "인페인트 실패";
          return;
        }
        if (payload.output_url) {
          showOutputPreview(payload.output_url);
        }
        sam3Status.textContent = `인페인트 완료: ${payload.method}, seed ${payload.seed}`;
        refreshHistory().catch(() => {});
      } catch (error) {
        sam3Status.textContent = String(error);
        setResultPayload({error: String(error)});
      } finally {
        maskedInpaintButton.disabled = false;
        sam3SegmentButton.disabled = false;
        sam3CompareButton.disabled = false;
        maskAdjustButton.disabled = false;
      }
    }
    function setSelectValue(select, value) {
      if (value && ![...select.options].some((option) => option.value === value)) {
        select.add(new Option(`${value} (누락)`, value));
      }
      select.value = value || "";
    }
    function renderCheckpointOptions(inventory, selectedCheckpoint) {
      const defaultCheckpoint = inventory.default || animaDefaults.checkpoint;
      const seen = new Set();
      const options = [];
      const addOption = (label, value) => {
        if (!seen.has(value)) {
          seen.add(value);
          options.push(new Option(label, value));
        }
      };
      addOption(defaultCheckpoint, defaultCheckpoint);
      (inventory.items || []).forEach((item) => addOption(item.relative_path, item.relative_path));
      checkpointSelect.replaceChildren(...options);
      setSelectValue(checkpointSelect, selectedCheckpoint || defaultCheckpoint);
    }
    function renderLoraSelectOptions(select, selectedPath = "") {
      select.replaceChildren(
        new Option("없음", ""),
        ...loraCatalog.map((item) => new Option(item.relative_path, item.relative_path))
      );
      setSelectValue(select, selectedPath);
    }
    function syncLoraRemoveButtons() {
      const rows = [...loraList.querySelectorAll(".lora-row")];
      rows.forEach((row) => {
        const button = row.querySelector("[data-remove-lora]");
        if (button) {
          button.disabled = rows.length <= 1;
        }
      });
    }
    function addLoraRow(config = {}) {
      const row = document.createElement("div");
      row.className = "lora-row";
      const selectWrap = document.createElement("div");
      const selectLabel = document.createElement("label");
      selectLabel.textContent = "LoRA";
      const select = document.createElement("select");
      select.className = "lora-path";
      select.setAttribute("aria-label", "LoRA 경로");
      renderLoraSelectOptions(select, config.path || "");
      selectWrap.append(selectLabel, select);

      const strengthWrap = document.createElement("div");
      const strengthLabel = document.createElement("label");
      strengthLabel.textContent = "강도";
      const strength = document.createElement("input");
      strength.className = "lora-strength";
      strength.type = "number";
      strength.min = "0";
      strength.step = "0.05";
      strength.value = config.model_strength ?? config.strength ?? 1;
      strength.setAttribute("aria-label", "LoRA 강도");
      strengthWrap.append(strengthLabel, strength);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary-button";
      remove.dataset.removeLora = "1";
      remove.textContent = "삭제";
      remove.addEventListener("click", () => {
        row.remove();
        if (!loraList.querySelector(".lora-row")) {
          addLoraRow();
        }
        syncLoraRemoveButtons();
      });

      row.append(selectWrap, strengthWrap, remove);
      loraList.append(row);
      syncLoraRemoveButtons();
      return row;
    }
    function loraRowConfigs() {
      return [...loraList.querySelectorAll(".lora-row")].map((row) => {
        const path = row.querySelector(".lora-path")?.value || "";
        const strength = Number(row.querySelector(".lora-strength")?.value || 1);
        return {path, model_strength: Number.isFinite(strength) ? strength : 1};
      });
    }
    function selectedLoras() {
      return loraRowConfigs()
        .filter((item) => item.path)
        .map((item) => ({path: item.path, model_strength: item.model_strength, clip_strength: item.model_strength}));
    }
    function setLoraRows(loras) {
      loraList.replaceChildren();
      const rows = loras.length ? loras : [{}];
      rows.forEach((item) => addLoraRow(item));
      syncLoraRemoveButtons();
    }
    async function loadStatus() {
      const [healthResponse, loraResponse, checkpointResponse, readinessResponse, versionResponse] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/loras"),
        fetch("/api/checkpoints"),
        fetch("/api/readiness"),
        fetch("/api/version")
      ]);
      const health = await healthResponse.json();
      const loras = await loraResponse.json();
      const checkpoints = await checkpointResponse.json();
      const readiness = await readinessResponse.json();
      const version = await versionResponse.json();
      const selectedCheckpoint = checkpointSelect.value;
      const currentLoraRows = loraRowConfigs();
      renderCheckpointOptions(checkpoints, selectedCheckpoint);
      loraCatalog = loras.items || [];
      setLoraRows(currentLoraRows.length ? currentLoraRows : [{}]);
      statusPanel.replaceChildren(
        statusCard("모델", health.models.ready ? "준비됨" : `${health.models.missing.length}개 누락`),
        statusCard("체크포인트", `${checkpoints.count}개 로컬`),
        statusCard("LoRA", `${loras.count}개 사용 가능`),
        statusCard("출력", health.outputs.image_root)
      );
      renderUpdateStatus(version);
      renderReadiness(readiness);
    }
    function historyType(item) {
      return item.output_url ? "images" : "dry-run";
    }
    function historyTypeLabel(item) {
      return item.output_url ? "이미지" : "드라이런";
    }
    function filteredHistoryItems() {
      if (historyFilter === "all") {
        return historyItems;
      }
      return historyItems.filter((item) => historyType(item) === historyFilter);
    }
    function historyCard(item) {
      const card = document.createElement("article");
      card.className = `history-item history-item-${historyType(item)}`;
      const manifestName = item.manifest_path.split(/[\/]/).pop();
      card.tabIndex = 0;
      if (item.output_url) {
        const image = document.createElement("img");
        image.className = "history-thumb";
        image.src = item.output_url;
        image.alt = "";
        card.append(image);
      } else {
        const placeholder = document.createElement("div");
        placeholder.className = "history-thumb history-thumb-empty";
        placeholder.textContent = "생성 정보";
        card.append(placeholder);
      }
      const body = document.createElement("div");
      body.className = "history-card-body";
      const title = document.createElement("strong");
      title.textContent = item.prompt || "(빈 프롬프트)";
      const type = document.createElement("span");
      type.className = "history-type";
      type.textContent = historyTypeLabel(item);
      const meta = document.createElement("span");
      meta.textContent = `${statusLabel(item.status || "unknown")} / ${item.output_url || "이미지 없음"}`;
      body.append(title, type, meta);
      card.append(body);
      const actions = document.createElement("div");
      actions.className = "history-actions";
      actions.addEventListener("click", (event) => event.stopPropagation());
      const manifestButton = document.createElement("button");
      manifestButton.type = "button";
      manifestButton.className = "history-action";
      manifestButton.textContent = "상세";
      manifestButton.title = "생성 정보 보기";
      manifestButton.addEventListener("click", () => openManifest(manifestName));
      actions.append(manifestButton);
      if (item.output_url) {
        const openOutput = document.createElement("a");
        openOutput.className = "history-action";
        openOutput.href = item.output_url;
        openOutput.target = "_blank";
        openOutput.rel = "noopener";
        openOutput.textContent = "열기";
        openOutput.title = "출력 이미지 열기";
        actions.append(openOutput);
      }
      const exportButton = document.createElement("button");
      exportButton.type = "button";
      exportButton.className = "history-action";
      exportButton.textContent = "내보내기";
      exportButton.title = "생성 정보 JSON 다운로드";
      exportButton.addEventListener("click", () => exportManifest(manifestName));
      actions.append(exportButton);
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "history-action danger";
      deleteButton.textContent = "삭제";
      deleteButton.title = "생성 정보와 관리 출력 이미지 삭제";
      deleteButton.addEventListener("click", () => deleteHistoryItem(manifestName));
      actions.append(deleteButton);
      card.append(actions);
      card.addEventListener("click", () => openManifest(manifestName, {showCompare: false}));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openManifest(manifestName, {showCompare: false});
        }
      });
      return card;
    }
    function renderHistory() {
      const visibleItems = filteredHistoryItems();
      historyFilters.forEach((button) => {
        button.classList.toggle("active", button.dataset.historyFilter === historyFilter);
      });
      historyCount.textContent = `${visibleItems.length} / ${historyItems.length} 표시`;
      if (!visibleItems.length) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        empty.textContent = "아직 표시할 히스토리가 없습니다.";
        history.replaceChildren(empty);
        return;
      }
      history.replaceChildren(...visibleItems.map(historyCard));
    }
    async function loadHistory() {
      const response = await fetch("/api/history?limit=8");
      const payload = await response.json();
      historyItems = payload.items || [];
      renderHistory();
    }
    async function openManifest(name, options = {}) {
      const response = await fetch("/api/manifests/" + encodeURIComponent(name));
      const payload = await response.json();
      currentManifest = payload;
      compareVisible = Boolean(options.showCompare);
      setResultPayload(payload);
      clearOutputPreview();
      if (payload.output_url) {
        showOutputPreview(payload.output_url);
      }
      syncCompareControls(payload);
    }
    async function exportManifest(name) {
      const response = await fetch("/api/manifests/" + encodeURIComponent(name));
      const payload = await response.json();
      if (!response.ok || payload.error) {
        setResultPayload(payload);
        return;
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setResultPayload({status: "manifest_exported", filename: name});
    }
    async function deleteHistoryItem(name) {
      if (!window.confirm(`${name} 생성 기록과 연결된 출력 이미지를 삭제할까요?`)) {
        return;
      }
      const response = await fetch("/api/manifests/" + encodeURIComponent(name), {method: "DELETE"});
      const payload = await response.json();
      const currentName = currentManifest?.manifest_path?.split(/[\/]/).pop();
      if (response.ok && currentName === name) {
        currentManifest = null;
        clearOutputPreview();
      }
      setResultPayload(payload);
      if (response.ok) {
        await loadHistory();
        await loadStatus();
      }
    }
    async function loadPresets() {
      const response = await fetch("/api/presets");
      const payload = await response.json();
      presets = payload.items || [];
      presetSelect.replaceChildren(
        new Option(presets.length ? "프리셋 선택" : "저장된 프리셋 없음", ""),
        ...presets.map((item) => new Option(item.name, item.slug))
      );
    }
    async function exportPresets() {
      const response = await fetch("/api/presets/export");
      const payload = await response.json();
      if (!response.ok || payload.error) {
        setResultPayload(payload);
        return;
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "anima-app-settings-presets.json";
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setResultPayload({status: "settings_exported", count: payload.count});
    }
    async function importPresetsFromFile(file) {
      if (!file) {
        return;
      }
      try {
        const bundle = JSON.parse(await file.text());
        const response = await fetch("/api/presets/import", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(bundle)
        });
        const payload = await response.json();
        setResultPayload(payload);
        await loadPresets();
      } catch (error) {
        setResultPayload({error: String(error)});
      } finally {
        presetImportFile.value = "";
      }
    }
    async function loadWildcards() {
      const response = await fetch("/api/wildcards");
      const payload = await response.json();
      const items = payload.items || [];
      const presets = payload.presets || [];
      wildcardSelect.replaceChildren(
        new Option(items.length ? "와일드카드 선택" : "와일드카드 파일 없음", ""),
        ...items.map((item) => new Option(`${item.name} (${item.value_count})`, item.token))
      );
      presetWildcardSelect.replaceChildren(
        new Option(presets.length ? "프리셋 선택" : "프롬프트 프리셋 없음", ""),
        ...presets.map((item) => new Option(`${item.name} (${item.value_count})`, item.token))
      );
    }
    function insertWildcard() {
      insertTokenAtPrompt(wildcardSelect.value);
    }
    function insertPresetWildcard() {
      insertTokenAtPrompt(presetWildcardSelect.value);
    }
    function insertTokenAtPrompt(token) {
      if (!token) {
        return;
      }
      const prompt = form.elements.prompt;
      const start = prompt.selectionStart ?? prompt.value.length;
      const end = prompt.selectionEnd ?? prompt.value.length;
      const before = prompt.value.slice(0, start);
      const after = prompt.value.slice(end);
      const insertion = formatWildcardInsertion(token, before, after);
      prompt.value = before + insertion + after;
      const nextCursor = start + insertion.length;
      prompt.focus();
      prompt.setSelectionRange(nextCursor, nextCursor);
    }
    function formatWildcardInsertion(token, before, after) {
      const prefix = before.trim().length ? (before.trimEnd().endsWith(",") ? " " : ", ") : "";
      const suffix = after.trim().length ? (after.trimStart().startsWith(",") ? " " : ", ") : ",";
      return `${prefix}${token}${suffix}`;
    }
    function autocompleteTargets() {
      return [
        form.elements.prompt,
        form.elements.negative_prompt,
        inpaintPromptInput,
        inpaintNegativeInput
      ].filter(Boolean);
    }
    function currentAutocompleteFragment(input) {
      const cursor = input.selectionStart ?? input.value.length;
      const before = input.value.slice(0, cursor);
      const marker = Math.max(before.lastIndexOf(","), before.lastIndexOf("\n"));
      const rawStart = marker + 1;
      const leading = before.slice(rawStart).match(/^\s*/)?.[0] || "";
      const start = rawStart + leading.length;
      const query = before.slice(start);
      if (query.length < 2) {
        return null;
      }
      return {start, end: cursor, query};
    }
    function hideAutocomplete() {
      autocompleteMenu.hidden = true;
      autocompleteMenu.replaceChildren();
      autocompleteItems = [];
      autocompleteIndex = -1;
      autocompleteFragment = null;
    }
    function positionAutocomplete(input) {
      const rect = input.getBoundingClientRect();
      autocompleteMenu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - 432))}px`;
      autocompleteMenu.style.top = `${Math.min(rect.bottom + 4, window.innerHeight - 272)}px`;
    }
    function setAutocompleteIndex(index) {
      autocompleteIndex = index;
      [...autocompleteMenu.querySelectorAll(".autocomplete-item")].forEach((button, buttonIndex) => {
        button.classList.toggle("active", buttonIndex === autocompleteIndex);
      });
    }
    function renderAutocomplete(input, items) {
      autocompleteItems = items || [];
      autocompleteMenu.replaceChildren();
      if (!autocompleteItems.length) {
        hideAutocomplete();
        return;
      }
      autocompleteItems.forEach((item, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "autocomplete-item";
        button.setAttribute("role", "option");
        const label = document.createElement("span");
        label.textContent = item.value;
        const count = document.createElement("span");
        count.className = "autocomplete-item-count";
        count.textContent = item.count ? item.count.toLocaleString() : "";
        button.append(label, count);
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          applyAutocompleteItem(index);
        });
        autocompleteMenu.append(button);
      });
      autocompleteActiveInput = input;
      autocompleteMenu.hidden = false;
      positionAutocomplete(input);
      setAutocompleteIndex(0);
    }
    async function requestAutocomplete(input) {
      const fragment = currentAutocompleteFragment(input);
      autocompleteFragment = fragment;
      if (!fragment) {
        hideAutocomplete();
        return;
      }
      try {
        const response = await fetch(`/api/autocomplete?q=${encodeURIComponent(fragment.query)}&limit=24`);
        const payload = await response.json();
        if (autocompleteActiveInput && autocompleteActiveInput !== input) {
          return;
        }
        renderAutocomplete(input, payload.items || []);
      } catch (error) {
        hideAutocomplete();
      }
    }
    function scheduleAutocomplete(input) {
      autocompleteActiveInput = input;
      window.clearTimeout(autocompleteTimer);
      autocompleteTimer = window.setTimeout(() => requestAutocomplete(input), 90);
    }
    function applyAutocompleteItem(index = autocompleteIndex) {
      const input = autocompleteActiveInput;
      const item = autocompleteItems[index];
      const fragment = input ? (autocompleteFragment || currentAutocompleteFragment(input)) : null;
      if (!input || !item || !fragment) {
        hideAutocomplete();
        return;
      }
      const before = input.value.slice(0, fragment.start);
      const after = input.value.slice(fragment.end);
      const suffix = after.trim().length && !after.trimStart().startsWith(",") ? ", " : "";
      input.value = before + item.value + suffix + after;
      const cursor = before.length + item.value.length + suffix.length;
      input.focus();
      input.setSelectionRange(cursor, cursor);
      hideAutocomplete();
      input.dispatchEvent(new Event("input", {bubbles: true}));
    }
    function handleAutocompleteKeydown(event) {
      if (autocompleteMenu.hidden) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setAutocompleteIndex((autocompleteIndex + 1) % autocompleteItems.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setAutocompleteIndex((autocompleteIndex - 1 + autocompleteItems.length) % autocompleteItems.length);
      } else if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        applyAutocompleteItem();
      } else if (event.key === "Escape") {
        event.preventDefault();
        hideAutocomplete();
      }
    }
    function setupAutocomplete() {
      autocompleteTargets().forEach((input) => {
        input.addEventListener("input", () => scheduleAutocomplete(input));
        input.addEventListener("keydown", handleAutocompleteKeydown);
        input.addEventListener("blur", () => window.setTimeout(hideAutocomplete, 120));
      });
      window.addEventListener("resize", hideAutocomplete);
      document.addEventListener("scroll", hideAutocomplete, true);
    }
    function renderWildcardPreview(payload) {
      const lines = [];
      if (payload.error) {
        lines.push(`오류: ${payload.error}`);
      }
      lines.push("프롬프트:");
      lines.push(payload.prompt || "");
      if (payload.negative_prompt) {
        lines.push("");
        lines.push("네거티브:");
        lines.push(payload.negative_prompt);
      }
      lines.push("");
      lines.push(`선택: ${payload.selection_count || 0}`);
      (payload.selections || []).forEach((item, index) => {
        const label = item.wildcard || item.type || "항목";
        const value = item.expanded_value || item.value || "";
        lines.push(`${index + 1}. ${label}: ${value}`);
      });
      wildcardPreview.textContent = lines.join("\n");
      wildcardPreview.hidden = false;
    }
    async function previewWildcards() {
      previewWildcardsButton.disabled = true;
      try {
        const response = await fetch("/api/wildcards/preview", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(buildRequestData())
        });
        const payload = await response.json();
        renderWildcardPreview(payload);
      } catch (error) {
        renderWildcardPreview({error: String(error), prompt: form.elements.prompt.value, selection_count: 0, selections: []});
      } finally {
        previewWildcardsButton.disabled = false;
      }
    }
    async function refinePromptWithLlm() {
      const prompt = form.elements.prompt.value.trim();
      if (!prompt) {
        llmPromptStatus.textContent = "프롬프트가 비어 있음";
        return;
      }
      const refinePriority = llmRefinePrioritySelect.value === "natural" ? "natural" : "tag";
      const refinePriorityLabel = refinePriority === "natural" ? "natural-language priority" : "tag priority";
      const previousText = llmRefinePromptButton.textContent;
      llmRefinePromptButton.disabled = true;
      llmRefinePromptButton.textContent = "LLM 처리 중...";
      llmPromptStatus.textContent = "LLM 보정 중...";
      try {
        const response = await fetch("/api/llm/generate", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            prompt_prefix: [
              "Clean and refine an image-generation prompt before final generation.",
              "Return JSON only. Do not return markdown, code fences, quotes around the JSON, explanations, or negative prompts.",
              "Detect contradictions and remove or rewrite the weaker side before writing the final prompt.",
              "Examples of contradictions: full body vs portrait, standing vs sitting, long hair vs short hair, multiple hair colors, multiple eye colors, indoor vs outdoor, day vs night, solo vs multiple characters, and conflicting outfit descriptions.",
              "If priority is tag priority, preserve explicit tags, LoRA trigger words, character names, style tokens, pose tokens, and composition tags unless they directly conflict with stronger tags.",
              "If priority is natural-language priority, preserve the user's natural-language intent and remove conflicting tags that would fight that intent.",
              "Translate non-English natural-language descriptions into concise English, then remove the original non-English text from cleaned_prompt.",
              "Deduplicate repeated ideas. Keep important subject, style, composition, colors, outfit, pose, lighting, and mood.",
              "JSON schema: {\"cleaned_prompt\":\"comma-separated English tags after contradiction cleanup\",\"natural_language_prompt\":\"one concise English sentence that reinforces the cleaned prompt\",\"resolved_conflicts\":[\"short notes about removed or rewritten conflicts\"]}"
            ].join("\n"),
            prompt_suffix: "\nPriority: " + refinePriorityLabel + "\nPrompt: " + prompt + "\nJSON:",
            max_new_tokens: 180
          })
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "LLM request failed");
        }
        const completion = String(payload.completion_text || "").trim();
        if (!completion) {
          throw new Error("LLM returned an empty completion");
        }
        const refined = parseLlmPromptRefinement(completion, prompt, refinePriority);
        const nextPrompt = appendNaturalLanguagePrompt(refined.cleanedPrompt, refined.naturalLanguagePrompt);
        if (!nextPrompt) {
          throw new Error("LLM returned an empty refined prompt");
        }
        form.elements.prompt.value = nextPrompt;
        llmPromptStatus.textContent = refined.resolvedConflicts.length
          ? `LLM 보정 완료 (${refined.resolvedConflicts.length}개 정리)`
          : "LLM 보정 완료";
        setResultPayload({
          status: "llm_prompt_appended",
          original_prompt: prompt,
          refine_priority: refinePriority,
          cleaned_prompt: refined.cleanedPrompt,
          natural_language_prompt: refined.naturalLanguagePrompt,
          resolved_conflicts: refined.resolvedConflicts,
          llm_json_parsed: refined.jsonParsed,
          ...payload
        });
      } catch (error) {
        llmPromptStatus.textContent = "LLM 보정 실패";
        setResultPayload({error: String(error)});
      } finally {
        llmRefinePromptButton.textContent = previousText;
        llmRefinePromptButton.disabled = false;
      }
    }
    function appendNaturalLanguagePrompt(prompt, addition) {
      const base = String(prompt || "").trim();
      const natural = String(addition || "").trim().replace(/^["'`]+|["'`]+$/g, "");
      if (!base) {
        return natural;
      }
      if (!natural) {
        return base;
      }
      const separator = /[,.;:]$/.test(base) ? " " : ", ";
      return `${base}${separator}${natural}`;
    }
    function parseLlmPromptRefinement(rawCompletion, originalPrompt, refinePriority) {
      const raw = String(rawCompletion || "").trim();
      const fallbackCleaned = removeNonEnglishPromptParts(originalPrompt);
      const parsed = parseJsonObjectFromText(raw);
      if (parsed && typeof parsed === "object") {
        const cleanedPrompt = stringOrEmpty(parsed.cleaned_prompt) || fallbackCleaned;
        const naturalLanguagePrompt = stringOrEmpty(parsed.natural_language_prompt);
        const resolvedConflicts = Array.isArray(parsed.resolved_conflicts)
          ? parsed.resolved_conflicts.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
        return {
          cleanedPrompt,
          naturalLanguagePrompt,
          resolvedConflicts,
          refinePriority,
          jsonParsed: true
        };
      }
      return {
        cleanedPrompt: fallbackCleaned,
        naturalLanguagePrompt: stripJsonCodeFence(raw),
        resolvedConflicts: [],
        refinePriority,
        jsonParsed: false
      };
    }
    function parseJsonObjectFromText(text) {
      const raw = stripJsonCodeFence(text);
      if (!raw) {
        return null;
      }
      try {
        return JSON.parse(raw);
      } catch (_error) {
        const start = raw.indexOf("{");
        const end = raw.lastIndexOf("}");
        if (start >= 0 && end > start) {
          try {
            return JSON.parse(raw.slice(start, end + 1));
          } catch (_innerError) {
            return null;
          }
        }
        return null;
      }
    }
    function stringOrEmpty(value) {
      return typeof value === "string" ? value.trim().replace(/^["'`]+|["'`]+$/g, "") : "";
    }
    function stripJsonCodeFence(text) {
      return String(text || "")
        .trim()
        .replace(/^```(?:json)?\s*/i, "")
        .replace(/\s*```$/i, "")
        .trim();
    }
    function removeNonEnglishPromptParts(prompt) {
      return String(prompt || "")
        .split(/([,\n])/)
        .reduce((parts, chunk, index, chunks) => {
          if (chunk === "," || chunk === "\n") {
            return parts;
          }
          const value = chunk.trim();
          if (!value || containsNonEnglishText(value)) {
            return parts;
          }
          parts.push(value);
          return parts;
        }, [])
        .join(", ");
    }
    function containsNonEnglishText(text) {
      return /[぀-ヿ㐀-鿿가-힯Ѐ-ӿ؀-ۿ฀-๿]/.test(text);
    }
    function buildRequestData() {
      const data = Object.fromEntries(new FormData(form).entries());
      data.width = Number(data.width);
      data.height = Number(data.height);
      data.steps = Number(data.steps);
      data.cfg = Number(data.cfg);
      data.checkpoint = data.checkpoint || animaDefaults.checkpoint;
      if (data.i2i_image) {
        data.i2i = {enabled: true, image_path: data.i2i_image, denoise: Number(data.i2i_denoise || 0.35)};
      }
      if (data.upscale_enabled) {
        data.upscale = {
          enabled: true,
          scale: Number(data.upscale_scale || 1.5),
          steps: Number(data.upscale_steps || 10),
          denoise: Number(data.upscale_denoise || 0.35),
          method: data.upscale_method || "bicubic",
          tiled: Boolean(data.upscale_tiled),
          tile_size: Number(data.upscale_tile_size || 128),
          overlap: Number(data.upscale_overlap || 8)
        };
      }
      data.vae_decode = {
        mode: data.vae_decode_mode || "auto",
        tile_size: Number(data.vae_tile_size || 128),
        overlap: Number(data.vae_overlap || 8)
      };
      if (data.face_detailer_enabled) {
        data.face_detailer = {
          enabled: true,
          detector: data.face_detector || "default",
          mask_backend: data.face_mask_backend || "sam_b",
          threshold: Number(data.face_threshold || 0.5),
          crop_scale: Number(data.face_crop_scale || 1.5),
          padding: Number(data.face_padding || 32),
          feather: Number(data.face_feather || 24),
          exclude_forehead_ratio: Number(data.face_exclude_forehead || 0),
          steps: Number(data.face_steps || 10),
          denoise: Number(data.face_denoise || 0.28),
          sam3_face_eyes: Boolean(data.face_sam3_face_eyes),
          sam3_hands: Boolean(data.face_sam3_hands),
          hand_denoise: Number(data.hand_denoise || 0.35)
        };
      }
      const loras = selectedLoras();
      if (loras.length) {
        data.loras = loras;
      }
      delete data.i2i_image;
      delete data.i2i_denoise;
      delete data.upscale_enabled;
      delete data.upscale_scale;
      delete data.upscale_steps;
      delete data.upscale_denoise;
      delete data.upscale_method;
      delete data.upscale_tiled;
      delete data.upscale_tile_size;
      delete data.upscale_overlap;
      delete data.vae_decode_mode;
      delete data.vae_tile_size;
      delete data.vae_overlap;
      delete data.face_detailer_enabled;
      delete data.face_detector;
      delete data.face_mask_backend;
      delete data.face_threshold;
      delete data.face_crop_scale;
      delete data.face_padding;
      delete data.face_feather;
      delete data.face_exclude_forehead;
      delete data.face_steps;
      delete data.face_denoise;
      delete data.face_sam3_face_eyes;
      delete data.face_sam3_hands;
      delete data.hand_denoise;
      delete data.lora_path;
      delete data.lora_strength;
      delete data.queue_count;
      delete data.queue_infinite;
      delete data.queue_seed_mode;
      delete data.queue_delay;
      if (data.seed === "") {
        delete data.seed;
      } else {
        data.seed = Number(data.seed);
      }
      return data;
    }
    function syncSam3DetailerControls() {
      sam3DetailerControls.hidden = form.elements.face_mask_backend.value !== "sam3";
    }
    function applyPreset(item) {
      const request = item.request || {};
      const wildcardInfo = request.wildcards || {};
      form.elements.prompt.value = wildcardInfo.original_prompt || request.prompt || "";
      form.elements.negative_prompt.value = wildcardInfo.original_negative_prompt || request.negative_prompt || "";
      form.elements.width.value = request.width || animaDefaults.width;
      form.elements.height.value = request.height || animaDefaults.height;
      form.elements.steps.value = request.steps || animaDefaults.steps;
      form.elements.cfg.value = request.cfg || animaDefaults.cfg;
      form.elements.sampler.value = request.sampler || animaDefaults.sampler;
      form.elements.scheduler.value = request.scheduler || animaDefaults.scheduler;
      form.elements.seed.value = request.seed ?? "";
      form.elements.memory_profile.value = request.memory_profile || "auto";
      setSelectValue(checkpointSelect, request.checkpoint || animaDefaults.checkpoint);
      const wildcardMode = request.wildcard_mode || wildcardInfo.mode || "random";
      form.elements.wildcard_mode.value = wildcardMode === "off" ? "random" : wildcardMode;
      form.elements.i2i_image.value = request.i2i?.image_path || "";
      form.elements.i2i_denoise.value = request.i2i?.denoise ?? 0.35;
      form.elements.upscale_enabled.checked = Boolean(request.upscale?.enabled);
      form.elements.upscale_scale.value = request.upscale?.scale ?? 1.5;
      form.elements.upscale_steps.value = request.upscale?.steps ?? 10;
      form.elements.upscale_denoise.value = request.upscale?.denoise ?? 0.35;
      form.elements.upscale_method.value = request.upscale?.method || "bicubic";
      form.elements.upscale_tiled.checked = Boolean(request.upscale?.tiled);
      form.elements.upscale_tile_size.value = request.upscale?.tile_size ?? 128;
      form.elements.upscale_overlap.value = request.upscale?.overlap ?? 8;
      form.elements.vae_decode_mode.value = request.vae_decode?.mode || "auto";
      form.elements.vae_tile_size.value = request.vae_decode?.tile_size ?? 128;
      form.elements.vae_overlap.value = request.vae_decode?.overlap ?? 8;
      form.elements.face_detailer_enabled.checked = Boolean(request.face_detailer?.enabled);
      form.elements.face_detector.value = request.face_detailer?.detector || "default";
      form.elements.face_mask_backend.value = request.face_detailer?.mask_backend || "sam_b";
      form.elements.face_threshold.value = request.face_detailer?.threshold ?? 0.5;
      form.elements.face_crop_scale.value = request.face_detailer?.crop_scale ?? 1.5;
      form.elements.face_padding.value = request.face_detailer?.padding ?? 32;
      form.elements.face_feather.value = request.face_detailer?.feather ?? 24;
      form.elements.face_exclude_forehead.value = request.face_detailer?.exclude_forehead_ratio ?? 0;
      form.elements.face_steps.value = request.face_detailer?.steps ?? 10;
      form.elements.face_denoise.value = request.face_detailer?.denoise ?? 0.28;
      form.elements.face_sam3_face_eyes.checked = request.face_detailer?.sam3_face_eyes !== false;
      form.elements.face_sam3_hands.checked = Boolean(request.face_detailer?.sam3_hands);
      form.elements.hand_denoise.value = request.face_detailer?.hand_denoise ?? 0.35;
      syncSam3DetailerControls();
      referenceImageSection.open = Boolean(request.i2i?.image_path || request.upscale?.enabled || request.upscale?.tiled || (request.vae_decode?.mode && request.vae_decode.mode !== "auto"));
      faceDetailerSection.open = Boolean(request.face_detailer?.enabled);
      setLoraRows(request.loras || []);
      presetName.value = item.name || "";
    }
    function applyStartingSizePreset(key) {
      const preset = startingSizePresets[key];
      if (!preset) {
        return;
      }
      selectedStartingSize = key;
      const landscape = startingOrientation === "landscape" && preset.width !== preset.height;
      form.elements.width.value = landscape ? preset.height : preset.width;
      form.elements.height.value = landscape ? preset.width : preset.height;
      syncStartingPointButtons();
    }
    function applyStartingOrientation(orientation) {
      startingOrientation = orientation === "landscape" ? "landscape" : "portrait";
      const currentWidth = Number(form.elements.width.value || 0);
      const currentHeight = Number(form.elements.height.value || 0);
      if (currentWidth && currentHeight && currentWidth !== currentHeight) {
        form.elements.width.value = startingOrientation === "landscape" ? Math.max(currentWidth, currentHeight) : Math.min(currentWidth, currentHeight);
        form.elements.height.value = startingOrientation === "landscape" ? Math.min(currentWidth, currentHeight) : Math.max(currentWidth, currentHeight);
      }
      syncStartingPointButtons();
    }
    function applyLowVramHighresPreset() {
      form.elements.memory_profile.value = "low_vram_highres";
      form.elements.upscale_enabled.checked = true;
      form.elements.upscale_tiled.checked = true;
      form.elements.upscale_scale.value = form.elements.upscale_scale.value || 1.5;
      form.elements.upscale_steps.value = 10;
      form.elements.upscale_denoise.value = form.elements.upscale_denoise.value || 0.35;
      form.elements.upscale_tile_size.value = form.elements.upscale_tile_size.value || 128;
      form.elements.upscale_overlap.value = form.elements.upscale_overlap.value || 8;
      form.elements.vae_decode_mode.value = "tiled";
      form.elements.vae_tile_size.value = form.elements.vae_tile_size.value || 128;
      form.elements.vae_overlap.value = form.elements.vae_overlap.value || 8;
      referenceImageSection.open = true;
    }
    function syncStartingPointButtons() {
      startingSizeButtons.forEach((button) => {
        button.classList.toggle("is-selected", button.dataset.sizePreset === selectedStartingSize);
      });
      orientationButtons.forEach((button) => {
        button.classList.toggle("is-selected", button.dataset.orientation === startingOrientation);
      });
    }
    function applyManifest() {
      if (currentManifest) {
        applyPreset({name: currentManifest.prompt || "manifest", request: currentManifest});
      }
    }
    function queueCount() {
      const value = Number(queueCountInput.value || 1);
      return Math.max(1, Math.min(99, Number.isFinite(value) ? Math.floor(value) : 1));
    }
    function queueIsInfinite() {
      return Boolean(queueInfiniteInput.checked);
    }
    function queueTotalLabel(total) {
      return total === null ? "무한" : String(total);
    }
    function queueDelaySeconds() {
      const value = Number(queueDelayInput.value || 0);
      return Math.max(0, Math.min(60, Number.isFinite(value) ? value : 0));
    }
    function setQueueStatus(message) {
      queueStatus.textContent = message;
    }
    function setQueueControlsRunning(running) {
      queueRunning = running;
      queueCountInput.disabled = running;
      queueInfiniteInput.disabled = running;
      queueSeedMode.disabled = running;
      queueDelayInput.disabled = running;
      startQueueButton.disabled = running;
      stopQueueButton.disabled = !running;
      generateButton.disabled = running;
    }
    async function submitGenerateRequest(data, message = "생성 중...") {
      const progressId = createProgressId();
      data.progress_id = progressId;
      currentManifest = null;
      clearOutputPreview();
      setResultMessage(message);
      startStageProgress(buildGenerationStages(data));
      startProgressPolling(progressId);
      try {
        const response = await fetch("/api/generate", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(data)
        });
        const payload = await response.json();
        const succeeded = response.ok && !payload.error;
        finishGenerationStages(payload.stages || {}, succeeded ? "completed" : "failed", payload.error || "");
        setResultPayload(payload);
        if (!succeeded) {
          return {ok: false, payload};
        }
        if (payload.manifest_path) {
          const manifestName = payload.manifest_path.split(/[\/]/).pop();
          if (manifestName) {
            await openManifest(manifestName);
          }
        } else if (payload.output_url) {
          showOutputPreview(payload.output_url);
        }
        await loadStatus();
        await loadHistory();
        return {ok: true, payload};
      } catch (error) {
        finishGenerationStages({}, "failed", String(error));
        const payload = {error: String(error)};
        setResultPayload(payload);
        return {ok: false, payload};
      }
    }
    function stopServerQueuePolling() {
      if (serverQueuePollTimer) {
        window.clearInterval(serverQueuePollTimer);
        serverQueuePollTimer = null;
      }
    }
    function jobsForActiveBatch(payload) {
      const items = payload.items || [];
      if (!activeQueueBatchId) {
        return items;
      }
      return items.filter((item) => item.batch_id === activeQueueBatchId);
    }
    function queueSummaryForJobs(items) {
      const summary = {queued: 0, waiting: 0, running: 0, completed: 0, failed: 0, cancelled: 0};
      items.forEach((item) => {
        if (Object.prototype.hasOwnProperty.call(summary, item.status)) {
          summary[item.status] += 1;
        }
      });
      return summary;
    }
    function queueIsSettled(items) {
      return items.length > 0 && !items.some((item) => ["queued", "waiting", "running"].includes(item.status));
    }
    function renderServerQueueStatus(payload) {
      const items = jobsForActiveBatch(payload);
      const summary = queueSummaryForJobs(items);
      const active = items.find((item) => item.status === "running") || items.find((item) => item.status === "waiting") || items.find((item) => item.status === "queued");
      const total = items.length;
      setQueueStatus(`등록 ${summary.queued}, 대기 ${summary.waiting}, 실행 ${summary.running}, 완료 ${summary.completed}, 실패 ${summary.failed}, 취소 ${summary.cancelled}`);
      if (active?.progress_id && active.status === "running" && active.progress_id !== activeProgressId) {
        startStageProgress(buildGenerationStages(active.request || {}));
        startProgressPolling(active.progress_id);
      }
      return {items, summary, total};
    }
    async function showLatestQueueResult(items) {
      const latest = [...items].reverse().find((item) => item.result && ["completed", "failed"].includes(item.status));
      if (!latest?.result) {
        return;
      }
      const manifestPath = latest.result.manifest_path || "";
      if (manifestPath && manifestPath === lastQueueResultManifest) {
        return;
      }
      lastQueueResultManifest = manifestPath;
      setResultPayload(latest.result);
      if (latest.result.manifest_path) {
        const manifestName = latest.result.manifest_path.split(/[\/]/).pop();
        if (manifestName) {
          await openManifest(manifestName);
        }
      } else if (latest.result.output_url) {
        showOutputPreview(latest.result.output_url);
      }
      await loadStatus();
      await loadHistory();
    }
    async function pollServerQueue() {
      const response = await fetch("/api/jobs", {cache: "no-store"});
      const payload = await response.json();
      if (!response.ok) {
        setQueueStatus(payload.error || "큐 상태 확인 실패");
        return;
      }
      const rendered = renderServerQueueStatus(payload);
      await showLatestQueueResult(rendered.items);
      if (queueRunning && queueIsSettled(rendered.items)) {
        setQueueControlsRunning(false);
        queueRunning = false;
        stopServerQueuePolling();
        const failed = rendered.summary.failed;
        const cancelled = rendered.summary.cancelled;
        setQueueStatus(`큐 완료. 완료 ${rendered.summary.completed}, 실패 ${failed}, 취소 ${cancelled}.`);
        if (!activeProgressId) {
          finishGenerationStages({}, failed ? "failed" : "completed", failed ? "하나 이상의 작업 실패" : "");
        }
      }
    }
    function startServerQueuePolling() {
      stopServerQueuePolling();
      pollServerQueue().catch((error) => setQueueStatus(String(error)));
      serverQueuePollTimer = window.setInterval(() => {
        pollServerQueue().catch((error) => setQueueStatus(String(error)));
      }, 900);
    }
    async function enqueueServerJobs(baseData, total, infinite) {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          request: baseData,
          count: total || 1,
          infinite,
          seed_mode: queueSeedMode.value,
          delay_seconds: queueDelaySeconds()
        })
      });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || "큐 등록 실패");
      }
      activeQueueBatchId = payload.batch_id || "";
      lastQueueResultManifest = "";
      return payload;
    }
    async function cancelServerJob(jobId) {
      const response = await fetch("/api/jobs/" + encodeURIComponent(jobId) + "/cancel", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}"
      });
      return response.json();
    }
    async function startAutoQueue() {
      if (queueRunning) {
        return;
      }
      const infinite = queueIsInfinite();
      const total = infinite ? null : queueCount();
      const baseData = buildRequestData();
      setQueueControlsRunning(true);
      clearOutputPreview();
      setResultMessage(infinite ? "무한 큐 준비 중..." : `${total}개 작업 큐 등록 중...`);
      startStageProgress(buildGenerationStages(baseData));
      try {
        const queued = await enqueueServerJobs(baseData, total, infinite);
        setQueueStatus(infinite ? "서버 큐 실행 중: 무한 모드" : `서버 큐 ${queued.count} / ${queueTotalLabel(total)}개 등록됨`);
        startServerQueuePolling();
      } catch (error) {
        setQueueControlsRunning(false);
        finishGenerationStages({}, "failed", String(error));
        setResultPayload({error: String(error)});
        setQueueStatus(String(error));
      }
    }
    async function stopAutoQueue() {
      if (!queueRunning) {
        return;
      }
      stopQueueButton.disabled = true;
      setQueueStatus("서버 큐 정지 중...");
      try {
        const response = await fetch("/api/jobs", {cache: "no-store"});
        const payload = await response.json();
        const jobs = jobsForActiveBatch(payload).filter((item) => ["queued", "waiting", "running"].includes(item.status));
        await Promise.all(jobs.map((item) => cancelServerJob(item.id)));
        await pollServerQueue();
      } catch (error) {
        setQueueStatus(String(error));
      }
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (queueRunning) {
        return;
      }
      const button = generateButton;
      button.disabled = true;
      await submitGenerateRequest(buildRequestData(), "생성 중...");
      button.disabled = false;
    });
    savePresetButton.addEventListener("click", async () => {
      const name = presetName.value || form.elements.prompt.value.slice(0, 48) || "preset";
      const response = await fetch("/api/presets", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name, request: buildRequestData()})
      });
      const payload = await response.json();
      setResultPayload({status: "settings_saved", ...payload});
      await loadPresets();
      presetSelect.value = payload.slug || "";
    });
    applyPresetButton.addEventListener("click", () => {
      const item = presets.find((preset) => preset.slug === presetSelect.value);
      if (item) {
        applyPreset(item);
      }
    });
    exportPresetsButton.addEventListener("click", exportPresets);
    importPresetsButton.addEventListener("click", () => presetImportFile.click());
    presetImportFile.addEventListener("change", () => importPresetsFromFile(presetImportFile.files[0]));
    startingSizeButtons.forEach((button) => {
      button.addEventListener("click", () => applyStartingSizePreset(button.dataset.sizePreset || ""));
    });
    orientationButtons.forEach((button) => {
      button.addEventListener("click", () => applyStartingOrientation(button.dataset.orientation || "portrait"));
    });
    lowVramHighresPresetButton.addEventListener("click", applyLowVramHighresPreset);
    syncStartingPointButtons();
    applyManifestButton.addEventListener("click", applyManifest);
    sam3SegmentButton.addEventListener("click", segmentCurrentImageWithSam3);
    sam3CompareButton.addEventListener("click", compareCurrentImageWithSam3);
    maskAdjustButton.addEventListener("click", adjustCurrentMask);
    maskedInpaintButton.addEventListener("click", runMaskedInpaint);
    toggleCompareButton.addEventListener("click", () => {
      compareVisible = !compareVisible;
      syncCompareControls(currentManifest);
    });
    insertWildcardButton.addEventListener("click", insertWildcard);
    insertPresetWildcardButton.addEventListener("click", insertPresetWildcard);
    previewWildcardsButton.addEventListener("click", previewWildcards);
    llmRefinePromptButton.addEventListener("click", refinePromptWithLlm);
    checkUpdateButton.addEventListener("click", checkForUpdates);
    addLoraButton.addEventListener("click", () => addLoraRow());
    setupAutocomplete();
    startQueueButton.addEventListener("click", () => {
      startAutoQueue().catch((error) => {
        setQueueControlsRunning(false);
        setQueueStatus(`큐 실패: ${String(error)}`);
        setResultPayload({error: String(error)});
      });
    });
    stopQueueButton.addEventListener("click", stopAutoQueue);
    historyFilters.forEach((button) => {
      button.addEventListener("click", () => {
        historyFilter = button.dataset.historyFilter || "all";
        renderHistory();
      });
    });
    readinessPanel.addEventListener("click", (event) => {
      const button = event.target.closest("[data-profile]");
      if (!button) {
        return;
      }
      prepareModelProfile(button.dataset.profile, button);
    });
    loraImportForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = loraImportForm.querySelector('button[type="submit"]');
      button.disabled = true;
      const data = Object.fromEntries(new FormData(loraImportForm).entries());
      try {
        const response = await fetch("/api/loras/import", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(data)
        });
        const payload = await response.json();
        setResultPayload({status: payload.error ? "lora_import_failed" : "lora_imported", ...payload});
        await loadStatus();
      } catch (error) {
        setResultPayload({error: String(error)});
      } finally {
        button.disabled = false;
      }
    });
    addLoraRow();
    form.elements.face_mask_backend.addEventListener("change", syncSam3DetailerControls);
    syncSam3DetailerControls();
    renderSam3Presets();
    function reportStartupError(label, error) {
      setResultPayload({status: "startup_error", error: `${label} 불러오기 실패: ${String(error)}`});
    }
    loadStatus().catch((error) => reportStartupError("상태", error));
    loadHistory().catch((error) => reportStartupError("기록", error));
    loadPresets().catch((error) => reportStartupError("설정", error));
    loadWildcards().catch((error) => reportStartupError("와일드카드", error));
    renderResultSummary();
