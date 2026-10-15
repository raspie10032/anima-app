const tr = window.AppI18n.msg;
    const {text: naiText, bind: naiBind} = window.NaiI18n;
    const animaDefaults = JSON.parse(document.getElementById("anima-defaults").textContent);
    const form = document.getElementById("generate-form");
    const sam3DetailerControls = document.getElementById("sam3-detailer-controls");
    const loraImportForm = document.getElementById("lora-import-form");
    const loraUploadButton = loraImportForm.querySelector('button[type="submit"]');
    const loraFileInput = document.getElementById("lora-file");
    const loraDropZone = document.getElementById("lora-drop-zone");
    const loraUploadStatus = document.getElementById("lora-upload-status");
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
    const sideStatusPanel = document.getElementById("side-status-panel");
    const readinessPanel = document.getElementById("readiness-panel");
    const updateStatus = document.getElementById("update-status");
    const checkUpdateButton = document.getElementById("check-update");
    const updateLink = document.getElementById("update-link");
    const generationStages = document.getElementById("generation-stages");
    const generationStageList = document.getElementById("generation-stage-list");
    const generationStageSummary = document.getElementById("generation-stage-summary");
    const history = document.getElementById("history");
    const historyCount = document.getElementById("history-count");
    const historyStorage = document.getElementById("history-storage");
    const historySearchForm = document.getElementById("history-search-form");
    const historySearchInput = document.getElementById("history-search");
    const historyLoadMore = document.getElementById("history-load-more");
    const historyFilters = [...document.querySelectorAll("[data-history-filter]")];
    const checkpointSelect = document.getElementById("checkpoint-select");
    const providerSelect = document.getElementById("provider-select");
    const providerStatus = document.getElementById("provider-status");
    const novelAISettings = document.getElementById("novelai-settings");
    const naiEffective = document.getElementById("nai-effective");
    let providerCapabilities = null;
    let naiTokenConfigured = false;
    const naiCharacters = document.getElementById("nai-characters");
    const naiCharacterCount = document.getElementById("nai-character-count");
    const naiAddCharacter = document.getElementById("nai-add-character");
    const naiUseCoords = document.getElementById("nai-use-coords");
    const naiUseOrder = document.getElementById("nai-use-order");
    const convertField = document.getElementById("convert-field");
    const convertApply = document.getElementById("convert-apply");
    let conversion = null;
    let conversionRevision = 0;
    const loraList = document.getElementById("lora-list");
    const addLoraButton = document.getElementById("add-lora");
    const presetName = document.getElementById("preset-name");
    const presetSelect = document.getElementById("preset-select");
    const savePresetButton = document.getElementById("save-preset");
    const applyPresetButton = document.getElementById("apply-preset");
    const exportPresetsButton = document.getElementById("export-presets");
    const importPresetsButton = document.getElementById("import-presets");
    const presetImportFile = document.getElementById("preset-import-file");
    const presetStatus = document.getElementById("preset-status");
    const applyManifestButton = document.getElementById("apply-manifest");
    const naiMetadataFile = document.getElementById("nai-metadata-file");
    const naiMetadataDropZone = document.getElementById("nai-metadata-drop-zone");
    const naiMetadataStatus = document.getElementById("nai-metadata-status");
    const naiMetadataPreview = document.getElementById("nai-metadata-preview");
    const naiMetadataModel = document.getElementById("nai-metadata-model");
    const applyNaiMetadataButton = document.getElementById("apply-nai-metadata");
    let naiMetadata = null;
    let naiMetadataRevision = 0;
    const naiOperation = document.getElementById("nai-operation");
    naiOperation.value = "generate";
    const naiInpaintInputs = document.getElementById("nai-inpaint-inputs");
    const naiInpaintStatus = document.getElementById("nai-inpaint-status");
    const naiMaskCanvas = document.getElementById("nai-mask-canvas");
    const naiInputPreview = document.getElementById("nai-input-preview");
    const naiMaskBuffer = document.createElement("canvas");
    let naiInputObjectUrl = null;
    let naiMaskPointer = null;
    const sam3Tools = document.getElementById("sam3-tools");
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
    const autocompleteStatus = document.getElementById("autocomplete-status");
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
    const referenceFileInput = document.getElementById("reference-file");
    const referenceDropZone = document.getElementById("reference-drop-zone");
    const referenceUploadStatus = document.getElementById("reference-upload-status");
    const referencePreview = document.getElementById("reference-preview");
    const removeReferenceButton = document.getElementById("remove-reference");
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
    let historyNextCursor = "";
    let historyHasMore = false;
    let historyTotalCount = 0;
    let historyRequestRevision = 0;
    let historySearchTimer = null;
    let historyLoading = false;
    let loraCatalog = [];
    let referencePreviewUrl = "";
    let activeUploadCount = 0;
    let referenceUploadRevision = 0;
    let referenceUploadController = null;
    let loraUploadInFlight = false;
    let stageTimer = null;
    let stageHideTimer = null;
    let progressPollTimer = null;
    let taggerJob = null;
    let taggerPollTimer = null;
    let taggerSubmitting = false;
    let activeProgressId = "";
    let activeStageItems = [];
    let activeStageIndex = 0;
    let queueRunning = false;
    let serverQueuePollTimer = null;
    let activeQueueBatchId = "";
    let lastQueueResultJobId = "";
    let generationReadiness = null;
    let readinessRequestRevision = 0;
    let autocompleteTimer = null;
    let autocompleteRequestRevision = 0;
    let autocompleteActiveInput = null;
    let autocompleteItems = [];
    let autocompleteIndex = -1;
    let autocompleteFragment = null;
    const stageStateLabels = {
      pending: tr("대기"),
      active: tr("진행 중"),
      completed: tr("완료"),
      skipped: tr("건너뜀"),
      failed: tr("실패"),
      cancelled: tr("취소됨")
    };
    const stageVisibleStateLabels = {
      pending: "",
      active: tr("진행 중"),
      completed: "",
      skipped: "",
      failed: tr("실패"),
      cancelled: tr("취소")
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
      window.AppI18n.setText(title, () => label);
      const body = document.createElement("span");
      window.AppI18n.setText(body, () => value);
      card.append(title, body);
      return card;
    }
    function updateStatusText(payload) {
      if (!payload) {
        return tr("확인 전");
      }
      if (payload.status === "update_available") {
        return tr`새 버전 있음: ${payload.latest_version}`;
      }
      if (payload.status === "up_to_date") {
        return tr`최신 상태: ${payload.current_version}`;
      }
      if (payload.status === "update_check_failed") {
        return tr("업데이트 확인 실패");
      }
      if (payload.version) {
        return tr`현재: ${payload.version}`;
      }
      return payload.error || tr("알 수 없음");
    }
    function renderUpdateStatus(payload) {
      window.AppI18n.setText(updateStatus, () => updateStatusText(payload));
      const href = payload?.latest_url || payload?.repository_url || "https://github.com/raspie10032/anima-app";
      updateLink.href = href;
      window.AppI18n.setText(updateLink, () => payload?.status === "update_available" ? tr("릴리스") : "GitHub");
    }
    async function checkForUpdates() {
      const previousText = checkUpdateButton.textContent;
      checkUpdateButton.disabled = true;
      window.AppI18n.setText(checkUpdateButton, () => tr("확인 중..."));
      window.AppI18n.setText(updateStatus, () => tr("GitHub 확인 중..."));
      try {
        const response = await fetch("/api/update-check");
        const payload = await response.json();
        renderUpdateStatus(payload);
        setResultPayload(payload);
      } catch (error) {
        renderUpdateStatus({status: "update_check_failed", error: String(error)});
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        window.AppI18n.setText(checkUpdateButton, () => previousText);
        checkUpdateButton.disabled = false;
      }
    }
    function readinessActionLabel(profile) {
      if (profile.ready) {
        return tr("준비됨");
      }
      return profile.prepare_source === "local" ? tr("로컬에서 복사") : tr("다운로드");
    }
    function formatByteSize(value) {
      if (value === null || value === undefined || value === "") {
        return tr("용량 미확인");
      }
      const bytes = Number(value);
      if (!Number.isFinite(bytes) || bytes < 0) {
        return tr("용량 미확인");
      }
      if (bytes >= 1024 ** 3) {
        return `${(bytes / (1024 ** 3)).toFixed(2)} GB`;
      }
      if (bytes >= 1024 ** 2) {
        return `${(bytes / (1024 ** 2)).toFixed(1)} MB`;
      }
      return `${Math.max(0, Math.round(bytes / 1024))} KB`;
    }
    function renderHistoryStorage(outputs = {}) {
      if (!historyStorage) {
        return;
      }
      const imageCount = Number(outputs.image_count) || 0;
      const manifestCount = Number(outputs.manifest_count) || 0;
      const managedBytes = outputs.managed_bytes ?? ((Number(outputs.image_bytes) || 0) + (Number(outputs.manifest_bytes) || 0));
      window.AppI18n.setText(historyStorage, () => tr`이미지 ${imageCount.toLocaleString(window.AppI18n.locale)}개 · ${formatByteSize(outputs.image_bytes)} / 기록 ${manifestCount.toLocaleString(window.AppI18n.locale)}개 · ${formatByteSize(outputs.manifest_bytes)} / 관리 합계 ${formatByteSize(managedBytes)} / 디스크 여유 ${formatByteSize(outputs.disk_free_bytes)}`);
    }
    function readinessSourceLabel(profile) {
      const size = formatByteSize(profile.prepare_size_bytes);
      if (profile.prepare_source === "local") {
        return tr`로컬 복사 · ${size}`;
      }
      if (profile.prepare_source === "huggingface") {
        return tr`Hugging Face 다운로드 · ${size}`;
      }
      return tr`원격 다운로드 · ${size}`;
    }
    function readinessRequirementLabel(requirement) {
      return {required: tr("필수"), recommended: tr("권장"), optional: tr("선택")}[requirement] || tr("선택");
    }
    function generationReadinessCard(generation = {}) {
      const card = document.createElement("article");
      card.className = "readiness-card generation-readiness-card";
      card.dataset.ready = String(Boolean(generation.ready));
      const title = document.createElement("strong");
      window.AppI18n.setText(title, () => tr("현재 생성 요청"));
      const summary = document.createElement("span");
      const problemCount = (generation.missing_files || []).length + (generation.invalid_files || []).length;
      window.AppI18n.setText(summary, () => generation.dry_run
        ? tr`드라이런 · 모델 검사 생략 · ${generation.checkpoint || tr("체크포인트 미선택")}`
        : generation.ready
          ? tr`실행 가능 · ${generation.checkpoint}`
          : tr`실행 불가 · ${problemCount}개 파일 미준비 · ${generation.checkpoint || tr("체크포인트 미선택")}`);
      const files = document.createElement("ul");
      files.className = "readiness-files";
      for (const path of generation.missing_files || []) {
        const file = document.createElement("li");
        window.AppI18n.setText(file, () => tr`누락 ${path}`);
        files.append(file);
      }
      for (const path of generation.invalid_files || []) {
        const file = document.createElement("li");
        window.AppI18n.setText(file, () => tr`손상 ${path}`);
        files.append(file);
      }
      card.append(title, summary, files);
      return card;
    }
    function syncGenerationControls() {
      const localPreview = ["detail", "focused_infill"].includes(naiOperation.value) && document.getElementById("nai-detailer-preview").checked;
      const blocked = providerSelect.value === "novelai"
        ? !providerCapabilities || (!providerCapabilities.default_dry_run && !naiTokenConfigured && !localPreview)
        : Boolean(generationReadiness && !generationReadiness.ready);
      const uploadBlocked = activeUploadCount > 0;
      generateButton.disabled = queueRunning || blocked || uploadBlocked;
      startQueueButton.disabled = queueRunning || blocked || uploadBlocked;
      const explanation = uploadBlocked
        ? tr("파일 업로드가 끝날 때까지 기다려 주세요.")
        : (blocked ? (providerSelect.value === "novelai" ? tr("NAI_ACCESS_TOKEN 환경변수와 엔진 상태를 확인하세요.") : tr("선택한 체크포인트의 필수 모델 파일을 먼저 준비하세요.")) : "");
      window.AppI18n.setProperty(generateButton, "title", () => explanation);
      window.AppI18n.setProperty(startQueueButton, "title", () => explanation);
      providerSelect.disabled = queueRunning || uploadBlocked;
      applyNaiMetadataButton.disabled = queueRunning || uploadBlocked || !naiMetadata || !naiMetadataModel.value;
      naiOperation.disabled = providerSelect.value !== "novelai" || queueRunning || uploadBlocked;
      naiInpaintInputs.querySelectorAll("input, select, button").forEach((input) => {
        input.disabled = naiInpaintInputs.hidden || queueRunning || uploadBlocked;
      });
      document.getElementById("nai-reference-panel").querySelectorAll("input, select, button").forEach((input) => {
        input.disabled = providerSelect.value !== "novelai" || queueRunning || uploadBlocked;
      });
      document.getElementById("nai-detailer-panel").querySelectorAll("input, select, button").forEach((input) => {
        input.disabled = providerSelect.value !== "novelai" || queueRunning || uploadBlocked;
      });
      syncTaggerControls();
    }
    function renderReadiness(payload) {
      const profiles = payload.profiles || [];
      generationReadiness = payload.generation || null;
      const cards = profiles.map((profile) => {
        const card = document.createElement("article");
        card.className = "readiness-card";
        card.dataset.ready = String(Boolean(profile.ready));
        const title = document.createElement("strong");
        window.AppI18n.setText(title, () => `${profile.label || profile.name} · ${readinessRequirementLabel(profile.requirement)}`);
        const summary = document.createElement("span");
        const problems = [];
        if (profile.missing_count) problems.push(tr`${profile.missing_count}개 누락`);
        if (profile.invalid_count) problems.push(tr`${profile.invalid_count}개 손상`);
        window.AppI18n.setText(summary, () => profile.ready ? tr("준비됨") : `${problems.join(" · ")} · ${readinessSourceLabel(profile)}`);
        const files = document.createElement("ul");
        files.className = "readiness-files";
        for (const item of profile.files || []) {
          const file = document.createElement("li");
          const fileStatus = item.valid ? tr("확인됨") : (item.exists ? tr("손상") : tr("누락"));
          window.AppI18n.setText(file, () => `${fileStatus} ${item.relative_path}`);
          files.append(file);
        }
        const action = document.createElement("button");
        action.type = "button";
        action.className = "secondary-button readiness-action";
        action.dataset.profile = profile.name;
        action.dataset.source = profile.prepare_source || "auto";
        action.dataset.sizeBytes = profile.prepare_size_bytes ?? "";
        window.AppI18n.setText(action, () => readinessActionLabel(profile));
        action.disabled = Boolean(profile.ready);
        card.append(title, summary, files, action);
        return card;
      });
      readinessPanel.replaceChildren(generationReadinessCard(payload.generation), ...cards);
      syncGenerationControls();
    }
    async function prepareModelProfile(profile, button) {
      const previousText = button.textContent;
      const source = button.dataset.source || "auto";
      const sourceDescription = source === "local"
        ? tr`로컬 원본에서 ${formatByteSize(button.dataset.sizeBytes)}를 복사합니다.`
        : tr`${source === "huggingface" ? "Hugging Face" : tr("원격 저장소")}에서 다운로드합니다. 다운로드 용량은 아직 확인되지 않았습니다.`;
      if (!window.confirm(tr`${sourceDescription}\n계속할까요?`)) {
        return;
      }
      button.disabled = true;
      window.AppI18n.setText(button, () => tr("준비 중..."));
      try {
        const response = await fetch("/api/models/prepare", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({profile, source})
        });
        const payload = await response.json();
        setResultPayload({status: response.ok ? "profile_prepared" : "profile_prepare_failed", ...payload});
        await loadStatus();
      } catch (error) {
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        window.AppI18n.setText(button, () => previousText);
        button.disabled = false;
      }
    }
    function summaryItem(label, value) {
      const item = document.createElement("div");
      item.className = "summary-item";
      const title = document.createElement("strong");
      window.AppI18n.setText(title, () => label);
      const body = document.createElement("span");
      window.AppI18n.setText(body, () => value);
      item.append(title, body);
      return item;
    }
    function resultMode(payload) {
      if (payload?.error) {
        return tr("실패");
      }
      if (payload?.dry_run || payload?.status === "dry_run") {
        return tr("드라이런");
      }
      if (payload?.status) {
        return statusLabel(payload.status);
      }
      return tr("준비됨");
    }
    function statusLabel(status) {
      const labels = {
        generated: tr("생성됨"),
        previewed: tr("디테일러 미리보기"),
        dry_run: tr("드라이런"),
        manifest_exported: tr("생성 정보 내보냄"),
        settings_exported: tr("설정 내보냄"),
        settings_saved: tr("설정 저장됨"),
        profile_prepared: tr("모델 준비 완료"),
        profile_prepare_failed: tr("모델 준비 실패"),
        lora_imported: tr("LoRA 가져오기 완료"),
        lora_import_failed: tr("LoRA 가져오기 실패"),
        deleted: tr("삭제됨"),
        unknown: tr("알 수 없음")
      };
      return labels[status] || status;
    }
    function renderResultSummary(payload = null) {
      if (!payload) {
        window.AppI18n.setText(resultTitle, () => tr("현재 결과"));
        window.AppI18n.setText(resultStatus, () => tr("준비됨"));
        resultSummary.replaceChildren(summaryItem(tr("상태"), tr("준비됨")));
        return;
      }
      if (payload.error) {
        const modelsNotReady = payload.error_code === "models_not_ready";
        window.AppI18n.setText(resultTitle, () => modelsNotReady ? tr("모델 준비 필요") : tr("요청 실패"));
        window.AppI18n.setText(resultStatus, () => modelsNotReady ? tr("준비 필요") : tr("실패"));
        resultSummary.replaceChildren(summaryItem(tr("오류"), payload.error));
        return;
      }
      const size = payload.width && payload.height ? `${payload.width}x${payload.height}` : tr("알 수 없음");
      const seed = payload.seed ?? tr("랜덤");
      const warnings = Array.isArray(payload.warnings) ? payload.warnings.filter(Boolean) : [];
      const upscale = payload.upscale?.enabled ? `${payload.upscale.scale || 1}x${payload.upscale.tiled ? tr(" 타일") : ""}` : tr("꺼짐");
      const faceTargets = payload.face_detailer?.mask_backend === "sam3"
        ? [payload.face_detailer?.sam3_face_eyes !== false ? tr("얼굴+눈") : "", payload.face_detailer?.sam3_hands ? tr("손") : ""].filter(Boolean).join(" / ")
        : tr("얼굴");
      const face = payload.face_detailer?.enabled ? tr`${faceTargets || tr("선택 없음")} · ${payload.face_detailer.steps || tr("자동")} 스텝` : tr("꺼짐");
      window.AppI18n.setText(resultTitle, () => payload.prompt || tr("현재 결과"));
      window.AppI18n.setText(resultStatus, () => warnings.length ? tr`${resultMode(payload)} · 경고 ${warnings.length}` : resultMode(payload));
      const items = [
        summaryItem(tr("엔진"), payload.provider === "novelai" ? "NovelAI" : tr("로컬 Anima")),
        summaryItem(tr("상태"), resultMode(payload)),
        summaryItem(tr("크기"), size),
        summaryItem(tr("스텝 / CFG"), `${payload.steps ?? "?"} / ${payload.cfg ?? "?"}`),
        summaryItem(tr("샘플러"), payload.sampler || "?"),
        summaryItem(tr("시드"), seed)
      ];
      if (payload.upscale?.enabled) {
        items.push(summaryItem(tr("업스케일"), upscale));
      }
      if (payload.face_detailer?.enabled) {
        items.push(summaryItem(tr("페이스 디테일러"), face));
      }
      const regions = payload.detailer_regions || payload.novelai?.detailer || [];
      if (regions.length) items.push(summaryItem(tr("NAI 보정 영역"), regions.map((r) =>
        `${r.region}: ${r.concept} → ${r.character ? tr`캐릭터 ${r.character_slot ?? r.character}` : tr("공통 / 미확정")} · ${r.status} (${r.reason})` +
        `${Number.isFinite(r.score) && Number.isFinite(r.margin) ? tr` · 점수 ${r.score.toFixed(3)} / 차이 ${r.margin.toFixed(3)}` : ""}` +
        `${r.tight_crop_retried ? tr(" · 좁은 크롭 재확인") : ""}${r.tagger ? ` · ${r.tagger.model_name}` : ""}${r.explanation ? ` · ${r.explanation}` : ""}`).join(" / ")));
      if (warnings.length) {
        items.push(summaryItem(tr("경고"), warnings.join(" · ")));
      }
      resultSummary.replaceChildren(...items);
    }
    function variantEntries(payload = currentManifest) {
      const variants = payload?.variants || {};
      const slots = [
        {key: "original", label: tr("원본")},
        {key: "upscale", label: tr("업스케일")},
        {key: "face_eye_detailer", label: tr("얼굴 + 눈")},
        {key: "hand_detailer", label: tr("손")}
      ];
      if (variants.face_detailer && !variants.face_eye_detailer && !variants.hand_detailer) {
        slots.push({key: "face_detailer", label: tr("페이스 디테일러")});
      }
      for (const [key, variant] of Object.entries(variants)) {
        if (key.startsWith("workflow_")) slots.push({key, label: variant.label || key});
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
        window.AppI18n.setText(title, () => entry.label);
        cell.append(title);
        if (entry.output_url) {
          const image = document.createElement("img");
          image.src = entry.output_url + "?t=" + Date.now();
          window.AppI18n.setProperty(image, "alt", () => entry.label);
          cell.append(image);
        } else {
          const empty = document.createElement("div");
          empty.className = "compare-empty";
          window.AppI18n.setText(empty, () => tr("생성 안 됨"));
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
      window.AppI18n.setText(toggleCompareButton, () => compareVisible ? tr("비교 숨기기") : tr("단계 비교"));
      renderCompareGrid(payload);
    }
    function setResultPayload(payload) {
      window.NaiErrors.render("nai-error-guide", payload);
      window.AppI18n.setText(result, () => JSON.stringify(payload, null, 2));
      renderResultSummary(payload);
      syncCompareControls(payload);
      if (payload?.error_code === "models_not_ready") {
        sideStatusPanel.open = true;
        sideStatusPanel.querySelector("summary")?.focus();
        loadStatus().catch(() => {});
      }
    }
    function setResultMessage(message) {
      window.NaiErrors.render("nai-error-guide", null);
      window.AppI18n.setText(result, () => message);
      window.AppI18n.setText(resultTitle, () => tr("현재 결과"));
      window.AppI18n.setText(resultStatus, () => message);
      resultSummary.replaceChildren(summaryItem(tr("상태"), message));
      compareVisible = false;
      syncCompareControls(null);
    }
    function buildGenerationStages(data) {
      if (data.provider === "novelai") {
        return [{key: "request", label: tr("요청")}, {key: "wildcards", label: tr("프롬프트 / 와일드카드")},
                {key: "base_t2i", label: tr("NovelAI 응답 대기")}, {key: "metadata", label: tr("결과 저장")}];
      }
      return [
        {key: "request", label: tr("요청")},
        {key: "wildcards", label: tr("프롬프트 / 와일드카드")},
        {key: "text_encode", label: tr("텍스트 인코드")},
        {key: "base_t2i", label: tr("기본 렌더")},
        {key: "high_res_fix", label: tr("고해상도 / 업스케일"), optional: !data.upscale?.enabled},
        {key: "vae_decode", label: tr("VAE 디코드")},
        ...(data.face_detailer?.mask_backend === "sam3"
          ? [
              {key: "face_eye_detailer", label: tr("얼굴 + 눈 보정"), optional: !data.face_detailer?.enabled || data.face_detailer?.sam3_face_eyes === false},
              {key: "hand_detailer", label: tr("손 보정"), optional: !data.face_detailer?.enabled || !data.face_detailer?.sam3_hands}
            ]
          : [{key: "face_detailer", label: tr("페이스 디테일러"), optional: !data.face_detailer?.enabled}]),
        {key: "metadata", label: tr("메타데이터 저장")}
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
      if (finalState === "cancelled") {
        return item.optional ? "skipped" : "cancelled";
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
      window.AppI18n.setText(generationStageSummary, () => finalState === "running"
        ? tr("작업 중")
        : (finalState === "failed"
          ? (message ? tr`실패: ${message}` : tr("실패"))
          : (finalState === "cancelled" ? (message || tr("취소됨")) : "")));
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
        window.AppI18n.setAttribute(row, "aria-label", () => `${item.label}: ${stageStateLabels[state] || state}`);
        const marker = document.createElement("span");
        marker.className = "stage-marker";
        marker.setAttribute("aria-hidden", "true");
        const label = document.createElement("span");
        window.AppI18n.setText(label, () => item.label);
        const status = document.createElement("span");
        status.className = "stage-state";
        window.AppI18n.setText(status, () => stageVisibleStateLabels[state] ?? stageStateLabels[state] ?? state);
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
      const finalState = payload.status === "failed"
        ? "failed"
        : (payload.status === "cancelled" ? "cancelled" : (payload.status === "completed" ? "completed" : "running"));
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
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      generationStages.scrollIntoView({block: "nearest", behavior: reducedMotion ? "auto" : "smooth"});
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
      window.AppI18n.setProperty(preview, "alt", () => tr("생성 결과 이미지"));
      preview.hidden = true;
      outputLink.removeAttribute("href");
      outputLink.hidden = true;
      sam3Tools.hidden = true;
      window.AppI18n.setText(sam3Status, () => tr("결과 이미지를 선택하면 마스크를 만들 수 있습니다."));
    }
    function showOutputPreview(url) {
      currentOutputUrl = url;
      currentMaskUrl = "";
      preview.src = url + "?t=" + Date.now();
      window.AppI18n.setProperty(preview, "alt", () => tr("생성 결과 이미지"));
      preview.hidden = false;
      outputLink.href = url;
      outputLink.hidden = false;
      sam3Tools.hidden = providerSelect.value === "novelai" || currentManifest?.provider === "novelai";
      window.AppI18n.setText(sam3Status, () => tr("SAM3 마스크를 만들 수 있습니다."));
    }
    function setCurrentMaskFromPayload(payload) {
      currentMaskUrl = payload.mask_url || currentMaskUrl;
      if (payload.overlay_url) {
        preview.src = payload.overlay_url + "?t=" + Date.now();
        window.AppI18n.setProperty(preview, "alt", () => tr("선택 영역이 표시된 생성 결과 이미지"));
        preview.hidden = false;
      }
    }
    async function segmentCurrentImageWithSam3() {
      if (!currentOutputUrl) {
        window.AppI18n.setText(sam3Status, () => tr("먼저 결과 이미지를 선택하세요."));
        return;
      }
      const prompt = sam3Prompt.value.trim();
      if (!prompt) {
        window.AppI18n.setText(sam3Status, () => tr("마스크 프롬프트를 입력하세요."));
        return;
      }
      sam3SegmentButton.disabled = true;
      window.AppI18n.setText(sam3Status, () => tr("SAM3 마스크 생성 중..."));
      try {
        const response = await fetch("/api/sam3/segment", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({image_path: currentOutputUrl, prompt, threshold: 0.25})
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          window.AppI18n.setText(sam3Status, () => payload.error || tr("SAM3 마스크 생성 실패"));
          return;
        }
        setCurrentMaskFromPayload(payload);
        window.AppI18n.setText(sam3Status, () => tr`마스크 생성 완료: ${payload.boxes?.length || 0}개 영역`);
        loadHistoryStorage().catch(() => {});
      } catch (error) {
        window.AppI18n.setText(sam3Status, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        sam3SegmentButton.disabled = false;
      }
    }
    function renderSam3Presets() {
      sam3Presets.replaceChildren(...sam3PromptPresets.map((prompt) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "sam3-preset";
        window.AppI18n.setText(button, () => prompt);
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
        window.AppI18n.setText(button, () => `${item.prompt}: ${boxCount} / ${bestScore.toFixed(2)}`);
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
        window.AppI18n.setText(sam3Status, () => tr("먼저 결과 이미지를 선택하세요."));
        return;
      }
      sam3CompareButton.disabled = true;
      sam3SegmentButton.disabled = true;
      window.AppI18n.setText(sam3Status, () => tr("SAM3 후보 비교 중..."));
      try {
        const response = await fetch("/api/sam3/compare", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({image_path: currentOutputUrl, prompts: sam3ClothingComparePrompts, threshold: 0.15})
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          window.AppI18n.setText(sam3Status, () => payload.error || tr("SAM3 후보 비교 실패"));
          return;
        }
        renderSam3CompareResults(payload.results || []);
        if (payload.best?.overlay_url) {
          sam3Prompt.value = payload.best.prompt || sam3Prompt.value;
          setCurrentMaskFromPayload(payload.best);
        }
        const bestCount = payload.best?.boxes?.length || 0;
        window.AppI18n.setText(sam3Status, () => tr`후보 비교 완료: ${payload.count || 0}개, 최고 ${bestCount}개 영역`);
        loadHistoryStorage().catch(() => {});
      } catch (error) {
        window.AppI18n.setText(sam3Status, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        sam3CompareButton.disabled = false;
        sam3SegmentButton.disabled = false;
      }
    }
    async function adjustCurrentMask() {
      if (!currentOutputUrl || !currentMaskUrl) {
        window.AppI18n.setText(sam3Status, () => tr("먼저 SAM3 마스크를 생성하거나 후보를 선택하세요."));
        return;
      }
      maskAdjustButton.disabled = true;
      window.AppI18n.setText(sam3Status, () => tr("마스크 조정 중..."));
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
          window.AppI18n.setText(sam3Status, () => payload.error || tr("마스크 조정 실패"));
          return;
        }
        setCurrentMaskFromPayload(payload);
        window.AppI18n.setText(sam3Status, () => tr`마스크 조정 완료: 확장 ${payload.dilation}px, 페더 ${payload.feather}px`);
        loadHistoryStorage().catch(() => {});
      } catch (error) {
        window.AppI18n.setText(sam3Status, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        maskAdjustButton.disabled = false;
      }
    }
    async function runMaskedInpaint() {
      if (!currentOutputUrl || !currentMaskUrl) {
        window.AppI18n.setText(sam3Status, () => tr("먼저 조정할 마스크를 선택하세요."));
        return;
      }
      const prompt = inpaintPromptInput.value.trim();
      if (!prompt) {
        window.AppI18n.setText(sam3Status, () => tr("바꿀 내용을 입력하세요."));
        return;
      }
      const inpaintSeed = seedNumberFromElement(inpaintSeedInput);
      if (!inpaintSeedInput.reportValidity()) {
        return;
      }
      maskedInpaintButton.disabled = true;
      sam3SegmentButton.disabled = true;
      sam3CompareButton.disabled = true;
      maskAdjustButton.disabled = true;
      window.AppI18n.setText(sam3Status, () => tr("인페인트 생성 중..."));
      try {
        const response = await fetch("/api/inpaint/masked", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            image_path: currentOutputUrl,
            mask_path: currentMaskUrl,
            prompt,
            checkpoint: checkpointSelect.value,
            loras: selectedLoras(),
            negative_prompt: inpaintNegativeInput.value,
            method: inpaintMethodSelect.value || "noise_mask",
            denoise: Number(inpaintDenoiseInput.value || 0.65),
            steps: Number(inpaintStepsInput.value || 20),
            cfg: Number(inpaintCfgInput.value || 3.5),
            seed: inpaintSeed
          })
        });
        const payload = await response.json();
        setResultPayload(payload);
        if (!response.ok) {
          window.AppI18n.setText(sam3Status, () => payload.error || tr("인페인트 실패"));
          return;
        }
        if (payload.output_url) {
          showOutputPreview(payload.output_url);
        }
        window.AppI18n.setText(sam3Status, () => tr`인페인트 완료: ${payload.method}, seed ${payload.seed}`);
        loadHistory().catch(() => {});
        loadHistoryStorage().catch(() => {});
      } catch (error) {
        window.AppI18n.setText(sam3Status, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        maskedInpaintButton.disabled = false;
        sam3SegmentButton.disabled = false;
        sam3CompareButton.disabled = false;
        maskAdjustButton.disabled = false;
      }
    }
    function setSelectValue(select, value) {
      if (value && ![...select.options].some((option) => option.value === value)) {
        select.add(new Option(tr`${value} (누락)`, value));
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
        new Option(tr("없음"), ""),
        ...loraCatalog.map((item) => new Option(item.relative_path, item.relative_path))
      );
      setSelectValue(select, selectedPath);
    }
    function syncLoraRemoveButtons() {
      const rows = [...loraList.querySelectorAll(".lora-row")];
      addLoraButton.disabled = loraUploadInFlight || rows.length >= animaDefaults.limits.max_loras;
      rows.forEach((row) => {
        const button = row.querySelector("[data-remove-lora]");
        if (button) {
          button.disabled = rows.length <= 1 || row.dataset.uploadReserved === "true";
        }
      });
    }
    function addLoraRow(config = {}, {focus = false} = {}) {
      const row = document.createElement("div");
      row.className = "lora-row";
      const selectWrap = document.createElement("div");
      const selectLabel = document.createElement("label");
      window.AppI18n.setText(selectLabel, () => "LoRA");
      const select = document.createElement("select");
      select.className = "lora-path";
      window.AppI18n.setAttribute(select, "aria-label", tr("LoRA 경로"));
      renderLoraSelectOptions(select, config.path || "");
      selectWrap.append(selectLabel, select);

      const strengthWrap = document.createElement("div");
      const strengthLabel = document.createElement("label");
      window.AppI18n.setText(strengthLabel, () => tr("강도"));
      const strength = document.createElement("input");
      strength.className = "lora-strength";
      strength.type = "number";
      strength.min = "0";
      strength.max = String(animaDefaults.limits.max_lora_strength);
      strength.step = "0.05";
      strength.value = config.model_strength ?? config.strength ?? 1;
      window.AppI18n.setAttribute(strength, "aria-label", tr("LoRA 강도"));
      strength.setAttribute("form", form.id);
      strengthWrap.append(strengthLabel, strength);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary-button";
      remove.dataset.removeLora = "1";
      window.AppI18n.setText(remove, () => tr("삭제"));
      remove.addEventListener("click", () => {
        const rows = [...loraList.querySelectorAll(".lora-row")];
        const rowIndex = rows.indexOf(row);
        const focusTarget = rows[rowIndex + 1]?.querySelector(".lora-path")
          || rows[rowIndex - 1]?.querySelector(".lora-path")
          || addLoraButton;
        row.remove();
        if (!loraList.querySelector(".lora-row")) {
          addLoraRow();
        }
        syncLoraRemoveButtons();
        focusTarget.focus();
      });

      row.append(selectWrap, strengthWrap, remove);
      loraList.append(row);
      syncLoraRemoveButtons();
      if (focus) {
        select.focus();
      }
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
    function setUploadActive(active) {
      activeUploadCount = Math.max(0, activeUploadCount + (active ? 1 : -1));
      syncGenerationControls();
    }
    function uploadsAreIdle({report = false} = {}) {
      if (activeUploadCount === 0) {
        return true;
      }
      if (report) {
        setResultMessage(tr("파일 업로드가 끝난 뒤 다시 시도해 주세요."));
      }
      return false;
    }
    function validateUploadFile(file, kind) {
      if (!(file instanceof File)) {
        throw new Error(tr("파일 한 개를 선택해 주세요."));
      }
      const name = file.name.toLowerCase();
      if (kind === "reference" || kind === "metadata") {
        if (kind === "metadata" && !/[.](png|webp)$/.test(name)) {
          throw new Error(tr("NAI PNG 또는 WebP 파일을 선택해 주세요."));
        }
        if (!/[.](png|jpe?g|webp)$/.test(name)) {
          throw new Error(tr("참조 이미지는 PNG, JPEG 또는 WebP만 사용할 수 있습니다."));
        }
        if (file.size > animaDefaults.limits.max_reference_upload_bytes) {
          throw new Error(tr`참조 이미지는 ${formatByteSize(animaDefaults.limits.max_reference_upload_bytes)} 이하여야 합니다.`);
        }
      } else {
        if (!name.endsWith(".safetensors")) {
          throw new Error(tr("LoRA는 .safetensors 파일만 사용할 수 있습니다."));
        }
        if (file.size > animaDefaults.limits.max_lora_upload_bytes) {
          throw new Error(tr`LoRA는 ${formatByteSize(animaDefaults.limits.max_lora_upload_bytes)} 이하여야 합니다.`);
        }
      }
      if (file.size <= 0) {
        throw new Error(tr("빈 파일은 업로드할 수 없습니다."));
      }
    }
    function uploadContentType(file, kind) {
      if (kind === "lora") {
        return "application/octet-stream";
      }
      const extension = file.name.toLowerCase().split(".").pop();
      return {
        png: "image/png",
        jpg: "image/jpeg",
        jpeg: "image/jpeg",
        webp: "image/webp"
      }[extension] || "application/octet-stream";
    }
    async function uploadFile(endpoint, file, kind, {signal} = {}) {
      const response = await fetch(`${endpoint}?filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: {"Content-Type": uploadContentType(file, kind)},
        body: file,
        signal
      });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw window.NaiErrors.asError(payload, tr("파일 업로드 실패"));
      }
      return payload;
    }
    function revokeReferencePreviewUrl() {
      if (referencePreviewUrl) {
        URL.revokeObjectURL(referencePreviewUrl);
        referencePreviewUrl = "";
      }
    }
    function setManagedReferencePath(path, file = null) {
      referenceFileInput.value = "";
      form.elements.i2i_image.value = path || "";
      revokeReferencePreviewUrl();
      if (file) {
        referencePreviewUrl = URL.createObjectURL(file);
        referencePreview.src = referencePreviewUrl;
        referencePreview.hidden = false;
      } else {
        referencePreview.removeAttribute("src");
        referencePreview.hidden = true;
      }
      window.AppI18n.setText(referenceUploadStatus, () => path ? tr`관리 파일: ${path}` : tr("선택된 이미지 없음"));
      removeReferenceButton.hidden = !path;
    }
    function cancelPendingReferenceUpload() {
      referenceUploadRevision += 1;
      referenceUploadController?.abort();
      referenceUploadController = null;
      referenceDropZone.removeAttribute("aria-busy");
    }
    async function uploadReferenceFile(file) {
      cancelPendingReferenceUpload();
      setManagedReferencePath("");
      validateUploadFile(file, "reference");
      const revision = ++referenceUploadRevision;
      const controller = new AbortController();
      referenceUploadController = controller;
      window.AppI18n.setText(referenceUploadStatus, () => tr`${file.name} 업로드 중...`);
      referenceDropZone.setAttribute("aria-busy", "true");
      setUploadActive(true);
      try {
        const payload = await uploadFile("/api/inputs/reference", file, "reference", {signal: controller.signal});
        if (revision !== referenceUploadRevision) {
          return null;
        }
        setManagedReferencePath(payload.relative_path, file);
        referenceImageSection.open = true;
        setResultPayload(payload);
        return payload;
      } catch (error) {
        if (revision !== referenceUploadRevision || error?.name === "AbortError") {
          return null;
        }
        setManagedReferencePath("");
        throw error;
      } finally {
        if (revision === referenceUploadRevision) {
          referenceUploadController = null;
          referenceDropZone.removeAttribute("aria-busy");
        }
        setUploadActive(false);
      }
    }
    function reserveLoraUploadRow() {
      const rows = [...loraList.querySelectorAll(".lora-row")];
      const emptyRow = rows.find((row) => !row.querySelector(".lora-path")?.value);
      if (emptyRow) {
        return emptyRow;
      }
      if (rows.length >= animaDefaults.limits.max_loras) {
        throw new Error(tr`LoRA 스택은 ${animaDefaults.limits.max_loras}개까지 사용할 수 있습니다.`);
      }
      return addLoraRow();
    }
    async function uploadLoraFile(file) {
      validateUploadFile(file, "lora");
      if (loraUploadInFlight) {
        throw new Error(tr("다른 LoRA 업로드가 끝날 때까지 기다려 주세요."));
      }
      const targetRow = reserveLoraUploadRow();
      const targetSelect = targetRow.querySelector(".lora-path");
      const targetRemove = targetRow.querySelector("[data-remove-lora]");
      loraUploadInFlight = true;
      targetRow.dataset.uploadReserved = "true";
      targetSelect.disabled = true;
      targetRemove.disabled = true;
      addLoraButton.disabled = true;
      loraFileInput.value = "";
      loraFileInput.disabled = true;
      loraUploadButton.disabled = true;
      loraDropZone.setAttribute("aria-busy", "true");
      window.AppI18n.setText(loraUploadStatus, () => tr`${file.name} 업로드 중...`);
      setUploadActive(true);
      try {
        const payload = await uploadFile("/api/loras/upload", file, "lora");
        setSelectValue(targetSelect, payload.relative_path);
        window.AppI18n.setText(loraUploadStatus, () => tr`업로드 완료: ${payload.relative_path}`);
        setResultPayload(payload);
        try {
          const response = await fetch("/api/loras", {cache: "no-store"});
          const inventory = await response.json();
          if (!response.ok || inventory.error) {
            throw new Error(inventory.error || tr("LoRA 목록 새로고침 실패"));
          }
          loraCatalog = inventory.items || [];
          [...loraList.querySelectorAll(".lora-path")].forEach((select) => {
            renderLoraSelectOptions(select, select.value);
          });
        } catch {
          window.AppI18n.setText(loraUploadStatus, () => tr`업로드 완료: ${payload.relative_path} · 목록 새로고침 실패`);
        }
        return payload;
      } finally {
        loraUploadInFlight = false;
        loraFileInput.disabled = false;
        loraUploadButton.disabled = false;
        loraDropZone.removeAttribute("aria-busy");
        delete targetRow.dataset.uploadReserved;
        targetSelect.disabled = false;
        syncLoraRemoveButtons();
        setUploadActive(false);
      }
    }
    async function readNaiMetadata(file) {
      window.NaiErrors.render("nai-metadata-error-guide", null);
      const revision = ++naiMetadataRevision;
      naiMetadata = null;
      naiMetadataPreview.hidden = true;
      syncGenerationControls();
      if (queueRunning || activeUploadCount > 0) {
        throw new Error(tr("생성과 파일 업로드가 끝난 뒤 생성 조건을 불러와 주세요."));
      }
      validateUploadFile(file, "metadata");
      setUploadActive(true);
      window.AppI18n.setText(naiMetadataStatus, () => tr`${file.name}: 메타데이터 읽는 중…`);
      try {
        const payload = await uploadFile("/api/metadata/novelai", file, "metadata");
        if (revision !== naiMetadataRevision) return;
        naiMetadata = payload;
        const request = payload.request;
        window.AppI18n.setText(document.getElementById("nai-metadata-summary"), () => [
          tr`모델 해시: ${payload.model_hash || tr("없음")}`,
          tr`원본 표기: ${payload.source_model || tr("미기록")}`,
          tr`모델 대응: ${payload.detected_model || tr("확인 필요")} · 생성 방식: ${{t2i: "T2I", i2i: "I2I", inpaint: tr("인페인트"), unknown: tr("확인 필요")}[payload.generation_mode]}`,
          tr`생성 크기: ${request.width ?? tr("미기록")} × ${request.height ?? tr("미기록")}`,
          tr`스텝: ${request.steps ?? tr("미기록")} · CFG: ${request.cfg ?? tr("미기록")} · 시드: ${request.seed ?? tr("미기록")}`,
          tr`샘플러: ${request.nai_sampler ?? tr("미기록")} · 스케줄러: ${request.nai_scheduler ?? tr("미기록")}`,
          `CFG rescale: ${request.nai_cfg_rescale ?? tr("미기록")} · Brownian: ${request.nai_prefer_brownian ?? tr("미기록")} · Variety boost: ${request.nai_variety_boost ?? tr("미기록")}`,
          "", tr("프롬프트"), request.prompt ?? tr("미기록"), "", tr("네거티브 프롬프트"), request.negative_prompt ?? tr("미기록")
        ].join("\n"));
        naiMetadataModel.replaceChildren(new Option(tr("모델을 확인하고 선택하세요"), ""),
          ...payload.model_candidates.map((value) => new Option(value, value)));
        document.getElementById("nai-metadata-summary").textContent += tr`\n\n캐릭터: ${request.nai_characters?.length ?? 0}명\n` +
          (request.nai_characters || []).map((c, index) => tr`캐릭터 ${index + 1} (${c.x}, ${c.y})\n${c.prompt}\n네거티브: ${c.negative_prompt}`).join("\n");
        naiMetadataModel.value = request.nai_model || "";
        window.AppI18n.setText(document.getElementById("nai-metadata-warnings"), () => payload.warnings.join("\n"));
        naiMetadataPreview.hidden = false;
        window.AppI18n.setText(applyNaiMetadataButton, () => payload.generation_mode === "inpaint"
          ? tr("인페인트 조건 적용") : payload.generation_mode === "i2i" ? tr("Img2Img 조건 적용") : tr("생성 조건 적용"));
        window.AppI18n.setText(naiMetadataStatus, () => tr`${file.name}: 생성 조건을 읽었습니다. 확인 후 적용하세요.`);
      } finally {
        naiMetadataFile.value = "";
        setUploadActive(false);
      }
    }
    function resetNaiEditor() {
      if (naiInputObjectUrl) URL.revokeObjectURL(naiInputObjectUrl);
      naiInputObjectUrl = null;
      naiInputPreview.removeAttribute("src");
      document.getElementById("nai-mask-editor").hidden = true;
      naiMaskCanvas.width = naiMaskBuffer.width = 0;
      naiMaskCanvas.height = naiMaskBuffer.height = 0;
      naiMaskPointer = null;
      window.AppI18n.setText(naiInpaintStatus, () => form.elements.input_image.value
        ? tr`입력: ${form.elements.input_image.value} · 마스크: ${form.elements.mask_image.value || tr("없음")}. 편집하려면 입력 파일을 다시 선택하세요.`
        : tr("입력 이미지와 수정할 마스크를 지정하세요."));
    }
    function redrawNaiMask() {
      const pixels = naiMaskBuffer.getContext("2d").getImageData(0, 0, naiMaskBuffer.width, naiMaskBuffer.height);
      for (let i = 0; i < pixels.data.length; i += 4) {
        const coverage = pixels.data[i];
        pixels.data[i] = 65;
        pixels.data[i + 1] = 145;
        pixels.data[i + 2] = 255;
        pixels.data[i + 3] = Math.round(coverage * 0.5);
      }
      naiMaskCanvas.getContext("2d").putImageData(pixels, 0, 0);
    }
    async function showNaiInput(url) {
      const image = new Image();
      image.src = url;
      await image.decode();
      naiInputPreview.src = url;
      naiMaskCanvas.width = naiMaskBuffer.width = image.naturalWidth;
      naiMaskCanvas.height = naiMaskBuffer.height = image.naturalHeight;
      const context = naiMaskBuffer.getContext("2d");
      context.fillStyle = "black";
      context.fillRect(0, 0, image.naturalWidth, image.naturalHeight);
      document.getElementById("nai-mask-editor").hidden = false;
      form.elements.width.value = image.naturalWidth;
      form.elements.height.value = image.naturalHeight;
      redrawNaiMask();
    }
    async function uploadNaiInput(file, mask = false) {
      if (queueRunning || !uploadsAreIdle()) return;
      validateUploadFile(file, "reference");
      if (mask && !form.elements.input_image.value) throw new Error(tr("입력 이미지를 먼저 지정하세요."));
      const field = mask ? form.elements.mask_image : form.elements.input_image;
      field.value = "";
      if (!mask) { form.elements.mask_image.value = ""; resetNaiEditor(); }
      setUploadActive(true);
      try {
        const uploaded = await uploadFile("/api/inputs/reference", file, "reference");
        const url = URL.createObjectURL(file);
        try {
          const image = new Image();
          image.src = url;
          await image.decode();
          if (mask) {
            if (image.naturalWidth !== Number(form.elements.width.value) || image.naturalHeight !== Number(form.elements.height.value)) {
              throw new Error(tr("입력 이미지와 마스크 크기가 다릅니다."));
            }
            if (naiMaskBuffer.width) {
              const ctx = naiMaskBuffer.getContext("2d");
              ctx.fillStyle = "black";
              ctx.fillRect(0, 0, naiMaskBuffer.width, naiMaskBuffer.height);
              ctx.drawImage(image, 0, 0);
              // Use luminance, matching the server's grayscale mask interpretation.
              const data = ctx.getImageData(0, 0, naiMaskBuffer.width, naiMaskBuffer.height);
              for (let i = 0; i < data.data.length; i += 4) {
                const gray = Math.round(0.299 * data.data[i] + 0.587 * data.data[i + 1] + 0.114 * data.data[i + 2]);
                data.data[i] = data.data[i + 1] = data.data[i + 2] = gray;
              }
              ctx.putImageData(data, 0, 0);
              redrawNaiMask();
            }
          } else {
            await showNaiInput(url);
            naiInputObjectUrl = url;
          }
          field.value = uploaded.relative_path;
        } finally { if (mask || naiInputObjectUrl !== url) URL.revokeObjectURL(url); }
        window.AppI18n.setText(naiInpaintStatus, () => tr`입력: ${form.elements.input_image.value} · 마스크: ${form.elements.mask_image.value || tr("그린 뒤 저장하세요")}`);
      } finally { setUploadActive(false); syncGenerationResourceValidity(); syncGenerationControls(); }
    }
    async function saveNaiMask() {
      if (queueRunning || !uploadsAreIdle() || !naiMaskBuffer.width) return;
      setUploadActive(true);
      try {
        const blob = await new Promise((resolve) => naiMaskBuffer.toBlob(resolve, "image/png"));
        if (!blob) throw new Error(tr("마스크를 저장할 수 없습니다."));
        const uploaded = await uploadFile("/api/inputs/reference", new File([blob], "inpaint-mask.png", {type: "image/png"}), "reference");
        form.elements.mask_image.value = uploaded.relative_path;
        window.AppI18n.setText(naiInpaintStatus, () => tr("그린 마스크를 저장했습니다. 전송 설정과 비용 한도를 확인하세요."));
      } finally { setUploadActive(false); syncGenerationResourceValidity(); syncGenerationControls(); }
    }
    function applyNaiMetadata() {
      if (!naiMetadata || !naiMetadataModel.value || queueRunning || !uploadsAreIdle()) return;
      // Apply only recognized fields. Missing fields and the user's cost cap stay unchanged.
      const request = naiMetadata.request;
      providerSelect.value = "novelai";
      naiOperation.value = request.operation || "generate";
      renderNovelAIOptions();
      setSelectValue(form.elements.nai_model, naiMetadataModel.value);
      for (const [key, value] of Object.entries(request)) {
        if (["provider", "nai_model", "nai_characters", "nai_use_coords", "nai_use_order"].includes(key)) continue;
        const input = form.elements[key];
        if (!input) continue;
        if (input.type === "checkbox") input.checked = value;
        else if (input.tagName === "SELECT") setSelectValue(input, value);
        else input.value = value;
      }
      setNaiCharacters(request.nai_character_slots || request.nai_characters || [], request.nai_character_count);
      setNaiReferences([], []);
      setNaiDetailer(request.nai_detailer || {});
      naiUseCoords.checked = request.nai_use_coords ?? true;
      naiUseOrder.checked = request.nai_use_order ?? true;
      syncStartingPointSelectionFromInputs();
      syncProviderControls();
      if (request.operation && request.operation !== "generate") resetNaiEditor();
      window.AppI18n.setText(naiMetadataStatus, () => tr("NAI 생성 조건을 적용했습니다. 전송 설정을 확인하고 생성하기를 누르세요."));
      form.elements.prompt.focus();
    }
    function setupSingleFileDropZone(zone, input, onFile, onError, uploadOnChange = true) {
      const run = (files) => {
        if (!files || files.length !== 1) {
          onError(new Error(tr("파일은 한 번에 한 개만 선택해 주세요.")));
          return;
        }
        Promise.resolve(onFile(files[0])).catch(onError);
      };
      if (uploadOnChange) {
        input.addEventListener("change", () => run(input.files));
      }
      zone.addEventListener("dragover", (event) => {
        event.preventDefault();
        zone.dataset.dragging = "true";
      });
      zone.addEventListener("dragleave", () => delete zone.dataset.dragging);
      zone.addEventListener("drop", (event) => {
        event.preventDefault();
        delete zone.dataset.dragging;
        run(event.dataTransfer?.files);
      });
    }
    async function loadReadiness() {
      const checkpoint = checkpointSelect.value || animaDefaults.checkpoint;
      const requestRevision = ++readinessRequestRevision;
      let response;
      try {
        response = await fetch(`/api/readiness?checkpoint=${encodeURIComponent(checkpoint)}`, {cache: "no-store"});
      } catch (error) {
        if (requestRevision !== readinessRequestRevision || checkpoint !== checkpointSelect.value) {
          return null;
        }
        throw error;
      }
      if (requestRevision !== readinessRequestRevision || checkpoint !== checkpointSelect.value) {
        return null;
      }
      const payload = await response.json();
      if (requestRevision !== readinessRequestRevision || checkpoint !== checkpointSelect.value) {
        return null;
      }
      if (!response.ok) {
        throw new Error(payload.error || tr("모델 준비 상태 확인 실패"));
      }
      renderReadiness(payload);
      return payload;
    }
    async function loadHistoryStorage() {
      const response = await fetch("/api/health", {cache: "no-store"});
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || tr("저장공간 확인 실패"));
      }
      renderHistoryStorage(payload.outputs);
      return payload.outputs;
    }
    async function loadStatus() {
      const [healthResponse, loraResponse, checkpointResponse, versionResponse, providersResponse, naiResponse] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/loras"),
        fetch("/api/checkpoints"),
        fetch("/api/version"),
        fetch("/api/providers"),
        fetch("/api/nai/status")
      ]);
      const health = await healthResponse.json();
      renderHistoryStorage(health.outputs);
      const loras = await loraResponse.json();
      const checkpoints = await checkpointResponse.json();
      const version = await versionResponse.json();
      if (!providersResponse.ok || !naiResponse.ok) {
        throw new Error(tr("생성 엔진 상태 확인 실패"));
      }
      providerCapabilities = await providersResponse.json();
      naiTokenConfigured = Boolean((await naiResponse.json()).configured);
      renderNovelAIOptions();
      const selectedCheckpoint = checkpointSelect.value;
      renderCheckpointOptions(checkpoints, selectedCheckpoint);
      loraCatalog = loras.items || [];
      if (!loraList.querySelector(".lora-row")) {
        addLoraRow();
      }
      [...loraList.querySelectorAll(".lora-path")].forEach((select) => {
        renderLoraSelectOptions(select, select.value);
      });
      const readiness = await loadReadiness();
      const readinessGeneration = readiness?.generation || generationReadiness;
      statusPanel.replaceChildren(
        statusCard(tr("현재 모델"), readinessGeneration?.ready ? tr("실행 가능") : tr("준비 필요")),
        statusCard(tr("체크포인트"), tr`${checkpoints.count}개 로컬`),
        statusCard("LoRA", tr`${loras.count}개 사용 가능`),
        statusCard(tr("출력"), health.outputs.image_root)
      );
      renderUpdateStatus(version);
      syncProviderControls();
      window.dispatchEvent(new Event("generation-ready"));
    }
    window.addEventListener('anima-setup-changed', () => {
      loadStatus().catch(error => setResultPayload({error: String(error)}));
    });
    function historyType(item) {
      return item.output_url ? "images" : "dry-run";
    }
    function historyTypeLabel(item) {
      return item.output_url ? tr("이미지") : tr("드라이런");
    }
    function historyThumbnailPlaceholder(label = tr("생성 정보")) {
      const placeholder = document.createElement("div");
      placeholder.className = "history-thumb history-thumb-empty";
      window.AppI18n.setText(placeholder, () => label);
      return placeholder;
    }
    function historyCard(item) {
      const card = document.createElement("article");
      card.className = `history-item history-item-${historyType(item)}`;
      const manifestName = item.manifest_name;
      if (item.thumbnail_url) {
        const image = document.createElement("img");
        image.className = "history-thumb";
        window.AppI18n.setProperty(image, "alt", () => "");
        image.loading = "lazy";
        image.decoding = "async";
        image.addEventListener("error", () => {
          image.replaceWith(historyThumbnailPlaceholder(tr("미리보기 없음")));
        }, {once: true});
        image.src = item.thumbnail_url;
        card.append(image);
      } else {
        card.append(historyThumbnailPlaceholder());
      }
      const body = document.createElement("div");
      body.className = "history-card-body";
      const title = document.createElement("strong");
      window.AppI18n.setText(title, () => item.prompt || tr("(빈 프롬프트)"));
      const type = document.createElement("span");
      type.className = "history-type";
      window.AppI18n.setText(type, () => historyTypeLabel(item));
      const meta = document.createElement("span");
      const outputSummary = item.output_url ? formatByteSize(item.output_size_bytes) : tr("이미지 없음");
      window.AppI18n.setText(meta, () => `${statusLabel(item.status || "unknown")} / ${outputSummary}`);
      body.append(title, type, meta);
      card.append(body);
      const actions = document.createElement("div");
      actions.className = "history-actions";
      actions.addEventListener("click", (event) => event.stopPropagation());
      const manifestButton = document.createElement("button");
      manifestButton.type = "button";
      manifestButton.className = "history-action";
      window.AppI18n.setText(manifestButton, () => tr("상세"));
      window.AppI18n.setProperty(manifestButton, "title", () => tr("생성 정보 보기"));
      manifestButton.addEventListener("click", () => openManifest(manifestName));
      actions.append(manifestButton);
      if (item.output_url) {
        const openOutput = document.createElement("a");
        openOutput.className = "history-action";
        openOutput.href = item.output_url;
        openOutput.target = "_blank";
        openOutput.rel = "noopener";
        window.AppI18n.setText(openOutput, () => tr("열기"));
        window.AppI18n.setProperty(openOutput, "title", () => tr("출력 이미지 열기"));
        actions.append(openOutput);
      }
      const exportButton = document.createElement("button");
      exportButton.type = "button";
      exportButton.className = "history-action";
      window.AppI18n.setText(exportButton, () => tr("내보내기"));
      window.AppI18n.setProperty(exportButton, "title", () => tr("생성 정보 JSON 다운로드"));
      exportButton.addEventListener("click", () => exportManifest(manifestName));
      actions.append(exportButton);
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "history-action danger";
      window.AppI18n.setText(deleteButton, () => tr("삭제"));
      window.AppI18n.setProperty(deleteButton, "title", () => tr("생성 정보와 관리 출력 이미지 삭제"));
      deleteButton.addEventListener("click", () => deleteHistoryItem(manifestName));
      actions.append(deleteButton);
      card.append(actions);
      card.addEventListener("click", () => openManifest(manifestName, {showCompare: false}));
      return card;
    }
    function renderHistory() {
      historyFilters.forEach((button) => {
        const active = button.dataset.historyFilter === historyFilter;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      window.AppI18n.setText(historyCount, () => historyLoading
        ? (historyItems.length ? tr`${historyItems.length.toLocaleString(window.AppI18n.locale)} / ${historyTotalCount.toLocaleString(window.AppI18n.locale)} 표시 · 불러오는 중` : tr("히스토리 불러오는 중"))
        : tr`${historyItems.length.toLocaleString(window.AppI18n.locale)} / ${historyTotalCount.toLocaleString(window.AppI18n.locale)} 표시${historyHasMore ? tr(" · 더 있음") : ""}`);
      if (!historyItems.length) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        window.AppI18n.setText(empty, () => historyLoading
          ? tr("히스토리를 불러오는 중입니다.")
          : (historySearchInput?.value.trim() ? tr("검색 조건에 맞는 히스토리가 없습니다.") : tr("아직 표시할 히스토리가 없습니다.")));
        history.replaceChildren(empty);
        return;
      }
      history.replaceChildren(...historyItems.map(historyCard));
    }
    async function loadHistory({append = false} = {}) {
      if (append && !historyNextCursor) {
        return;
      }
      const requestRevision = ++historyRequestRevision;
      if (!append) {
        historyItems = [];
        historyNextCursor = "";
        historyHasMore = false;
        historyTotalCount = 0;
        historyLoadMore.hidden = true;
      }
      historyLoading = true;
      renderHistory();
      const query = new URLSearchParams({limit: "8"});
      const rawQuery = (historySearchInput?.value || "").trim();
      query.set("q", historySearchInput ? rawQuery.slice(0, historySearchInput.maxLength) : rawQuery);
      query.set("type", historyFilter);
      if (append) {
        query.set("cursor", historyNextCursor);
      }
      historyLoadMore.disabled = true;
      try {
        const response = await fetch(`/api/history?${query.toString()}`, {cache: "no-store"});
        const payload = await response.json();
        if (requestRevision !== historyRequestRevision) {
          return;
        }
        if (!response.ok) {
          throw new Error(payload.error || tr("히스토리 불러오기 실패"));
        }
        const items = payload.items || [];
        historyItems = append ? [...historyItems, ...items] : items;
        const totalCount = Number(payload.total_count);
        historyTotalCount = Number.isFinite(totalCount) ? Math.max(0, totalCount) : historyItems.length;
        historyNextCursor = payload.next_cursor || "";
        historyHasMore = Boolean(payload.has_more && historyNextCursor);
        historyLoadMore.hidden = !historyHasMore;
      } catch (error) {
        if (requestRevision === historyRequestRevision) {
          throw error;
        }
      } finally {
        if (requestRevision === historyRequestRevision) {
          historyLoading = false;
          historyLoadMore.disabled = false;
          renderHistory();
        }
      }
    }
    function scheduleHistorySearch() {
      window.clearTimeout(historySearchTimer);
      historyRequestRevision += 1;
      historyItems = [];
      historyNextCursor = "";
      historyHasMore = false;
      historyTotalCount = 0;
      historyLoading = true;
      historyLoadMore.hidden = true;
      historyLoadMore.disabled = true;
      renderHistory();
      historySearchTimer = window.setTimeout(() => {
        loadHistory().catch((error) => setResultPayload({error: String(error)}));
      }, 250);
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
      window.animaAuthoring?.showResult(payload);
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
      if (!window.confirm(tr`${name} 생성 기록과 연결된 출력 이미지를 삭제할까요?`)) {
        return;
      }
      const response = await fetch("/api/manifests/" + encodeURIComponent(name), {method: "DELETE"});
      const payload = await response.json();
      const currentName = currentManifest?.manifest_name;
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
    function setPresetStatus(message) {
      if (presetStatus.textContent !== message) {
        window.AppI18n.setText(presetStatus, () => message);
      }
    }
    function syncPresetSelectionControls() {
      applyPresetButton.disabled = !presetSelect.value;
    }
    async function loadPresets() {
      const selectedSlug = presetSelect.value;
      const response = await fetch("/api/presets");
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || tr("저장된 설정 불러오기 실패"));
      }
      presets = payload.items || [];
      presetSelect.replaceChildren(
        new Option(presets.length ? tr("프리셋 선택") : tr("저장된 프리셋 없음"), ""),
        ...presets.map((item) => new Option(item.name, item.slug))
      );
      if (presets.some((item) => item.slug === selectedSlug)) {
        presetSelect.value = selectedSlug;
      }
      syncPresetSelectionControls();
      setPresetStatus(
        payload.invalid_count
          ? tr`설정 ${presets.length}개 불러옴 · 손상 파일 ${payload.invalid_count}개 제외`
          : tr`설정 ${presets.length}개 불러옴`
      );
    }
    async function exportPresets() {
      const response = await fetch("/api/presets/export");
      const payload = await response.json();
      if (!response.ok || payload.error) {
        setResultPayload(payload);
        setPresetStatus(tr`내보내기 실패: ${payload.error || tr("알 수 없는 오류")}`);
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
      setPresetStatus(tr`설정 ${payload.count}개 내보냄`);
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
        if (!response.ok || payload.error) {
          setPresetStatus(tr`가져오기 실패: ${payload.error || payload.errors?.[0]?.error || tr("알 수 없는 오류")}`);
          return;
        }
        await loadPresets();
        setPresetStatus(tr`설정 ${payload.imported_count}개 가져옴`);
      } catch (error) {
        setResultPayload(error.payload || {error: String(error)});
        setPresetStatus(tr`가져오기 실패: ${String(error)}`);
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
        new Option(items.length ? tr("와일드카드 선택") : tr("와일드카드 파일 없음"), ""),
        ...items.map((item) => new Option(`${item.name} (${item.value_count})`, item.token))
      );
      presetWildcardSelect.replaceChildren(
        new Option(presets.length ? tr("프리셋 선택") : tr("프롬프트 프리셋 없음"), ""),
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
      const afterCursor = input.value.slice(cursor);
      const delimiterOffset = afterCursor.search(/[,\n]/);
      const end = delimiterOffset < 0 ? input.value.length : cursor + delimiterOffset;
      return {start, end, query};
    }
    function setAutocompleteExpanded(input, expanded) {
      if (input?.tagName === "INPUT") {
        input.setAttribute("aria-expanded", String(expanded));
      }
    }
    function hideAutocomplete() {
      autocompleteRequestRevision += 1;
      window.clearTimeout(autocompleteTimer);
      if (autocompleteActiveInput) {
        setAutocompleteExpanded(autocompleteActiveInput, false);
        autocompleteActiveInput.removeAttribute("aria-activedescendant");
      }
      autocompleteMenu.hidden = true;
      autocompleteMenu.replaceChildren();
      window.AppI18n.setText(autocompleteStatus, () => "");
      autocompleteItems = [];
      autocompleteIndex = -1;
      autocompleteFragment = null;
      autocompleteActiveInput = null;
    }
    function positionAutocomplete(input) {
      const rect = input.getBoundingClientRect();
      autocompleteMenu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - 432))}px`;
      autocompleteMenu.style.top = `${Math.min(rect.bottom + 4, window.innerHeight - 272)}px`;
    }
    function setAutocompleteIndex(index) {
      autocompleteIndex = index;
      let activeId = "";
      let activeButton = null;
      [...autocompleteMenu.querySelectorAll(".autocomplete-item")].forEach((button, buttonIndex) => {
        const active = buttonIndex === autocompleteIndex;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
        if (active) {
          activeId = button.id;
          activeButton = button;
        }
      });
      if (autocompleteActiveInput && activeId) {
        autocompleteActiveInput.setAttribute("aria-activedescendant", activeId);
      }
      activeButton?.scrollIntoView({block: "nearest"});
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
        button.id = `autocomplete-option-${index}`;
        button.setAttribute("role", "option");
        button.tabIndex = -1;
        const label = document.createElement("span");
        window.AppI18n.setText(label, () => item.value);
        const count = document.createElement("span");
        count.className = "autocomplete-item-count";
        window.AppI18n.setText(count, () => item.count ? item.count.toLocaleString(window.AppI18n.locale) : "");
        button.append(label, count);
        button.addEventListener("mousedown", (event) => event.preventDefault());
        button.addEventListener("click", () => applyAutocompleteItem(index));
        autocompleteMenu.append(button);
      });
      autocompleteActiveInput = input;
      setAutocompleteExpanded(input, true);
      autocompleteMenu.hidden = false;
      window.AppI18n.setText(autocompleteStatus, () => tr`자동완성 제안 ${autocompleteItems.length}개. 위아래 화살표로 선택하세요.`);
      positionAutocomplete(input);
      setAutocompleteIndex(0);
    }
    async function requestAutocomplete(input, requestRevision) {
      if (requestRevision !== autocompleteRequestRevision) {
        return;
      }
      const fragment = currentAutocompleteFragment(input);
      if (!fragment) {
        hideAutocomplete();
        return;
      }
      try {
        const response = await fetch(`/api/autocomplete?q=${encodeURIComponent(fragment.query)}&limit=24`);
        const payload = await response.json();
        if (requestRevision !== autocompleteRequestRevision || autocompleteActiveInput !== input) {
          return;
        }
        autocompleteFragment = fragment;
        renderAutocomplete(input, payload.items || []);
      } catch (error) {
        if (requestRevision === autocompleteRequestRevision && autocompleteActiveInput === input) {
          hideAutocomplete();
        }
      }
    }
    function scheduleAutocomplete(input) {
      hideAutocomplete();
      autocompleteActiveInput = input;
      const requestRevision = ++autocompleteRequestRevision;
      autocompleteTimer = window.setTimeout(() => requestAutocomplete(input, requestRevision), 90);
    }
    function autocompleteReplacement(value, itemValue, fragment) {
      const before = value.slice(0, fragment.start);
      const after = value.slice(fragment.end);
      const delimiter = after.match(/^(?:,[ \t]*|\n[ \t]*)/);
      const separator = delimiter
        ? (delimiter[0].startsWith(",") ? ", " : delimiter[0])
        : ", ";
      const remainder = delimiter ? after.slice(delimiter[0].length) : after;
      return {
        value: before + itemValue + separator + remainder,
        cursor: before.length + itemValue.length + separator.length
      };
    }
    function autocompleteFragmentMatches(current, requested) {
      return Boolean(
        current
        && requested
        && current.start === requested.start
        && current.end === requested.end
        && current.query === requested.query
      );
    }
    function applyAutocompleteItem(index = autocompleteIndex) {
      const input = autocompleteActiveInput;
      const item = autocompleteItems[index];
      const fragment = input ? currentAutocompleteFragment(input) : null;
      if (!input || !item || !autocompleteFragmentMatches(fragment, autocompleteFragment)) {
        hideAutocomplete();
        return;
      }
      const replacement = autocompleteReplacement(input.value, item.value, fragment);
      input.value = replacement.value;
      input.focus();
      input.setSelectionRange(replacement.cursor, replacement.cursor);
      hideAutocomplete();
      input.dispatchEvent(new Event("input", {bubbles: true}));
    }
    function handleAutocompleteKeydown(event) {
      if (event.isComposing || event.keyCode === 229) {
        return;
      }
      if (autocompleteMenu.hidden) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setAutocompleteIndex((autocompleteIndex + 1) % autocompleteItems.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setAutocompleteIndex((autocompleteIndex - 1 + autocompleteItems.length) % autocompleteItems.length);
      } else if (event.key === "Enter") {
        event.preventDefault();
        applyAutocompleteItem();
      } else if (event.key === "Tab") {
        hideAutocomplete();
      } else if (event.key === "Escape") {
        event.preventDefault();
        hideAutocomplete();
      }
    }
    function setupAutocomplete() {
      autocompleteTargets().forEach((input) => {
        if (input.tagName === "INPUT") {
          input.setAttribute("role", "combobox");
        }
        input.setAttribute("aria-controls", autocompleteMenu.id);
        input.setAttribute("aria-autocomplete", "list");
        setAutocompleteExpanded(input, false);
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
        lines.push(tr`오류: ${payload.error}`);
      }
      lines.push(tr("프롬프트:"));
      lines.push(payload.prompt || "");
      if (payload.negative_prompt) {
        lines.push("");
        lines.push(tr("네거티브:"));
        lines.push(payload.negative_prompt);
      }
      lines.push("");
      lines.push(tr`선택: ${payload.selection_count || 0}`);
      (payload.selections || []).forEach((item, index) => {
        const label = item.wildcard || item.type || tr("항목");
        const value = item.expanded_value || item.value || "";
        lines.push(`${index + 1}. ${label}: ${value}`);
      });
      window.AppI18n.setText(wildcardPreview, () => lines.join("\n"));
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
        window.AppI18n.setText(llmPromptStatus, () => tr("프롬프트가 비어 있음"));
        return;
      }
      const refinePriority = llmRefinePrioritySelect.value === "natural" ? "natural" : "tag";
      const refinePriorityLabel = refinePriority === "natural" ? "natural-language priority" : "tag priority";
      const previousText = llmRefinePromptButton.textContent;
      llmRefinePromptButton.disabled = true;
      window.AppI18n.setText(llmRefinePromptButton, () => tr("LLM 처리 중..."));
      window.AppI18n.setText(llmPromptStatus, () => tr("LLM 보정 중..."));
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
        window.AppI18n.setText(llmPromptStatus, () => refined.resolvedConflicts.length
          ? tr`LLM 보정 완료 (${refined.resolvedConflicts.length}개 정리)`
          : tr("LLM 보정 완료"));
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
        window.AppI18n.setText(llmPromptStatus, () => tr("LLM 보정 실패"));
        setResultPayload(error.payload || {error: String(error)});
      } finally {
        window.AppI18n.setText(llmRefinePromptButton, () => previousText);
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
    function seedNumberFromElement(input) {
      const value = input.value.trim();
      input.setCustomValidity("");
      if (!value) {
        return null;
      }
      if (!/^\d+$/.test(value)) {
        input.setCustomValidity(tr("시드는 0 이상의 10진 정수여야 합니다."));
        return null;
      }
      const normalized = value.replace(/^0+(?=\d)/, "");
      const maximum = String(input === form.elements.seed && providerSelect.value === "novelai"
        ? 4294967295 : animaDefaults.limits.max_seed_safe);
      if (normalized.length > maximum.length || (normalized.length === maximum.length && normalized > maximum)) {
        input.setCustomValidity(tr`웹 시드는 ${maximum} 이하여야 합니다.`);
        return null;
      }
      return Number(normalized);
    }
    function seedNumberFromInput() {
      return seedNumberFromElement(form.elements.seed);
    }
    function syncGenerationResourceValidity() {
      window.dispatchEvent(new Event("generation-settings-applied"));
      syncCharacterControls();
      const widthInput = form.elements.width;
      const heightInput = form.elements.height;
      const upscaleScaleInput = form.elements.upscale_scale;
      const width = Number(widthInput.value);
      const height = Number(heightInput.value);
      const scale = Number(upscaleScaleInput.value);
      heightInput.setCustomValidity("");
      upscaleScaleInput.setCustomValidity("");
      seedNumberFromInput();

      if (providerSelect.value === "novelai") {
        naiOperation.setCustomValidity("");
        if (["infill", "focused_infill"].includes(naiOperation.value)) {
          if (!form.elements.input_image.value || !form.elements.mask_image.value) {
            naiOperation.setCustomValidity(tr("입력 이미지와 마스크를 지정하고, 그린 마스크는 저장해 주세요."));
          } else if (form.elements.nai_limit_opus_free.checked && naiOperation.value === "infill") {
            naiOperation.setCustomValidity(tr("인페인트는 비용이 발생할 수 있습니다. Opus 요청 한도를 직접 해제해 주세요."));
          }
        }
        if (naiOperation.value === "img2img") {
          if (!form.elements.input_image.value) naiOperation.setCustomValidity(tr("Img2Img 입력 이미지를 지정해 주세요."));
          else if (form.elements.nai_limit_opus_free.checked) naiOperation.setCustomValidity(tr("Img2Img는 비용이 발생할 수 있습니다. Opus 보호 모드를 직접 해제해 주세요."));
        }
        if (naiOperation.value === "detail" && !form.elements.input_image.value) naiOperation.setCustomValidity(tr("디테일러 입력 이미지를 지정해 주세요."));
        if (!form.elements.nai_limit_opus_free.checked && width * height > animaDefaults.limits.max_base_image_pixels) {
          heightInput.setCustomValidity(tr`한도 미적용 시 ${animaDefaults.limits.max_base_image_pixels.toLocaleString(window.AppI18n.locale)}픽셀 이하여야 합니다.`);
        }
        renderNovelAIEffective();
        const vibes = readNaiReferences("vibe"), references = readNaiReferences("precise");
        const model = form.elements.nai_model.value;
        if (vibes.length || references.length) {
          if (form.elements.nai_limit_opus_free.checked) naiOperation.setCustomValidity(tr("참조는 비용이 발생할 수 있습니다. Opus 보호 모드를 직접 해제해 주세요."));
          else if (vibes.length && references.length) naiOperation.setCustomValidity(tr("Vibe와 Precise Reference는 함께 사용할 수 없습니다."));
          else if (vibes.length && (!/^nai-diffusion-(3|furry-3|4)/.test(model) || ["infill", "focused_infill", "detail"].includes(naiOperation.value) && model.startsWith("nai-diffusion-4"))) naiOperation.setCustomValidity(tr("이 모델 / 생성 방식은 Vibe를 지원하지 않습니다."));
          else if (references.length && !model.startsWith("nai-diffusion-4-5")) naiOperation.setCustomValidity(tr("Precise Reference는 V4.5 모델을 선택해 주세요."));
          else if ([...vibes, ...references].some((r) => !r.image)) naiOperation.setCustomValidity(tr("참조 이미지를 업로드해 주세요."));
        }
        return;
      }

      if (width > 0 && height > 0 && width * height > animaDefaults.limits.max_base_image_pixels) {
        heightInput.setCustomValidity(tr`기본 이미지는 ${animaDefaults.limits.max_base_image_pixels.toLocaleString(window.AppI18n.locale)}픽셀 이하여야 합니다.`);
      }
      if (form.elements.upscale_enabled.checked && width > 0 && height > 0 && scale > 0) {
        const outputWidth = 8 * Math.round((width / 8) * scale);
        const outputHeight = 8 * Math.round((height / 8) * scale);
        const outputPixels = outputWidth * outputHeight;
        if (outputPixels > animaDefaults.limits.max_output_image_pixels) {
          upscaleScaleInput.setCustomValidity(tr`업스케일 결과는 ${animaDefaults.limits.max_output_image_pixels.toLocaleString(window.AppI18n.locale)}픽셀 이하여야 합니다.`);
        }
      }

      [
        [form.elements.upscale_tile_size, form.elements.upscale_overlap],
        [form.elements.vae_tile_size, form.elements.vae_overlap]
      ].forEach(([tileInput, overlapInput]) => {
        const tileSize = Number(tileInput.value);
        if (Number.isFinite(tileSize) && tileSize > 0) {
          overlapInput.max = String(Math.floor(tileSize / 4));
        } else {
          overlapInput.removeAttribute("max");
        }
      });
    }
    function generationFormIsValid({report = false} = {}) {
      syncGenerationResourceValidity();
      if (!(report ? form.reportValidity() : form.checkValidity())) return false;
      if (providerSelect.value === "novelai") {
        if (!naiCharacterCount.checkValidity()) {
          if (report) { document.getElementById("nai-characters-panel").open = true; naiCharacterCount.reportValidity(); }
          return false;
        }
        for (const input of naiCharacters.querySelectorAll("input, textarea")) {
          if (!input.checkValidity()) {
            if (report) { document.getElementById("nai-characters-panel").open = true; input.closest(".nai-character").querySelector("details").open = true; input.reportValidity(); }
            return false;
          }
        }
      }
      return true;
    }
    window.animaGenerationRequest = () => buildRequestData(false);
    window.addEventListener('anima-barracks-finished', () => loadHistory().catch(() => {}));
    window.animaGenerationDraft = () => {
      const request = buildRequestData(false, false);
      const steps = window.animaWorkflow?.snapshot() || [];
      return steps.length ? {...request, workflow: {version: 1, steps}} : request;
    };
    window.animaRestoreGeneration = request => applyPreset({name: tr("작업 초안"), request});
    function buildRequestData(includeWorkflow = true, validate = true) {
      if (validate && !generationFormIsValid()) {
        throw new Error(tr("생성 설정 값을 확인해 주세요."));
      }
      const data = Object.fromEntries(new FormData(form).entries());
      data.width = Number(data.width);
      data.height = Number(data.height);
      data.steps = Number(data.steps);
      data.cfg = Number(data.cfg);
      if (providerSelect.value === "novelai") {
        const request = {
          provider: "novelai", prompt: data.prompt, negative_prompt: data.negative_prompt,
          width: data.width, height: data.height, steps: data.steps, cfg: data.cfg,
          wildcard_mode: data.wildcard_mode, nai_model: data.nai_model,
          nai_sampler: data.nai_sampler, nai_scheduler: data.nai_scheduler,
          nai_cfg_rescale: Number(data.nai_cfg_rescale || 0),
          nai_prefer_brownian: form.elements.nai_prefer_brownian.checked,
          nai_variety_boost: form.elements.nai_variety_boost.checked,
          nai_limit_opus_free: form.elements.nai_limit_opus_free.checked,
          operation: naiOperation.value,
          input_image: naiOperation.value !== "generate" ? form.elements.input_image.value : "",
          mask_image: ["infill", "focused_infill"].includes(naiOperation.value) ? form.elements.mask_image.value : "",
          inpaint_strength: Number(form.elements.inpaint_strength.value),
          img2img_strength: Number(form.elements.img2img_strength.value),
          img2img_noise: Number(form.elements.img2img_noise.value)
        };
        for (const input of naiCharacters.querySelectorAll("input, textarea")) {
          if (validate && !input.checkValidity()) {
            document.getElementById("nai-characters-panel").open = true;
            input.reportValidity(); throw new Error(tr("캐릭터 프롬프트와 좌표를 확인해 주세요."));
          }
        }
        request.nai_characters = readNaiCharacters();
        request.nai_character_slots = readNaiCharacterSlots();
        request.nai_character_count = Number(naiCharacterCount.value);
        for (const input of document.querySelectorAll("#nai-reference-panel input, #nai-detailer-panel input")) {
          if (validate && !input.checkValidity()) { input.closest("details").open = true; input.reportValidity(); throw new Error(tr("참조 / 디테일러 설정 범위를 확인해 주세요.")); }
        }
        request.nai_use_coords = naiUseCoords.checked;
        request.nai_use_order = naiUseOrder.checked;
        request.nai_vibes = readNaiReferences("vibe");
        request.nai_references = readNaiReferences("precise");
        request.nai_normalize_vibe_strengths = document.getElementById("nai-normalize-vibes").checked;
        request.nai_detailer = readNaiDetailer();
        const seed = seedNumberFromInput();
        if (seed !== null) request.seed = seed;
        Object.assign(request, window.animaAuthoring?.context());
        return includeWorkflow && window.animaWorkflow ? window.animaWorkflow.decorate(request) : request;
      }
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
        data.seed = seedNumberFromInput();
      }
      Object.assign(data, window.animaAuthoring?.context());
      return includeWorkflow && window.animaWorkflow ? window.animaWorkflow.decorate(data) : data;
    }
    function renderNovelAIOptions() {
      const capability = providerCapabilities?.providers.find((item) => item.id === "novelai");
      if (!capability) return;
      const isInfill = ["infill", "focused_infill"].includes(naiOperation.value);
      const models = isInfill ? capability.inpaint_models : capability.models;
      [["nai_model", models], ["nai_sampler", capability.samplers], ["nai_scheduler", capability.schedulers]].forEach(([name, values]) => {
        const select = form.elements[name];
        const selected = select.value || capability.defaults[name];
        select.replaceChildren(...values.map((value) => new Option(value, value)));
        const routing = capability.inpaint_routing || {};
        const paired = name === "nai_model" && isInfill
          ? routing[selected] : Object.keys(routing).find((base) => routing[base] === selected);
        select.value = values.includes(selected) ? selected : values.includes(paired) ? paired : values[0];
      });
    }
    function readNaiDetailer() {
      const settings = {enabled: document.getElementById("nai-detailer-enabled").checked || naiOperation.value === "detail",
        preview_only: document.getElementById("nai-detailer-preview").checked,
        concepts: [...document.querySelectorAll(".nai-detailer-concept:checked")].map((input) => input.value)};
      for (const key of ["mode", "matching", "backend", "wd_device", "wd_model"]) settings[key] = document.getElementById(`nai-detailer-${key}`).value;
      for (const key of ["threshold", "mask_threshold", "crop_factor", "padding", "dilation", "strength", "steps", "max_regions", "match_min_score", "match_min_margin", "match_crop_factor", "wd_batch_size"]) {
        settings[key] = Number(document.getElementById(`nai-detailer-${key}`).value);
      }
      return settings;
    }
    function setNaiDetailer(value = {}) {
      const defaults = {enabled: false, preview_only: false, mode: "all", matching: "shared", backend: "sam_b",
        threshold: .5, mask_threshold: .3, crop_factor: 2, padding: 32, dilation: 0, strength: .55, steps: 28,
        max_regions: 16, match_min_score: .25, match_min_margin: .08, match_crop_factor: 2, wd_device: "auto", wd_batch_size: 4,
        wd_model: "WD ViT v3"};
      for (const [key, initial] of Object.entries(defaults)) {
        const input = document.getElementById(`nai-detailer-${key === "preview_only" ? "preview" : key}`);
        if (input.type === "checkbox") input.checked = value[key] ?? initial;
        else input.value = value[key] ?? initial;
      }
      for (const input of document.querySelectorAll(".nai-detailer-concept")) input.checked = (value.concepts || ["face", "eyes"]).includes(input.value);
    }
    function syncTaggerControls() {
      const busy = taggerJob?.status === "running" || taggerSubmitting;
      const disabled = providerSelect.value !== "novelai" || queueRunning || !uploadsAreIdle();
      naiBind(document.getElementById("nai-tagger-hint"), document.getElementById("nai-detailer-wd_model").value === "PixAI Tagger v1.0" ? "taggerPixAI" : "taggerWD");
      for (const key of ["wd_model", "wd_device", "wd_batch_size"]) {
        document.getElementById(`nai-detailer-${key}`).disabled = disabled || busy;
      }
      document.getElementById("nai-tagger-prepare").disabled = disabled || busy;
      document.getElementById("nai-tagger-cancel").disabled = taggerSubmitting || taggerJob?.status !== "running" || taggerJob?.cancel_requested;
    }
    function renderTaggerJob(data) {
      taggerJob = data.job;
      window.NaiErrors.render("nai-tagger-error-guide", taggerJob);
      const progress = document.getElementById("nai-tagger-progress");
      progress.hidden = !taggerJob;
      if (taggerJob) {
        if (taggerJob.status === "running" && !taggerJob.total_bytes) progress.removeAttribute("value");
        else progress.value = taggerJob.fraction;
        const status = {running: tr("준비 중"), ready: tr("준비 완료"), cancelled: tr("취소됨"), failed: tr("실패")}[taggerJob.status] || taggerJob.status;
        window.AppI18n.setText(document.getElementById("nai-tagger-status"), () => `${taggerJob.model_name} — ${status}: ${taggerJob.text}`
          + (taggerJob.error ? ` — ${window.NaiErrors.message(taggerJob)}` : ""));
      }
      syncTaggerControls();
      window.clearTimeout(taggerPollTimer);
      if (taggerJob?.status === "running") taggerPollTimer = window.setTimeout(refreshTagger, 500);
    }
    async function refreshTagger() {
      try {
        const response = await fetch("/api/nai/tagger", {cache: "no-store"});
        if (!response.ok) throw new Error(tr("태거 준비 상태를 확인할 수 없습니다."));
        renderTaggerJob(await response.json());
      } catch (error) {
        window.AppI18n.setText(document.getElementById("nai-tagger-status"), () => String(error));
        window.clearTimeout(taggerPollTimer);
        taggerPollTimer = window.setTimeout(refreshTagger, 2000);
      }
    }
    async function controlTagger(action) {
      window.NaiErrors.render("nai-tagger-error-guide", null);
      taggerSubmitting = true;
      syncTaggerControls();
      try {
        const settings = readNaiDetailer();
        const payload = action === "prepare" ? {model_name: settings.wd_model, device: settings.wd_device, batch_size: settings.wd_batch_size}
          : {job_id: taggerJob?.id};
        const response = await fetch(`/api/nai/tagger/${action}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
        const data = await response.json();
        if (!response.ok) throw window.NaiErrors.asError(data, tr("태거 준비 실패"));
        renderTaggerJob(data);
      } catch (error) {
        window.NaiErrors.render("nai-tagger-error-guide", error.payload);
        window.AppI18n.setText(document.getElementById("nai-tagger-status"), () => String(error));
      }
      finally { taggerSubmitting = false; syncTaggerControls(); }
    }
    function readNaiReferences(kind) {
      const container = document.getElementById(kind === "vibe" ? "nai-vibes" : "nai-references");
      return [...container.children].map((row) => ({image: row.dataset.image || "",
        strength: Number(row.querySelector(".reference-strength").value),
        ...(kind === "vibe" ? {information_extracted: Number(row.querySelector(".reference-information_extracted").value)}
          : {reference_type: row.querySelector(".reference-type").value, fidelity: Number(row.querySelector(".reference-fidelity").value)})}));
    }
    function addNaiReference(kind, value = {}) {
      const container = document.getElementById(kind === "vibe" ? "nai-vibes" : "nai-references");
      if (container.children.length >= 16 || queueRunning || !uploadsAreIdle()) return;
      const row = document.createElement("fieldset");
      row.dataset.image = value.image || "";
      const legend = document.createElement("legend"); window.AppI18n.setText(legend, () => kind === "vibe" ? "Vibe" : "Precise Reference"); row.append(legend);
      const path = document.createElement("p"); path.className = "reference-path";
      if (value.image) window.AppI18n.setText(path, () => value.image);
      else naiBind(path, "uploadReference");
      row.append(path);
      const file = document.createElement("input"); file.type = "file"; file.accept = "image/png,image/webp,image/jpeg";
      file.addEventListener("change", async () => {
        if (!file.files[0] || queueRunning || !uploadsAreIdle()) return;
        setUploadActive(true);
        try {
          const uploaded = await uploadFile("/api/inputs/reference", file.files[0], "reference");
          row.dataset.image = uploaded.relative_path;
          delete path.dataset.naiI18n; delete path.dataset.naiI18nParams;
          window.AppI18n.setText(path, () => uploaded.relative_path);
        } catch (error) { window.AppI18n.setText(document.getElementById("nai-reference-status"), () => String(error)); }
        finally { file.value = ""; setUploadActive(false); syncGenerationResourceValidity(); }
      }); row.append(file);
      for (const [key, label, initial] of [["strength", "strength", kind === "vibe" ? .6 : 1],
        [kind === "vibe" ? "information_extracted" : "fidelity", kind === "vibe" ? "information" : "fidelity", 1]]) {
        const wrapper = document.createElement("label"); wrapper.append(naiBind(document.createElement("span"), label));
        const input = document.createElement("input"); input.type = "number"; input.min = "0"; input.max = "1"; input.step = "any"; input.required = true;
        input.className = `reference-${key}`; input.value = value[key] ?? initial;
        wrapper.append(input); row.append(wrapper);
      }
      if (kind === "precise") {
        const select = document.createElement("select"); select.className = "reference-type";
        for (const [type, key] of [["character", "referenceCharacter"], ["style", "referenceStyle"], ["character&style", "referenceBoth"]]) select.add(naiBind(new Option("", type), key));
        select.value = value.reference_type || "character";
        const wrapper = document.createElement("label");
        wrapper.append(naiBind(document.createElement("span"), "referenceType"), select); row.append(wrapper);
      }
      const remove = document.createElement("button"); remove.type = "button"; naiBind(remove, "referenceRemove");
      remove.addEventListener("click", () => { if (!queueRunning && uploadsAreIdle()) { row.remove(); syncGenerationResourceValidity(); } }); row.append(remove);
      container.append(row); syncGenerationResourceValidity();
    }
    function setNaiReferences(vibes, references) {
      document.getElementById("nai-vibes").replaceChildren(); document.getElementById("nai-references").replaceChildren();
      vibes.forEach((value) => addNaiReference("vibe", value)); references.forEach((value) => addNaiReference("precise", value));
    }
    document.getElementById("nai-add-vibe").addEventListener("click", () => addNaiReference("vibe"));
    document.getElementById("nai-add-reference").addEventListener("click", () => addNaiReference("precise"));
    function readNaiCharacterSlots() {
      return [...naiCharacters.children].map((row) => ({
        prompt: row.querySelector(".character-prompt").value,
        negative_prompt: row.querySelector(".character-negative").value,
        x: Number(row.querySelector(".character-x").value), y: Number(row.querySelector(".character-y").value),
        enabled: row.querySelector(".character-enabled").checked, collapsed: !row.querySelector("details").open
      }));
    }
    function readNaiCharacters() {
      return readNaiCharacterSlots().slice(0, Number(naiCharacterCount.value))
        .filter((s) => s.enabled).map(({enabled, collapsed, ...character}) => character);
    }
    function syncCharacterControls(updateControls = true) {
      const count = Number(naiCharacterCount.value), active = readNaiCharacters().length;
      const model = form.elements.nai_model.value;
      const limits = providerCapabilities?.providers.find((p) => p.id === "novelai")?.characters?.model_limits || {};
      const limit = limits[model] ?? (model.startsWith("nai-diffusion-5") ? 22 : model.startsWith("nai-diffusion-4") ? 6 : 0);
      naiCharacterCount.setCustomValidity(Number.isInteger(count) && count >= 0 && count <= naiCharacters.children.length ? "" : naiText("characterCountInvalid"));
      const message = active > limit ? naiText("characterOverflow", {limit, active}) : "";
      form.elements.nai_model.setCustomValidity(providerSelect.value === "novelai" ? message : "");
      naiBind(document.getElementById("nai-character-status"), "characterStatus", {model: model || naiText("modelSelect"), active, limit,
        stored: naiCharacters.children.length, hidden: Math.max(0, naiCharacters.children.length - count), warning: message ? ` · ${message}` : ""});
      if (!updateControls) return;
      [...naiCharacters.children].forEach((row, index) => {
        row.hidden = index >= count;
        for (const input of row.querySelectorAll("input, textarea")) {
          input.disabled = providerSelect.value !== "novelai" || row.hidden || (input.className !== "character-enabled" && !row.querySelector(".character-enabled").checked);
        }
      });
      naiAddCharacter.disabled = providerSelect.value !== "novelai" || count >= 22;
    }
    function refreshConvertFields(invalidate = true) {
      const selected = convertField.value;
      convertField.replaceChildren(new Option(naiText("commonPrompt"), "prompt"), new Option(naiText("commonNegative"), "negative_prompt"));
      [...naiCharacters.children].forEach((row, index) => {
        if (row.hidden || !row.querySelector(".character-enabled").checked) return;
        for (const kind of ["prompt", "negative"]) {
          convertField.add(new Option(naiText("characterField", {number: index + 1, field: naiText(kind)}), `character:${index}:${kind}`));
        }
      });
      if ([...convertField.options].some((item) => item.value === selected)) convertField.value = selected;
      if (invalidate) invalidateConversion();
    }
    function addNaiCharacter(value = {}) {
      if (naiCharacters.children.length >= 22) return;
      const row = document.createElement("fieldset");
      row.className = "nai-character";
      const legend = document.createElement("legend");
      window.AppI18n.setText(legend, () => tr("캐릭터"));
      row.append(legend);
      const enabledLabel = document.createElement("label"), enabled = document.createElement("input");
      enabled.type = "checkbox"; enabled.className = "character-enabled"; enabled.checked = value.enabled ?? true;
      enabledLabel.append(enabled, naiBind(document.createElement("span"), "characterEnabled")); row.append(enabledLabel);
      enabled.addEventListener("change", refreshCharacterRows);
      const body = document.createElement("details"), summary = document.createElement("summary");
      body.open = !(value.collapsed ?? false); naiBind(summary, "characterFold");
      body.append(summary); row.append(body);
      for (const [key, label] of [["prompt", "prompt"], ["negative", "negative"], ["x", "X"], ["y", "Y"]]) {
        const wrapper = document.createElement("label");
        wrapper.append(naiBind(document.createElement("span"), label));
        const input = document.createElement(key === "prompt" || key === "negative" ? "textarea" : "input");
        input.className = `character-${key}`;
        if (input.tagName === "TEXTAREA") {
          input.maxLength = form.elements.prompt.maxLength;
          input.value = value[key === "negative" ? "negative_prompt" : key] ?? "";
          input.rows = 2;
        } else {
          input.type = "number"; input.min = "0"; input.max = "1"; input.step = "any"; input.required = true;
          input.value = value[key] ?? 0.5;
        }
        input.addEventListener("input", invalidateConversion);
        wrapper.append(input); body.append(wrapper);
      }
      const remove = document.createElement("button");
      remove.type = "button"; naiBind(remove, "characterRemove"); remove.className = "secondary-button";
      remove.addEventListener("click", () => {
        const index = [...naiCharacters.children].indexOf(row);
        if (index < Number(naiCharacterCount.value)) naiCharacterCount.value = Number(naiCharacterCount.value) - 1;
        row.remove(); refreshCharacterRows();
      });
      row.append(remove); naiCharacters.append(row); naiCharacterCount.value = naiCharacters.children.length; refreshCharacterRows();
    }
    function refreshCharacterRows() {
      [...naiCharacters.children].forEach((row, index) => { naiBind(row.querySelector("legend"), "character", {number: index + 1}); });
      syncCharacterControls();
      refreshConvertFields();
    }
    function setNaiCharacters(values, count = values.length) {
      if (values.length > 22) throw new Error(tr("캐릭터 슬롯 22개를 초과한 설정은 가져올 수 없습니다."));
      naiCharacters.replaceChildren();
      values.forEach(addNaiCharacter);
      naiCharacterCount.value = count;
      refreshCharacterRows();
    }
    naiCharacterCount.addEventListener("input", () => {
      const count = Number(naiCharacterCount.value);
      if (Number.isInteger(count) && count >= 0 && count <= 22) {
        while (naiCharacters.children.length < count) addNaiCharacter();
        naiCharacterCount.value = count;
      }
      refreshCharacterRows();
    });
    function conversionInput() {
      if (!convertField.value.startsWith("character:")) return form.elements[convertField.value];
      const [, index, kind] = convertField.value.split(":");
      return naiCharacters.children[Number(index)]?.querySelector(`.character-${kind}`);
    }
    function invalidateConversion() {
      window.NaiErrors.render("nai-convert-error-guide", null);
      conversionRevision += 1; conversion = null; convertApply.disabled = true;
      window.AppI18n.setText(document.getElementById("convert-status"), () => "");
      window.AppI18n.setText(document.getElementById("convert-result"), () => "");
    }
    document.getElementById("convert-preview").addEventListener("click", async () => {
      invalidateConversion();
      const revision = conversionRevision, input = conversionInput();
      const source = document.getElementById("convert-source").value;
      const target = document.getElementById("convert-target").value;
      const original = input?.value ?? "";
      try {
        const response = await fetch("/api/prompts/convert", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({source, target, text: original})});
        const result = await response.json();
        if (revision !== conversionRevision) return;
        if (!response.ok) throw window.NaiErrors.asError(result);
        window.AppI18n.setText(document.getElementById("convert-result"), () => tr`원문\n${original}\n\n변환 결과\n${result.converted}`);
        window.AppI18n.setText(document.getElementById("convert-status"), () => result.warnings.join("\n") || tr("변환 결과를 확인한 뒤 적용하세요."));
        conversion = {input, original, converted: result.converted}; convertApply.disabled = false;
      } catch (error) {
        if (revision === conversionRevision) {
          window.AppI18n.setText(document.getElementById("convert-status"), () => String(error));
          window.NaiErrors.render("nai-convert-error-guide", error.payload);
        }
      }
    });
    convertApply.addEventListener("click", () => {
      if (!conversion || !conversion.input.isConnected || conversion.input !== conversionInput() || conversion.input.value !== conversion.original) {
        invalidateConversion(); return;
      }
      const {input, converted} = conversion;
      input.value = converted; input.dispatchEvent(new Event("input", {bubbles: true})); invalidateConversion();
      window.AppI18n.setText(document.getElementById("convert-status"), () => tr("선택한 프롬프트에 적용했습니다."));
    });
    for (const id of ["convert-field", "convert-source", "convert-target"]) document.getElementById(id).addEventListener("change", invalidateConversion);
    form.elements.prompt.addEventListener("input", invalidateConversion);
    form.elements.negative_prompt.addEventListener("input", invalidateConversion);
    naiAddCharacter.addEventListener("click", () => {
      const count = Number(naiCharacterCount.value);
      if (count < naiCharacters.children.length) { naiCharacterCount.value = count + 1; refreshCharacterRows(); }
      else addNaiCharacter();
    });
    function renderNovelAIEffective() {
      let width = Number(form.elements.width.value), height = Number(form.elements.height.value);
      let steps = Number(form.elements.steps.value);
      const medium = ["nai-diffusion-5-full-medium", "nai-diffusion-5-full-medium-inpainting"].includes(form.elements.nai_model.value);
      const mediumNotice = document.getElementById("nai-medium-notice");
      mediumNotice.hidden = !medium;
      window.AppI18n.setText(mediumNotice, () => medium ? naiText("medium") : "");
      const routingNotice = document.getElementById("nai-routing-notice");
      const curatedInfill = ["infill", "focused_infill"].includes(naiOperation.value)
        && form.elements.nai_model.value === "nai-diffusion-4-5-curated-inpainting";
      const curatedDetail = form.elements.nai_model.value === "nai-diffusion-5-curated"
        && (naiOperation.value === "detail" || document.getElementById("nai-detailer-enabled").checked);
      routingNotice.hidden = !curatedInfill && !curatedDetail;
      window.AppI18n.setText(routingNotice, () => routingNotice.hidden ? "" : naiText("routing"));
      if (medium) steps = 14;
      const capped = form.elements.nai_limit_opus_free.checked;
      if (naiOperation.value !== "generate") {
        const label = naiText(`op_${naiOperation.value}`);
        const focused = ["detail", "focused_infill"].includes(naiOperation.value);
        const preview = focused && document.getElementById("nai-detailer-preview").checked;
        const model = naiOperation.value === "detail" ? providerCapabilities?.providers.find((p) => p.id === "novelai")?.inpaint_routing[form.elements.nai_model.value] : form.elements.nai_model.value;
        window.AppI18n.setText(naiEffective, () => naiText("effectiveEdit", {operation: label, model: model || naiText("modelCheck"), width, height,
          medium: medium ? naiText("mediumSteps") : "", cost: preview ? naiText("previewFree") : capped
            ? focused ? naiText("cropCheck", {steps: medium ? 14 : 28}) : naiText("blockedOpus") : naiText("mayCost")}));
        return;
      }
      if (capped && width * height > 1048576) {
        const scale = Math.sqrt(1048576 / (width * height));
        width = Math.max(64, Math.floor(width * scale / 64) * 64);
        height = Math.max(64, Math.floor(height * scale / 64) * 64);
      }
      if (capped) steps = Math.min(steps, 28);
      window.AppI18n.setText(naiEffective, () => naiText("effectiveGenerate", {width, height, steps, cost: naiText(capped ? "opusLimit" : "accountCost")}));
    }
    function renderNaiProviderStatus() {
      window.AppI18n.setText(providerStatus, () => providerSelect.value === "novelai"
        ? naiText(providerCapabilities?.default_dry_run ? "providerDry" : naiTokenConfigured ? "providerReady" : "providerToken")
        : tr("로컬 Anima"));
      providerStatus.lang = window.AppI18n.language;
    }
    function syncProviderControls() {
      const isNovelAI = providerSelect.value === "novelai";
      novelAISettings.hidden = !isNovelAI;
      novelAISettings.querySelectorAll("input, select, textarea").forEach((input) => { input.disabled = !isNovelAI; });
      syncCharacterControls();
      naiInpaintInputs.hidden = !isNovelAI || naiOperation.value === "generate";
      document.getElementById("nai-img2img-options").hidden = naiOperation.value !== "img2img";
      document.getElementById("nai-mask-controls").hidden = !["infill", "focused_infill"].includes(naiOperation.value);
      naiBind(document.getElementById("nai-input-help"), naiOperation.value === "img2img" ? "inputImg2img" : naiOperation.value === "detail" ? "inputDetail" : "inputInfill");
      naiInpaintInputs.querySelectorAll("input, select, button").forEach((input) => { input.disabled = naiInpaintInputs.hidden; });
      [document.getElementById("local-model-settings"), loraImportForm,
       document.getElementById("local-sampling-controls"), document.getElementById("local-memory-controls"),
       document.querySelector('[data-control-group="enhance"]')].forEach((section) => {
        section.hidden = isNovelAI;
        section.querySelectorAll("input, select, textarea, button").forEach((input) => { input.disabled = isNovelAI; });
      });
      for (const name of ["width", "height"]) {
        form.elements[name].step = isNovelAI ? "64" : "8";
        form.elements[name].min = isNovelAI ? "64" : "8";
      }
      form.elements.steps.max = isNovelAI ? "50" : "100";
      form.elements.seed.max = isNovelAI ? "4294967295" : String(animaDefaults.limits.max_seed_safe);
      renderNaiProviderStatus();
      sam3Tools.hidden = isNovelAI || !currentOutputUrl || currentManifest?.provider === "novelai";
      if (!isNovelAI) syncLoraRemoveButtons();
      syncGenerationResourceValidity();
      syncGenerationControls();
    }
    function syncSam3DetailerControls() {
      sam3DetailerControls.hidden = form.elements.face_mask_backend.value !== "sam3";
    }
    function applyPreset(item) {
      if (loraUploadInFlight) {
        setResultMessage(tr("LoRA 업로드가 끝난 뒤 설정을 불러와 주세요."));
        return false;
      }
      const request = item.request?.workflow_base_request || item.request?.authoring_request || item.request || {};
      window.animaAuthoring?.apply(request);
      window.animaWorkflow?.apply(request.workflow);
      providerSelect.value = request.provider || "local";
      const naiSettings = request.novelai?.effective || request;
      setNaiDetailer(naiSettings.nai_detailer || naiSettings.detailer || {});
      setNaiReferences(naiSettings.nai_vibes || naiSettings.vibes || [], naiSettings.nai_references || naiSettings.references || []);
      document.getElementById("nai-normalize-vibes").checked = naiSettings.nai_normalize_vibe_strengths ?? naiSettings.normalize_vibe_strengths ?? true;
      naiOperation.value = naiSettings.operation || "generate";
      renderNovelAIOptions();
      form.elements.input_image.value = naiSettings.input_image || "";
      form.elements.mask_image.value = naiSettings.mask_image || "";
      form.elements.inpaint_strength.value = naiSettings.inpaint_strength ?? 1;
      form.elements.img2img_strength.value = naiSettings.img2img_strength ?? 0.5;
      form.elements.img2img_noise.value = naiSettings.img2img_noise ?? 0;
      resetNaiEditor();
      for (const name of ["model", "sampler", "scheduler"]) {
        setSelectValue(form.elements[`nai_${name}`], naiSettings[`nai_${name}`] || (request.provider === "novelai" ? request[name] : "") ||
          {model: "nai-diffusion-5-curated", sampler: "k_euler", scheduler: "karras"}[name]);
      }
      form.elements.nai_cfg_rescale.value = naiSettings.nai_cfg_rescale ?? request.cfg_rescale ?? 0;
      form.elements.nai_prefer_brownian.checked = naiSettings.nai_prefer_brownian ?? request.prefer_brownian ?? false;
      form.elements.nai_variety_boost.checked = naiSettings.nai_variety_boost ?? request.variety_boost ?? true;
      form.elements.nai_limit_opus_free.checked = naiSettings.nai_limit_opus_free ?? request.limit_opus_free ?? true;
      const originalCharacters = request.wildcards?.characters?.map((item) => item.original);
      const savedSlots = request.novelai?.requested?.nai_character_slots || naiSettings.nai_character_slots || request.character_slots;
      if (savedSlots && originalCharacters) {
        let active = 0;
        const count = naiSettings.nai_character_count ?? request.character_count ?? savedSlots.length;
        setNaiCharacters(savedSlots.map((s, i) => i < count && s.enabled ? {...s, ...originalCharacters[active++]} : s), count);
      } else {
        setNaiCharacters(savedSlots || originalCharacters || naiSettings.nai_characters || request.characters || [],
          naiSettings.nai_character_count ?? request.character_count);
      }
      naiUseCoords.checked = naiSettings.nai_use_coords ?? request.use_coords ?? true;
      naiUseOrder.checked = naiSettings.nai_use_order ?? request.use_order ?? true;
      const wildcardInfo = request.wildcards || {};
      form.elements.prompt.value = wildcardInfo.original_prompt || request.prompt || "";
      form.elements.negative_prompt.value = wildcardInfo.original_negative_prompt || request.negative_prompt || "";
      form.elements.width.value = request.width || animaDefaults.width;
      form.elements.height.value = request.height || animaDefaults.height;
      form.elements.steps.value = request.steps || animaDefaults.steps;
      form.elements.cfg.value = request.cfg ?? animaDefaults.cfg;
      form.elements.sampler.value = request.sampler || animaDefaults.sampler;
      form.elements.scheduler.value = request.scheduler || animaDefaults.scheduler;
      form.elements.seed.value = request.seed ?? "";
      form.elements.memory_profile.value = request.memory_profile || "auto";
      setSelectValue(checkpointSelect, request.checkpoint || animaDefaults.checkpoint);
      const wildcardMode = request.wildcard_mode || wildcardInfo.mode || "random";
      form.elements.wildcard_mode.value = wildcardMode === "off" ? "random" : wildcardMode;
      cancelPendingReferenceUpload();
      setManagedReferencePath(request.i2i?.image_path || "");
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
      syncProviderControls();
      presetName.value = item.name || "";
      syncStartingPointSelectionFromInputs();
      syncGenerationResourceValidity();
      loadReadiness().catch((error) => setResultPayload({error: String(error)}));
      window.dispatchEvent(new Event("authoring-changed"));
      return true;
    }
    function syncStartingPointSelectionFromInputs() {
      const width = Number(form.elements.width.value || 0);
      const height = Number(form.elements.height.value || 0);
      if (width > 0 && height > 0 && width !== height) {
        startingOrientation = width > height ? "landscape" : "portrait";
      }
      const matchingSize = Object.entries(startingSizePresets).find(([, preset]) => (
        (width === preset.width && height === preset.height)
        || (width === preset.height && height === preset.width)
      ));
      selectedStartingSize = matchingSize?.[0] || "";
      syncStartingPointButtons();
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
      syncGenerationResourceValidity();
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
      syncGenerationResourceValidity();
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
      syncGenerationResourceValidity();
    }
    function syncStartingPointButtons() {
      startingSizeButtons.forEach((button) => {
        const selected = button.dataset.sizePreset === selectedStartingSize;
        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-pressed", String(selected));
      });
      orientationButtons.forEach((button) => {
        const selected = button.dataset.orientation === startingOrientation;
        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-pressed", String(selected));
      });
    }
    window.animaLibraryReadDraft = () => ({
      prompt: form.elements.prompt.value, negative_prompt: form.elements.negative_prompt.value,
      ...window.animaAuthoring?.context(),
    });
    window.animaLibraryApply = (request, mode) => {
      if (queueRunning || !uploadsAreIdle()) throw new Error(tr("생성·업로드가 끝난 뒤 적용해 주세요."));
      if (mode === "all") {
        if (request.provider === "novelai" && !(request.nai_model || request.model || request.novelai?.effective?.nai_model)) {
          throw new Error(tr("기록에서 모델을 확인할 수 없습니다. 프롬프트만 적용하고 모델을 직접 선택해 주세요."));
        }
        const cap = form.elements.nai_limit_opus_free.checked;
        applyPreset({name: tr("라이브러리"), request});
        form.elements.nai_limit_opus_free.checked = cap;
      } else if (mode === "artists") {
        form.elements.prompt.value = [form.elements.prompt.value.trim(), request.prompt].filter(Boolean).join(", ");
      } else {
        form.elements.prompt.value = request.prompt || "";
        if (mode === "prompt") form.elements.negative_prompt.value = request.negative_prompt || "";
      }
      window.animaAuthoring?.apply(request);
      window.dispatchEvent(new Event("authoring-changed"));
      form.elements.prompt.focus();
      form.elements.prompt.scrollIntoView({block: "center"});
      syncProviderControls();
      setResultMessage(tr("라이브러리 내용을 적용했습니다. 생성 조건을 확인해 주세요."));
    };
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
      return total === null ? tr("무한") : String(total);
    }
    function queueDelaySeconds() {
      const value = Number(queueDelayInput.value || 0);
      return Math.max(0, Math.min(60, Number.isFinite(value) ? value : 0));
    }
    function setQueueStatus(message) {
      if (queueStatus.textContent !== message) {
        window.AppI18n.setText(queueStatus, () => message);
      }
    }
    function setQueueControlsRunning(running) {
      queueRunning = running;
      queueCountInput.disabled = running;
      queueInfiniteInput.disabled = running;
      queueSeedMode.disabled = running;
      queueDelayInput.disabled = running;
      stopQueueButton.disabled = !running;
      syncGenerationControls();
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
      return !items.some((item) => ["queued", "waiting", "running"].includes(item.status));
    }
    function renderServerQueueStatus(payload) {
      const items = jobsForActiveBatch(payload);
      const summary = queueSummaryForJobs(items);
      const active = items.find((item) => item.status === "running") || items.find((item) => item.status === "waiting") || items.find((item) => item.status === "queued");
      const total = items.length;
      setQueueStatus(tr`등록 ${summary.queued}, 대기 ${summary.waiting}, 실행 ${summary.running}, 완료 ${summary.completed}, 실패 ${summary.failed}, 취소 ${summary.cancelled}`);
      if (active?.request?.provider === "novelai" && active.cancel_requested) {
        setQueueStatus(tr("다음 작업 예약 중지 · 이미 전송한 NovelAI 응답을 기다립니다."));
      }
      if (active?.progress_id && active.status === "running" && active.progress_id !== activeProgressId) {
        startStageProgress(buildGenerationStages(active.request || {}));
        startProgressPolling(active.progress_id);
      }
      return {items, summary, total};
    }
    async function showLatestQueueResult(items) {
      const latest = [...items].reverse().find((item) => item.result && ["completed", "failed", "cancelled"].includes(item.status));
      if (!latest?.result) {
        return;
      }
      if (latest.id === lastQueueResultJobId) {
        return;
      }
      lastQueueResultJobId = latest.id;
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
        throw new Error(payload.error || tr("큐 상태 확인 실패"));
      }
      const rendered = renderServerQueueStatus(payload);
      await showLatestQueueResult(rendered.items);
      if (queueRunning && queueIsSettled(rendered.items)) {
        setQueueControlsRunning(false);
        stopServerQueuePolling();
        const failed = rendered.summary.failed;
        const cancelled = rendered.summary.cancelled;
        setQueueStatus(tr`큐 완료. 완료 ${rendered.summary.completed}, 실패 ${failed}, 취소 ${cancelled}.`);
        if (!activeProgressId) {
          const finalState = failed ? "failed" : (cancelled ? "cancelled" : "completed");
          const message = failed ? tr("하나 이상의 작업 실패") : (cancelled ? tr("작업이 취소되었습니다.") : "");
          finishGenerationStages({}, finalState, message);
        }
        activeQueueBatchId = "";
      }
    }
    function startServerQueuePolling() {
      stopServerQueuePolling();
      pollServerQueue().catch((error) => setQueueStatus(String(error)));
      serverQueuePollTimer = window.setInterval(() => {
        pollServerQueue().catch((error) => setQueueStatus(String(error)));
      }, 900);
    }
    async function restoreServerQueue() {
      const response = await fetch("/api/jobs", {cache: "no-store"});
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || tr("큐 상태 복구 실패"));
      }
      const activeItems = (payload.items || []).filter((item) => ["running", "waiting", "queued"].includes(item.status));
      const activeJob = activeItems.find((item) => item.status === "running")
        || activeItems.find((item) => item.status === "waiting")
        || activeItems[activeItems.length - 1];
      if (!activeJob) {
        return false;
      }
      activeQueueBatchId = activeJob.batch_id || "";
      lastQueueResultJobId = "";
      setQueueControlsRunning(true);
      setResultMessage(tr("진행 중인 서버 작업에 다시 연결했습니다."));
      startStageProgress(buildGenerationStages(activeJob.request || {}));
      renderServerQueueStatus(payload);
      startServerQueuePolling();
      return true;
    }
    async function enqueueServerJobs(
      baseData,
      total,
      infinite,
      seedMode = queueSeedMode.value,
      delaySeconds = queueDelaySeconds()
    ) {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          request: baseData,
          count: total || 1,
          infinite,
          seed_mode: seedMode,
          delay_seconds: delaySeconds
        })
      });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw window.NaiErrors.asError(payload, tr("큐 등록 실패"));
      }
      activeQueueBatchId = payload.batch_id || "";
      lastQueueResultJobId = "";
      return payload;
    }
    async function cancelServerJob(jobId) {
      const response = await fetch("/api/jobs/" + encodeURIComponent(jobId) + "/cancel", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}"
      });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || tr("작업 취소 실패"));
      }
      return payload;
    }
    async function startSingleGeneration() {
      if (queueRunning || !uploadsAreIdle({report: true})) {
        return;
      }
      const baseData = buildRequestData();
      setQueueControlsRunning(true);
      currentManifest = null;
      clearOutputPreview();
      setResultMessage(tr("생성 작업 등록 중..."));
      startStageProgress(buildGenerationStages(baseData));
      try {
        await enqueueServerJobs(baseData, 1, false, "fixed", 0);
        setQueueStatus(tr("단일 생성 실행 중"));
        startServerQueuePolling();
      } catch (error) {
        setQueueControlsRunning(false);
        finishGenerationStages({}, "failed", String(error));
        setResultPayload(error.payload || {error: String(error)});
        setQueueStatus(String(error));
      }
    }
    async function startAutoQueue() {
      if (queueRunning || !uploadsAreIdle({report: true})) {
        return;
      }
      if (!generationFormIsValid({report: true})) {
        return;
      }
      const infinite = queueIsInfinite();
      const total = infinite ? null : queueCount();
      const baseData = buildRequestData();
      setQueueControlsRunning(true);
      clearOutputPreview();
      setResultMessage(infinite ? tr("무한 큐 준비 중...") : tr`${total}개 작업 큐 등록 중...`);
      startStageProgress(buildGenerationStages(baseData));
      try {
        const queued = await enqueueServerJobs(baseData, total, infinite);
        setQueueStatus(infinite ? tr("서버 큐 실행 중: 무한 모드") : tr`서버 큐 ${queued.count} / ${queueTotalLabel(total)}개 등록됨`);
        startServerQueuePolling();
      } catch (error) {
        setQueueControlsRunning(false);
        finishGenerationStages({}, "failed", String(error));
        setResultPayload(error.payload || {error: String(error)});
        setQueueStatus(String(error));
      }
    }
    async function stopAutoQueue() {
      if (!queueRunning) {
        return;
      }
      stopQueueButton.disabled = true;
      setQueueStatus(tr("서버 큐 정지 중..."));
      try {
        const response = await fetch("/api/jobs", {cache: "no-store"});
        const payload = await response.json();
        if (!response.ok || payload.error) {
          throw new Error(payload.error || tr("큐 상태 확인 실패"));
        }
        const jobs = jobsForActiveBatch(payload).filter((item) => ["queued", "waiting", "running"].includes(item.status));
        await Promise.all(jobs.map((item) => cancelServerJob(item.id)));
        await pollServerQueue();
      } catch (error) {
        setQueueStatus(String(error));
        if (queueRunning) {
          stopQueueButton.disabled = false;
        }
      }
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (queueRunning) {
        return;
      }
      if (!generationFormIsValid({report: true})) {
        return;
      }
      await startSingleGeneration();
    });
    savePresetButton.addEventListener("click", async () => {
      if (!uploadsAreIdle({report: true}) || !generationFormIsValid({report: true})) {
        return;
      }
      const name = presetName.value || form.elements.prompt.value.slice(0, 48) || "preset";
      const response = await fetch("/api/presets", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name, request: buildRequestData()})
      });
      const payload = await response.json();
      if (!response.ok || payload.error) {
        setResultPayload(payload);
        setPresetStatus(tr`저장 실패: ${payload.error || tr("알 수 없는 오류")}`);
        return;
      }
      setResultPayload({status: "settings_saved", ...payload});
      await loadPresets();
      presetSelect.value = payload.slug || "";
      syncPresetSelectionControls();
      setPresetStatus(tr`${payload.name} 저장됨`);
    });
    applyPresetButton.addEventListener("click", () => {
      const item = presets.find((preset) => preset.slug === presetSelect.value);
      if (item && applyPreset(item)) {
        setPresetStatus(tr`${item.name} 불러옴`);
      }
    });
    checkpointSelect.addEventListener("change", () => {
      loadReadiness().catch((error) => setResultPayload({error: String(error)}));
    });
    exportPresetsButton.addEventListener("click", exportPresets);
    importPresetsButton.addEventListener("click", () => presetImportFile.click());
    presetImportFile.addEventListener("change", () => importPresetsFromFile(presetImportFile.files[0]));
    presetSelect.addEventListener("change", syncPresetSelectionControls);
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
    addLoraButton.addEventListener("click", () => addLoraRow({}, {focus: true}));
    ["width", "height"].forEach((name) => {
      form.elements[name].addEventListener("input", () => {
        syncStartingPointSelectionFromInputs();
        syncGenerationResourceValidity();
      });
    });
    ["seed", "upscale_scale", "upscale_tile_size", "vae_tile_size"].forEach((name) => {
      form.elements[name].addEventListener("input", syncGenerationResourceValidity);
    });
    form.elements.upscale_enabled.addEventListener("change", syncGenerationResourceValidity);
    syncGenerationResourceValidity();
    setupAutocomplete();
    startQueueButton.addEventListener("click", () => {
      startAutoQueue().catch((error) => {
        setQueueControlsRunning(false);
        setQueueStatus(tr`큐 실패: ${String(error)}`);
        setResultPayload(error.payload || {error: String(error)});
      });
    });
    stopQueueButton.addEventListener("click", stopAutoQueue);
    historyFilters.forEach((button) => {
      button.addEventListener("click", () => {
        const nextFilter = button.dataset.historyFilter || "all";
        if (nextFilter === historyFilter) {
          return;
        }
        window.clearTimeout(historySearchTimer);
        historyFilter = nextFilter;
        loadHistory().catch((error) => setResultPayload({error: String(error)}));
      });
    });
    historySearchForm?.addEventListener("submit", (event) => {
      event.preventDefault();
      window.clearTimeout(historySearchTimer);
      loadHistory().catch((error) => setResultPayload({error: String(error)}));
    });
    historySearchInput?.addEventListener("input", scheduleHistorySearch);
    historyLoadMore.addEventListener("click", () => {
      loadHistory({append: true}).catch((error) => setResultPayload({error: String(error)}));
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
      const file = loraFileInput.files?.[0];
      if (!file) {
        window.AppI18n.setText(loraUploadStatus, () => tr("LoRA 파일을 선택해 주세요."));
        loraFileInput.focus();
        return;
      }
      try {
        await uploadLoraFile(file);
      } catch (error) {
        window.AppI18n.setText(loraUploadStatus, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      }
    });
    setupSingleFileDropZone(
      naiMetadataDropZone, naiMetadataFile, readNaiMetadata,
      (error) => { window.AppI18n.setText(naiMetadataStatus, () => String(error)); window.NaiErrors.render("nai-metadata-error-guide", error.payload); }
    );
    naiMetadataModel.addEventListener("change", syncGenerationControls);
    applyNaiMetadataButton.addEventListener("click", applyNaiMetadata);
    setupSingleFileDropZone(
      referenceDropZone,
      referenceFileInput,
      uploadReferenceFile,
      (error) => {
        window.AppI18n.setText(referenceUploadStatus, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      }
    );
    setupSingleFileDropZone(
      loraDropZone,
      loraFileInput,
      async (file) => {
        try {
          await uploadLoraFile(file);
        } finally {
          loraFileInput.value = "";
        }
      },
      (error) => {
        window.AppI18n.setText(loraUploadStatus, () => String(error));
        setResultPayload(error.payload || {error: String(error)});
      },
      false
    );
    loraFileInput.addEventListener("change", () => {
      try {
        if (loraFileInput.files?.length !== 1) {
          throw new Error(tr("파일은 한 번에 한 개만 선택해 주세요."));
        }
        validateUploadFile(loraFileInput.files[0], "lora");
        window.AppI18n.setText(loraUploadStatus, () => tr`선택됨: ${loraFileInput.files[0].name}`);
      } catch (error) {
        loraFileInput.value = "";
        window.AppI18n.setText(loraUploadStatus, () => String(error));
      }
    });
    removeReferenceButton.addEventListener("click", () => {
      cancelPendingReferenceUpload();
      setManagedReferencePath("");
    });
    window.addEventListener("beforeunload", revokeReferencePreviewUrl);
    addLoraRow();
    providerSelect.addEventListener("change", syncProviderControls);
    document.getElementById("nai-tagger-prepare").addEventListener("click", () => controlTagger("prepare"));
    document.getElementById("nai-tagger-cancel").addEventListener("click", () => controlTagger("cancel"));
    document.getElementById("nai-detailer-wd_model").addEventListener("change", syncTaggerControls);
    refreshTagger();
    form.elements.nai_model.addEventListener("change", syncGenerationResourceValidity);
    naiOperation.addEventListener("change", () => { renderNovelAIOptions(); syncProviderControls(); });
    for (const id of ["nai-reference-panel", "nai-detailer-panel"]) {
      document.getElementById(id).addEventListener("input", () => { syncGenerationResourceValidity(); syncGenerationControls(); });
      document.getElementById(id).addEventListener("change", () => { syncGenerationResourceValidity(); syncGenerationControls(); });
    }
    const reportNaiInputError = (error) => { window.AppI18n.setText(naiInpaintStatus, () => String(error)); };
    document.getElementById("nai-input-file").addEventListener("change", (event) => {
      if (event.target.files.length === 1) uploadNaiInput(event.target.files[0]).catch(reportNaiInputError);
      event.target.value = "";
    });
    document.getElementById("nai-mask-file").addEventListener("change", (event) => {
      if (event.target.files.length === 1) uploadNaiInput(event.target.files[0], true).catch(reportNaiInputError);
      event.target.value = "";
    });
    document.getElementById("nai-use-result").addEventListener("click", async () => {
      if (queueRunning || !uploadsAreIdle() || !currentOutputUrl) return;
      try {
        const url = new URL(currentOutputUrl, location.href);
        if (url.origin !== location.origin || !/^\/outputs\/images\/[^/]+$/.test(url.pathname)) throw new Error(tr("관리된 결과 이미지만 사용할 수 있습니다."));
        resetNaiEditor();
        form.elements.input_image.value = "outputs/images/" + decodeURIComponent(url.pathname.split("/").pop());
        form.elements.mask_image.value = "";
        setUploadActive(true);
        await showNaiInput(url.href);
        window.AppI18n.setText(naiInpaintStatus, () => tr("현재 결과를 입력으로 지정했습니다. 마스크를 칠하고 저장하세요."));
      } catch (error) { form.elements.input_image.value = ""; reportNaiInputError(error); }
      finally { setUploadActive(false); syncGenerationResourceValidity(); syncGenerationControls(); }
    });
    document.getElementById("nai-mask-save").addEventListener("click", () => saveNaiMask().catch(reportNaiInputError));
    document.getElementById("nai-mask-clear").addEventListener("click", () => {
      if (queueRunning || !uploadsAreIdle() || !naiMaskBuffer.width) return;
      const context = naiMaskBuffer.getContext("2d");
      context.fillStyle = "black";
      context.fillRect(0, 0, naiMaskBuffer.width, naiMaskBuffer.height);
      form.elements.mask_image.value = "";
      redrawNaiMask();
      syncGenerationControls();
    });
    function paintNaiMask(event) {
      if (queueRunning || !uploadsAreIdle() || !naiMaskBuffer.width) return;
      const rect = naiMaskCanvas.getBoundingClientRect();
      const point = {x: (event.clientX - rect.left) * naiMaskBuffer.width / rect.width,
                     y: (event.clientY - rect.top) * naiMaskBuffer.height / rect.height};
      const context = naiMaskBuffer.getContext("2d");
      const size = Math.max(1, Math.min(512, Number(document.getElementById("nai-brush-size").value) || 48));
      context.fillStyle = context.strokeStyle = document.getElementById("nai-brush-mode").value === "erase" ? "black" : "white";
      context.lineWidth = size;
      context.lineCap = "round";
      context.beginPath();
      context.moveTo(naiMaskPointer?.x ?? point.x, naiMaskPointer?.y ?? point.y);
      context.lineTo(point.x, point.y);
      context.stroke();
      context.beginPath();
      context.arc(point.x, point.y, size / 2, 0, 2 * Math.PI);
      context.fill();
      naiMaskPointer = {...point, pointerId: event.pointerId};
      form.elements.mask_image.value = "";
      window.AppI18n.setText(naiInpaintStatus, () => tr("마스크를 수정했습니다. 그린 마스크 저장을 눌러주세요."));
      redrawNaiMask();
      syncGenerationControls();
    }
    naiMaskCanvas.addEventListener("pointerdown", (event) => {
      if (queueRunning || !uploadsAreIdle()) return;
      naiMaskPointer = null;
      naiMaskCanvas.setPointerCapture(event.pointerId);
      paintNaiMask(event);
    });
    naiMaskCanvas.addEventListener("pointermove", (event) => {
      if (naiMaskPointer?.pointerId === event.pointerId) paintNaiMask(event);
    });
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) naiMaskCanvas.addEventListener(type, () => { naiMaskPointer = null; });
    window.addEventListener("beforeunload", () => { if (naiInputObjectUrl) URL.revokeObjectURL(naiInputObjectUrl); });
    ["nai_limit_opus_free", "steps"].forEach((name) => {
      form.elements[name].addEventListener("input", syncGenerationResourceValidity);
    });
    window.addEventListener("nai-language-change", () => {
      // Refresh text without recreating input cards or clearing conversion previews.
      syncCharacterControls(false); refreshConvertFields(false);
      renderNovelAIEffective(); syncTaggerControls(); renderNaiProviderStatus();
      syncGenerationResourceValidity();
    });
    syncProviderControls();
    form.elements.face_mask_backend.addEventListener("change", syncSam3DetailerControls);
    syncSam3DetailerControls();
    renderSam3Presets();
    function reportStartupError(label, error) {
      setResultPayload({status: "startup_error", error: tr`${label} 불러오기 실패: ${String(error)}`});
    }
    loadStatus().catch((error) => reportStartupError(tr("상태"), error));
    loadHistory().catch((error) => reportStartupError(tr("기록"), error));
    loadPresets().catch((error) => reportStartupError(tr("설정"), error));
    loadWildcards().catch((error) => reportStartupError(tr("와일드카드"), error));
    restoreServerQueue().catch((error) => setQueueStatus(tr`큐 상태 복구 실패: ${String(error)}`));
    renderResultSummary();
