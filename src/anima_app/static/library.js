/* Image workspace: pixels -> cases -> recorded combinations -> an editable draft. */
(() => {
  const el = (tag, text = "", props = {}) => {
    const node = Object.assign(document.createElement(tag), props);
    window.AppI18n.setText(node, text);
    for (const name of ["ariaLabel", "placeholder", "alt", "title"]) {
      if (name in props) window.AppI18n.setProperty(node, name, props[name]);
    }
    return node;
  };
  document.head.append(el("style", () => `
    #library-dialog{box-sizing:border-box;width:100vw;max-width:100vw;height:100dvh;max-height:100dvh;margin:0;padding:0;border:0;background:#101722;color:#e6edf8;font:14px/1.5 system-ui,sans-serif}
    #library-dialog[open]{display:flex;flex-direction:column}#library-dialog::backdrop{background:#060b13e8}
    #library-dialog *{box-sizing:border-box;min-width:0}#library-dialog [hidden]{display:none!important}
    #library-dialog h2,#library-dialog h3,#library-dialog p{margin:0 0 10px}#library-dialog h2{font-size:19px}#library-dialog h3{font-size:15px}
    #library-dialog button,#library-dialog input,#library-dialog select,#library-dialog textarea{font:inherit;border:1px solid #46556c;border-radius:8px;background:#202c3e;color:#e6edf8;padding:9px 12px;max-width:100%;margin:0;box-shadow:none}
    #library-dialog button{cursor:pointer;width:auto;min-height:42px}#library-dialog button:hover{border-color:#9fbde8;background:#2b3a51}
    #library-dialog button:disabled{cursor:default;opacity:.45}#library-dialog :focus-visible{outline:3px solid #a1c6ff;outline-offset:2px}
    #library-dialog button[aria-pressed=true],#library-dialog .lib-primary{border-color:#8bb6f6;background:#304d76;color:#fff}
    #library-dialog input:not([type=checkbox]),#library-dialog select,#library-dialog textarea{width:100%}#library-dialog input[type=checkbox]{width:18px;height:18px;accent-color:#a0c5ff}
    #library-dialog textarea{min-height:110px;resize:vertical}#library-dialog label{display:block;margin:8px 0 4px}#library-dialog summary{cursor:pointer;padding:10px 0;color:#c1d0e7}
    #library-dialog a{color:#a9c9ff}#library-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto}
    #library-dialog .lib-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}#library-dialog .lib-muted{font-size:12px;color:#aabbd2;overflow-wrap:anywhere}
    #library-dialog .lib-header{padding:14px 22px;border-bottom:1px solid #334157;display:flex;align-items:center;gap:24px;flex-wrap:wrap;background:#182233}
    #library-dialog .lib-header h2{margin:0}#library-dialog .lib-header nav{display:flex;gap:6px;flex:1}#library-dialog .lib-header p{margin:0}
    #library-dialog .lib-layout{display:grid;grid-template-columns:220px minmax(0,1fr) 340px;flex:1;min-height:0;overflow:hidden}
    #library-dialog .lib-reference,#library-dialog .lib-detail{padding:18px;overflow:auto;background:#151f2e;scrollbar-width:thin}
    #library-dialog .lib-reference{border-right:1px solid #334157}#library-dialog .lib-detail{border-left:1px solid #334157;overflow-wrap:anywhere}
    #library-dialog .lib-main{min-height:0;display:flex;flex-direction:column;padding:18px 22px;overflow:hidden}
    #library-dialog .lib-stage{overflow:auto;flex:1;min-height:0;scrollbar-width:thin;padding:3px}
    #library-dialog .lib-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}#library-dialog .lib-toolbar input[type=search]{flex:1;min-width:140px}
    #library-dialog .lib-toolbar label{display:flex;align-items:center;gap:6px;margin:0;font-size:12px}#library-dialog .lib-toolbar select{width:auto}
    #library-dialog .lib-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,var(--lib-card-width,210px)),1fr));gap:14px}
    #library-dialog .lib-card{border:1px solid #34445c;border-radius:12px;overflow:hidden;background:#1b2738;position:relative}
    #library-dialog .lib-card.is-selected{border-color:#99c0ff;box-shadow:0 0 0 1px #99c0ff}
    #library-dialog .lib-select{width:100%;display:block;text-align:left;padding:0;border:0;border-radius:0;background:transparent}
    #library-dialog .lib-select img{display:block;width:100%;height:var(--lib-image-height,260px);object-fit:contain;background:#0c121d}
    #library-dialog .lib-card-title{display:block;margin:10px 12px 3px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #library-dialog .lib-card-meta{display:block;padding:0 12px 6px;font-size:11px;color:#aabbd2}
    #library-dialog .lib-card label{display:flex;gap:7px;align-items:center;font-size:12px;margin:0;padding:4px 12px 10px;color:#b7c9e0}
    #library-dialog .lib-image-button{display:block;width:100%;padding:0;border:0;background:#0c121d;overflow:hidden}
    #library-dialog .lib-image-button img{display:block;width:100%;height:230px;object-fit:contain}#library-dialog .lib-detail .lib-image-button img{height:270px}
    #library-dialog .lib-drop{border:1px dashed #577298;border-radius:10px;padding:12px;margin-top:12px}#library-dialog .lib-drop input{font-size:11px;padding:4px}
    #library-dialog .lib-placeholder{display:grid;place-items:center;min-height:160px;border:1px dashed #425674;border-radius:10px;color:#9bb1ce;text-align:center;padding:20px}
    #library-dialog .lib-header select{width:auto;max-width:130px;padding:7px}
    #library-dialog .lib-count{margin:8px 0 12px;color:#b4c7e3;font-size:12px}#library-dialog .lib-combos{margin-bottom:12px}#library-dialog .lib-combos button{font-size:12px;max-width:100%;text-align:left;overflow-wrap:anywhere}
    #library-dialog .lib-record{border-top:1px solid #334157;margin-top:14px;padding-top:14px}#library-dialog .lib-artist{color:#c8dcff;white-space:pre-wrap;overflow-wrap:anywhere}
    #library-dialog .lib-pair{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:12px 0}#library-dialog .lib-pair figure{margin:0;overflow:hidden}
    #library-dialog .lib-pair img{height:clamp(240px,48vh,580px)}#library-dialog .lib-pair figcaption{padding:8px 0;color:#b9cde8}
    #library-dialog .lib-votes button{flex:1}#library-dialog .lib-votes{margin:14px 0}#library-dialog .lib-compose textarea{min-height:250px}
    #library-dialog .lib-compose textarea.lib-negative{min-height:95px}#library-dialog .lib-compose label{margin-top:18px}
    #library-dialog .lib-footer{border-top:1px solid #334157;background:#182233;padding:9px 22px;display:flex;gap:18px;align-items:center;font-size:12px;min-height:44px}
    #library-dialog #library-message{flex:1;margin:0;white-space:pre-wrap}#library-dialog .lib-queue{max-width:35%;color:#b6c6da}
    #library-zoom{padding:12px;border:1px solid #637c9f;border-radius:12px;background:#111a28;color:#eef3fa;width:min(96vw,1800px);max-width:96vw;max-height:96dvh}
    #library-zoom::backdrop{background:#000d}#library-zoom img{display:block;max-width:100%;height:80dvh;object-fit:contain;margin:auto}
    @media(min-width:1700px){#library-dialog .lib-layout{grid-template-columns:250px minmax(0,1fr) 370px}}
    @media(max-width:1200px){#library-dialog .lib-layout{grid-template-columns:185px minmax(0,1fr) 285px}#library-dialog .lib-main{padding:14px}#library-dialog .lib-reference,#library-dialog .lib-detail{padding:12px}}
    @media(max-width:900px){#library-dialog .lib-header{padding:10px 12px;gap:8px}#library-dialog .lib-header nav{order:3;flex-basis:100%}#library-dialog .lib-header nav button{flex:1}#library-dialog .lib-header>button{margin-left:auto}#library-dialog .lib-header .lib-muted{display:none}
      #library-dialog .lib-layout{display:block;overflow:auto}#library-dialog .lib-main{overflow:visible;display:block;padding:12px}#library-dialog .lib-stage{overflow:visible}
      #library-dialog .lib-reference{position:sticky;top:0;z-index:2;display:grid;grid-template-columns:100px minmax(0,1fr);gap:0 12px;border:0;border-bottom:1px solid #40536f;padding:10px 12px;max-height:40dvh;overflow:auto}
      #library-dialog .lib-reference>h3{display:none}#library-dialog .lib-ref-media{grid-row:1 / span 2}#library-dialog .lib-reference .lib-image-button img{height:94px}
      #library-dialog .lib-reference .lib-placeholder{min-height:94px;padding:8px;font-size:11px}#library-dialog .lib-reference .lib-drop{margin:0;padding:4px 8px;font-size:11px}
      #library-dialog .lib-reference details{grid-column:1/-1}#library-dialog .lib-reference .lib-ref-name{margin:4px 0;font-size:11px}#library-dialog .lib-reference .lib-ref-hint{display:none}
      #library-dialog .lib-detail{border:0;border-top:1px solid #40536f;padding:16px}#library-dialog .lib-detail .lib-image-button img{height:260px}
      #library-dialog .lib-grid{grid-template-columns:repeat(auto-fill,minmax(min(100%,var(--lib-card-width,160px)),1fr));gap:10px}#library-dialog .lib-select img{height:220px}
      #library-dialog .lib-pair{gap:8px}#library-dialog .lib-pair img{height:260px}#library-dialog .lib-footer{padding:8px 12px;gap:10px}#library-dialog .lib-queue{display:none}}
  `));
  const dialog = el("dialog", "", {id: "library-dialog", ariaLabel: tr("이미지 작업실")});
  const message = el("p", tr("기준 그림을 넣거나 보관한 사례를 살펴보세요."), {id: "library-message", role: "status"});
  const report = error => {window.AppI18n.setText(message, () => error.message || String(error));};
  const row = (...children) => {const r = el("div", "", {className: "lib-row"}); r.append(...children); return r;};
  const button = (text, action, props = {}) => {
    const b = el("button", text, {type: "button", ...props});
    b.addEventListener("click", () => Promise.resolve().then(action).catch(report));
    return b;
  };
  const api = async (route, data, options = {}) => {
    const response = await fetch(`/api/library/${route}`, data === undefined ? {cache: "no-store", ...options}
      : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || tr("라이브러리 요청에 실패했습니다."));
    return payload;
  };
  const previewURL = id => `/api/library/preview/${id}`;
  const artistLabel = item => item.records.find(r => r.combo.artists.length)?.combo.artists.map(a => a.tag).join(" + ") || tr("작가 태그 기록 없음");
  let revision = 0, detailRevision = 0, offset = 0, combination = "", selectedId = "", items = [], search = null;
  let pendingSearches = 0, detailLoading = false, comparisonBusy = false, modeChosen = false, loaded = false;
  let pairSelection = [], tab = "discover", reference = null, objectURL = null, pollBusy = false;
  let draft = null, draftDirty = false, draftHistory = [];
  const detail = el("aside", tr("사례를 선택하면 작가 조합과 원문을 여기서 볼 수 있습니다."), {className: "lib-detail", id: "library-detail", ariaLabel: tr("선택한 사례")});
  const grid = el("div", "", {className: "lib-grid", id: "library-grid"});
  const count = el("p", "", {className: "lib-count"});
  const groups = el("details", "", {className: "lib-combos", hidden: true});
  const query = el("input", "", {type: "search", placeholder: tr("프롬프트·태그·컬렉션 검색"), maxLength: 256, ariaLabel: tr("라이브러리 검색")});
  const favorites = el("input", "", {type: "checkbox", id: "library-favorites"});
  const favoriteLabel = el("label", ""); favoriteLabel.append(favorites, window.AppI18n.textNode(tr("즐겨찾기")));
  const mode = el("select", "", {ariaLabel: tr("이미지 검색 방식")});
  mode.append(el("option", tr("색감·배치·윤곽 (CPU)"), {value: "visual"}), el("option", tr("VRS 이미지 검색"), {value: "vrs"}));
  mode.addEventListener("change", () => {modeChosen = true;});
  const size = el("select", "", {ariaLabel: tr("카드 크기")});
  for (const [value, label] of [["160", tr("작게")], ["210", tr("보통")], ["300", tr("크게")]]) size.append(el("option", label, {value}));
  size.value = "210";
  size.addEventListener("change", () => {
    grid.style.setProperty("--lib-card-width", `${size.value}px`);
    grid.style.setProperty("--lib-image-height", `${Math.round(Number(size.value) * 1.25)}px`);
  });
  const more = button(tr("더 보기"), () => browse(true), {hidden: true});
  const discover = el("section", "", {className: "lib-stage", ariaLabel: tr("사례 탐색")});
  const compare = el("section", "", {className: "lib-stage", ariaLabel: tr("후보 비교"), hidden: true});
  const compose = el("section", "", {className: "lib-stage lib-compose", ariaLabel: tr("프롬프트 편집"), hidden: true});
  const tabs = {}, mobileScroll = {};
  function setTab(next) {
    const moved = next !== tab && matchMedia("(max-width:900px)").matches;
    if (moved) mobileScroll[tab] = layout.scrollTop;
    tab = next;
    for (const [name, panel] of Object.entries({discover, compare, compose})) {
      panel.hidden = name !== next; tabs[name].setAttribute("aria-pressed", String(name === next));
    }
    if (next === "compare") renderCompare();
    if (moved) layout.scrollTop = mobileScroll[next] || 0;
  }
  const nav = el("nav", "", {ariaLabel: tr("작업 단계")});
  for (const [key, title] of [["discover", tr("01 탐색")], ["compare", tr("02 비교")], ["compose", tr("03 프롬프트")]]) {
    tabs[key] = button(title, () => setTab(key), {id: `library-tab-${key}`});
    tabs[key].setAttribute("aria-pressed", String(key === tab)); nav.append(tabs[key]);
  }
  const zoom = el("dialog", "", {id: "library-zoom", ariaLabel: tr("이미지 크게 보기")});
  const zoomImage = el("img", "", {alt: tr("확대한 이미지")});
  zoom.append(button(tr("큰 그림 닫기"), () => zoom.close()), zoomImage);
  dialog.append(zoom);
  function imageButton(src, alt, fallback) {
    const img = el("img", "", {src, alt});
    if (fallback) img.addEventListener("error", () => {
      img.src = fallback; window.AppI18n.setProperty(img, "alt", () => tr`${alt} (원본 미리보기 없음, 보관된 썸네일)`);
    }, {once: true});
    const b = button("", () => {
      zoomImage.src = img.src; window.AppI18n.setProperty(zoomImage, "alt", () => img.alt);
      zoomImage.onerror = fallback ? () => {zoomImage.onerror = null; zoomImage.src = fallback;} : null;
      zoom.showModal();
    }, {className: "lib-image-button", ariaLabel: tr`${alt} 크게 보기`});
    b.append(img); return b;
  }
  const referencePanel = el("aside", "", {className: "lib-reference", ariaLabel: tr("기준 그림")});
  const referenceMedia = el("div", "", {className: "lib-ref-media"});
  const referenceName = el("p", tr("아직 기준 그림이 없습니다."), {className: "lib-ref-name lib-muted"});
  function renderReference() {
    referenceMedia.replaceChildren(reference ? imageButton(reference.src, tr("기준 그림"), reference.thumbnail)
      : el("div", tr("찾고 싶은 그림"), {className: "lib-placeholder"}));
    window.AppI18n.setText(referenceName, () => reference?.name || tr("아직 기준 그림이 없습니다."));
  }
  const file = el("input", "", {type: "file", accept: "image/png,image/jpeg,image/webp", ariaLabel: tr("비슷한 사례를 찾을 이미지")});
  const drop = el("div", tr("이미지를 놓거나 선택하세요"), {className: "lib-drop"}); drop.append(file);
  file.addEventListener("change", () => {if (file.files[0]) searchImage(null, file.files[0]).catch(report); file.value = "";});
  drop.addEventListener("dragover", e => e.preventDefault());
  drop.addEventListener("drop", e => {e.preventDefault(); if (e.dataTransfer.files[0]) searchImage(null, e.dataTransfer.files[0]).catch(report);});
  referencePanel.append(el("h3", tr("기준 그림")), referenceMedia, referenceName, drop,
    el("p", tr("그림에서 출발해 사례와 작가 조합을 찾아보세요."), {className: "lib-muted lib-ref-hint"}));
  renderReference();

  function renderCards(append = false, newItems = items) {
    if (!append) grid.replaceChildren();
    for (const item of newItems) {
      const card = el("article", "", {className: `lib-card${selectedId === item.id ? " is-selected" : ""}`}); card.dataset.id = item.id;
      const title = artistLabel(item);
      const select = button("", () => showDetail(item.id), {className: "lib-select", ariaLabel: tr`${title} 사례 보기`});
      select.append(el("img", "", {src: item.thumbnail, alt: tr("등록된 사례 이미지"), loading: "lazy"}),
        el("span", () => `${item.favorite ? "★ " : ""}${title}`, {className: "lib-card-title", title}),
        el("span", () => `${item.score !== undefined ? tr`${search?.items.findIndex(i => i.id === item.id) + 1}순위 · ` : ""}${item.width} × ${item.height}`, {className: "lib-card-meta"}));
      card.append(select);
      if (search?.items.some(i => i.id === item.id)) {
        const check = el("input", "", {type: "checkbox", checked: pairSelection.includes(item.id)});
        check.addEventListener("change", () => {
          if (check.checked && pairSelection.length >= 2) {check.checked = false; window.AppI18n.setText(message, () => tr("비교할 후보는 두 장까지 선택해 주세요.")); return;}
          pairSelection = check.checked ? [...pairSelection, item.id] : pairSelection.filter(id => id !== item.id);
          window.AppI18n.setText(message, () => tr`비교 후보 ${pairSelection.length}/2장 선택. 비교 탭에서 기준 그림과 나란히 볼 수 있습니다.`);
        });
        const label = el("label", ""); label.append(check, window.AppI18n.textNode(tr("비교에 담기"))); card.append(label);
      }
      grid.append(card);
    }
    if (!grid.children.length) grid.append(el("p", tr("표시할 사례가 없습니다. 검색 조건을 바꾸거나 이미지를 가져와 주세요."), {className: "lib-placeholder"}));
  }
  function clearSelection() {
    selectedId = ""; ++detailRevision;
    window.AppI18n.setText(detail, () => tr("사례를 선택하면 작가 조합과 원문을 여기서 볼 수 있습니다."));
  }
  async function browse(append = false, keepSearch = false) {
    const ticket = ++revision;
    window.AppI18n.setText(message, () => tr("사례를 불러오는 중…"));
    const start = append ? offset : 0;
    const params = new URLSearchParams({q: query.value, offset: String(start), favorite: favorites.checked ? "1" : "0", combo: combination});
    const data = await api(`items?${params}`);
    if (ticket !== revision) return;
    if (!append) {
      if (!keepSearch) {search = null; pairSelection = []; groups.hidden = true;}
      items = []; clearSelection();
    }
    backToSearch.hidden = !search || !combination;
    items.push(...data.items); offset = start + data.items.length;
    renderCards(append, data.items); more.hidden = offset >= data.total;
    window.AppI18n.setText(count, () => tr`${offset} / ${data.total}장${combination ? tr(" · 선택한 작가 조합") : ""}`);
    window.AppI18n.setText(message, () => tr("사례를 선택해 원문을 확인하거나 두 후보를 비교하세요."));
    loaded = true; setTab("discover");
  }
  async function searchImage(id, imageFile) {
    if (imageFile && (!/\.(png|jpe?g|webp)$/i.test(imageFile.name) || imageFile.size > 32 * 1024 * 1024)) throw new Error(tr("PNG/JPEG/WebP, 최대 32 MiB 이미지를 선택해 주세요."));
    const ticket = ++revision;
    window.AppI18n.setText(message, () => tr("이미지에서 비슷한 사례를 찾는 중…")); pendingSearches++; renderCompare();
    try {
      const source = id ? await api(`item/${id}`) : null;
      const result = imageFile ? await api(`query-image?mode=${mode.value}`, undefined,
        {method: "POST", headers: {"Content-Type": imageFile.type || (/\.webp$/i.test(imageFile.name) ? "image/webp" : /\.jpe?g$/i.test(imageFile.name) ? "image/jpeg" : "image/png")}, body: imageFile})
        : await api("search", {id, mode: mode.value});
      if (ticket !== revision) return;
      if (objectURL) URL.revokeObjectURL(objectURL);
      objectURL = imageFile ? URL.createObjectURL(imageFile) : null;
      reference = imageFile ? {src: objectURL, name: imageFile.name}
        : {src: previewURL(id), thumbnail: source.thumbnail, name: artistLabel(source)};
      renderReference(); clearSelection(); pairSelection = [];
      search = {...result, cursor: 0, history: []}; items = result.items;
      renderCards(); more.hidden = true; backToSearch.hidden = true; combination = ""; query.value = ""; favorites.checked = false;
      window.AppI18n.setText(count, () => tr`${result.total_indexed}장에서 유사사례 ${items.length}장 · ${result.mode === "vrs" ? "VRS" : "CPU"} 검색`);
      groups.replaceChildren(el("summary", tr`검색에서 찾은 작가 조합 ${result.combinations.length}종`));
      const groupRows = el("div", "", {className: "lib-row"});
      for (const group of result.combinations) {
        const label = group.combo.artists.map(a => `${a.tag} (${a.weight.toFixed(2)})`).join(" + ");
        groupRows.append(button(tr`${label} · ${group.cases.length}개 사례`, () => {
          combination = group.combo.key; query.value = ""; favorites.checked = false; return browse(false, true);
        }));
      }
      groups.append(groupRows); groups.hidden = !result.combinations.length;
      window.AppI18n.setText(message, () => tr("검색 완료 · 같은 픽셀의 사본은 제외했습니다. 순위는 화풍의 정답률을 뜻하지 않습니다."));
      loaded = true; setTab("discover");
    } finally {pendingSearches--; if (tab === "compare") renderCompare();}
  }
  function currentPair() {
    if (!search || search.items.length < 2) return [];
    if (pairSelection.length === 2) return pairSelection.map(id => search.items.find(i => i.id === id));
    const start = search.cursor * 2;
    return start >= search.items.length ? [] : [search.items[start], search.items[start + 1] || search.items[0]];
  }
  function renderCompare() {
    compare.replaceChildren(el("h2", tr("기준 그림에 더 가까운 쪽은?")),
      el("p", tr("선·채색·명암·질감을 비교해 주세요. 마음에 드는 정도와 닮은 정도는 따로 기록합니다."), {className: "lib-muted"}));
    if (pendingSearches) {compare.append(el("p", tr("새 검색을 마친 뒤 비교할 수 있습니다."))); return;}
    if (!search || search.items.length < 2) {compare.append(el("p", tr("먼저 기준 그림으로 검색해 주세요. 같은 검색의 후보 두 장을 비교합니다."), {className: "lib-placeholder"})); return;}
    const pair = currentPair();
    const undo = button(tr("마지막 판단 취소"), undoComparison, {disabled: comparisonBusy || !search.history.length});
    compare.append(row(el("span", tr`이 검색에서 ${search.history.length}회 판단`, {className: "lib-muted"}), undo));
    if (!pair.length) {compare.append(el("p", tr("이번 후보 비교를 마쳤습니다. 탐색에서 두 장을 골라 추가로 비교할 수 있습니다."), {className: "lib-placeholder"})); return;}
    const pairPanel = el("div", "", {className: "lib-pair"});
    pair.forEach((item, index) => {
      const fig = el("figure", "");
      fig.append(imageButton(previewURL(item.id), tr`후보 ${index ? "B" : "A"}`, item.thumbnail),
        el("figcaption", () => `${index ? "B" : "A"} · ${artistLabel(item)}`),
        button(tr("이 사례 기록 보기"), () => showDetail(item.id)));
      pairPanel.append(fig);
    });
    compare.append(pairPanel);
    const votes = el("div", "", {className: "lib-row lib-votes"});
    for (const [choice, title] of [["a", tr("A가 더 닮음")], ["b", tr("B가 더 닮음")], ["both", tr("둘 다 비슷함")], ["neither", tr("둘 다 다름")], ["skip", tr("판단 보류")]]) {
      votes.append(button(title, () => vote(choice), {disabled: comparisonBusy}));
    }
    compare.append(votes, el("p", tr("판단은 로컬에 저장됩니다. 아직 검색 순위에 자동 반영되지는 않습니다."), {className: "lib-muted"}));
  }
  async function vote(choice) {
    if (comparisonBusy || pendingSearches) return;
    const owner = search, pair = currentPair(); if (pair.length !== 2) return;
    const before = {cursor: owner.cursor, selection: [...pairSelection]};
    comparisonBusy = true; renderCompare();
    try {
      const result = await api("compare", {query_id: owner.query_id, a: pair[0].id, b: pair[1].id, choice});
      owner.history.push({...before, id: result.id});
      if (search === owner) {owner.cursor++; pairSelection = []; renderCards(); window.AppI18n.setText(message, () => tr("비교 판단을 저장했습니다. 마지막 판단을 취소할 수 있습니다."));}
    } finally {comparisonBusy = false; renderCompare();}
  }
  async function undoComparison() {
    if (comparisonBusy || !search?.history.length) return;
    const owner = search, last = owner.history.at(-1);
    comparisonBusy = true; renderCompare();
    try {
      await api("compare/undo", {id: last.id}); owner.history.pop(); owner.cursor = last.cursor;
      if (search === owner) {pairSelection = last.selection; renderCards(); window.AppI18n.setText(message, () => tr("마지막 비교 판단을 취소했습니다."));}
    } finally {comparisonBusy = false; renderCompare();}
  }

  const draftPrompt = el("textarea", "", {id: "library-draft", ariaLabel: tr("작업 프롬프트")});
  const draftNegative = el("textarea", "", {className: "lib-negative", ariaLabel: tr("작업 네거티브")});
  const draftInfo = el("p", "", {className: "lib-muted"});
  const draftConditions = el("details", "");
  const undoDraft = button(tr("가져오기 되돌리기"), () => {
    if (!draftHistory.length) return;
    const last = draftHistory.pop(); draft = last.draft; draftDirty = last.dirty; renderDraft();
    window.AppI18n.setText(message, () => tr("가져오기 전 초안으로 되돌렸습니다."));
  }, {disabled: true});
  const clone = value => JSON.parse(JSON.stringify(value));
  const draftKey = "anima.library-draft.v1";
  try {
    const saved = JSON.parse(localStorage.getItem(draftKey));
    if (saved?.version === 1 && typeof saved.draft?.prompt === "string" && saved.dirty) {
      draft = saved.draft; draftDirty = true; draftHistory = saved.history || [];
    }
  } catch (_) { /* Storage can be unavailable; editing remains usable. */ }
  function saveDraft() {
    try {localStorage.setItem(draftKey, JSON.stringify({version: 1, draft, dirty: draftDirty, history: draftHistory.slice(-10)}));}
    catch (_) {window.AppI18n.setText(message, () => tr("작업실 초안을 저장하지 못했습니다. 브라우저 저장 공간을 확인해 주세요."));}
  }
  function readDraft() {return {...(window.animaLibraryReadDraft?.() || {prompt: "", negative_prompt: ""}), request: null, source: ""};}
  function renderDraft() {
    if (!draft) draft = readDraft();
    draftPrompt.value = draft.prompt; draftNegative.value = draft.negative_prompt;
    window.AppI18n.setText(draftInfo, () => draft.source ? tr`가져온 기록: ${draft.source}${draft.request ? tr(" · 생성 조건 포함") : tr(" · 프롬프트만")}` : tr("현재 생성 화면의 프롬프트에서 시작합니다."));
    draftConditions.replaceChildren(el("summary", tr("함께 가져온 생성 조건")), el("pre", JSON.stringify(draft.request, null, 2)));
    draftConditions.hidden = !draft.request; undoDraft.disabled = !draftHistory.length;
    saveDraft();
  }
  for (const [field, input] of [["prompt", draftPrompt], ["negative_prompt", draftNegative]]) {
    input.addEventListener("input", () => {draft[field] = input.value; draftDirty = true; saveDraft();});
  }
  async function composeText(text, negative = "", routing = {source: "auto"}) {
    const response = await fetch("/api/prompts/plan", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({provider: "local", prompt: text || "", negative_prompt: negative, prompt_routing: routing})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || tr("프롬프트 표기를 맞추지 못했습니다."));
    return Object.fromEntries(result.stages[0].fields.map(field => [field.field, field.converted]));
  }
  let staging = false;
  async function stageRecord(record, scope, assetId) {
    if (staging) return;
    staging = true;
    const before = clone(draft);
    try {
      let next;
      if (scope === "artists") {
        const [current, incoming] = await Promise.all([
          composeText(draft.prompt, draft.negative_prompt, draft.prompt_routing), composeText(record.combo.prompt)]);
        next = {...current, prompt: [current.prompt.trim(), incoming.prompt].filter(Boolean).join(", "), prompt_routing: {source: "comfyui"}};
      } else {
        const request = scope === "all" ? (record.request.workflow_base_request || record.request.authoring_request || record.request) : record.request;
        next = {prompt: request.prompt || "", negative_prompt: request.negative_prompt || "", prompt_routing: request.prompt_routing || {source: "auto"}};
        if (scope === "all") next.request = clone(request);
      }
      if (JSON.stringify(draft) !== JSON.stringify(before)) throw new Error(tr("변환 중 초안이 바뀌었습니다. 다시 가져와 주세요."));
      const origin = {asset_id: assetId, record_id: record.id, scope};
      const origins = scope === "artists" ? [...(draft.generation_sources || [])] : [];
      if (!origins.some(item => JSON.stringify(item) === JSON.stringify(origin))) origins.push(origin);
      if (origins.length > 16) throw new Error(tr("참고 사례는 16개까지 연결할 수 있습니다. 생성 화면에서 연결을 정리해 주세요."));
    draftHistory.push({draft: clone(draft), dirty: draftDirty}); if (draftHistory.length > 50) draftHistory.shift();
    Object.assign(draft, next, {generation_sources: origins});
    if (scope === "prompt") draft.request = null;
    draft.source = `${record.source} · ${record.id.slice(0, 10)}`; draftDirty = true;
    renderDraft(); setTab("compose"); draftPrompt.focus(); window.AppI18n.setText(message, () => tr("편집 초안에 가져왔습니다. 내용을 다듬거나 가져오기를 되돌릴 수 있습니다."));
    } finally {staging = false;}
  }
  compose.append(el("h2", tr("찾은 조합으로 내 프롬프트 만들기")),
    el("p", tr("탐색으로 돌아가도 초안이 유지됩니다. 생성 화면에 적용하기 전까지 원래 생성 폼은 그대로입니다."), {className: "lib-muted"}),
    draftInfo, el("label", tr("프롬프트"), {htmlFor: draftPrompt.id}), draftPrompt, el("label", tr("네거티브")), draftNegative, draftConditions,
    row(undoDraft, button(tr("생성 화면의 프롬프트 가져오기"), () => {
      draftHistory.push({draft: clone(draft), dirty: draftDirty}); draft = readDraft(); draftDirty = true; renderDraft();
    }), button(tr("생성 화면에 적용"), () => {
      window.animaLibraryApply({...draft.request, prompt: draft.prompt, negative_prompt: draft.negative_prompt,
        prompt_routing: draft.prompt_routing || {source: "auto"}, generation_sources: draft.generation_sources || []}, draft.request ? "all" : "prompt");
      draftDirty = false; saveDraft(); dialog.close(); document.getElementById("prompt")?.focus();
    }, {className: "lib-primary"})),
    el("p", tr("초안과 최근 가져오기 기록은 이 브라우저에 저장됩니다. 새로고침 후에도 이어서 편집할 수 있습니다. 적용은 생성을 시작하지 않습니다."), {className: "lib-muted"}));

  async function showDetail(id, recordId = "") {
    const ticket = ++detailRevision;
    detailLoading = true;
    let item;
    try {item = await api(`item/${id}`);} finally {detailLoading = false;}
    if (ticket !== detailRevision) return;
    selectedId = id;
    for (const card of grid.querySelectorAll(".lib-card")) card.classList.toggle("is-selected", card.dataset.id === id);
    detail.replaceChildren(el("h3", tr("사례 → 작가 조합 → 프롬프트")), imageButton(previewURL(id), tr("선택한 사례"), item.thumbnail));
    detail.append(row(button(tr("이 그림과 비슷한 사례"), () => searchImage(id)), button(item.favorite ? tr("★ 즐겨찾기 해제") : tr("☆ 즐겨찾기"), async () => {
      await api("annotate", {id, favorite: !item.favorite});
      const listed = items.find(i => i.id === id); if (listed) listed.favorite = !item.favorite;
      renderCards(); if (selectedId === id) await showDetail(id);
    })));
    if (search?.items.some(i => i.id === id)) {
      const savedQuery = search.query_id;
      const rate = (field, value) => async () => {
        await api("feedback", {query_id: savedQuery, id, [field]: value});
        window.AppI18n.setText(message, () => tr("평가를 저장했습니다. 닮음과 재사용 가능성을 따로 기록합니다."));
      };
      detail.append(row(button(tr("닮았음"), rate("visual", 1)), button(tr("안 닮았음"), rate("visual", -1)), button(tr("조건을 다시 쓰고 싶음"), rate("reuse", 1))));
    }
    const selector = el("select", "", {ariaLabel: tr("생성 기록 선택")});
    item.records.forEach((record, i) => selector.append(el("option", () => `${i + 1}. ${record.source}`, {value: String(i)})));
    if (recordId) {
      const index = item.records.findIndex(record => record.id === recordId);
      if (index >= 0) selector.value = String(index);
      else window.AppI18n.setText(message, () => tr("연결된 생성 기록을 찾지 못했습니다. 이 이미지의 남아 있는 기록을 표시합니다."));
    }
    const recordPanel = el("div", "", {className: "lib-record"});
    const renderRecord = () => {
      const record = item.records[Number(selector.value)]; recordPanel.replaceChildren();
      if (!record) {recordPanel.append(el("p", tr("생성 기록이 없습니다."))); return;}
      const request = record.request;
      recordPanel.append(el("h3", tr("기록된 작가 조합")), el("p", record.combo.prompt || tr("분리 가능한 작가 태그 없음"), {className: "lib-artist"}),
        el("p", () => `${request.nai_model || request.model || request.provider || tr("모델 미상")} · ${request.width || item.width} × ${request.height || item.height} · seed ${request.seed ?? tr("미상")}`, {className: "lib-muted"}),
        el("textarea", "", {value: request.prompt || "", readOnly: true, ariaLabel: tr("기록된 프롬프트")}));
      recordPanel.append(row(
        button(tr("작가 태그만 덧붙이기"), () => stageRecord(record, "artists", id), {disabled: !record.combo.key}),
        button(tr("프롬프트 가져오기"), () => stageRecord(record, "prompt", id), {disabled: !request.prompt}),
        button(tr("조건까지 가져오기"), () => stageRecord(record, "all", id), {disabled: !request.prompt || !["local", "novelai"].includes(request.provider || (record.source === "anima_manifest" ? "local" : ""))})));
      for (const warning of record.warnings) recordPanel.append(el("p", warning, {className: "lib-muted"}));
      const raw = el("details", ""); raw.append(el("summary", tr("저장된 생성 조건 보기")), el("pre", JSON.stringify(request, null, 2))); recordPanel.append(raw);
    };
    selector.addEventListener("change", renderRecord); detail.append(selector, recordPanel); renderRecord();
    const annotations = el("details", ""); annotations.append(el("summary", tr("태그 · 컬렉션 · 메모")));
    const fields = {};
    for (const [name, label, max] of [["tags", tr("태그"), 2000], ["collection", tr("컬렉션"), 200], ["note", tr("메모"), 8000]]) {
      fields[name] = el("input", "", {value: item[name], maxLength: max, id: `library-${name}`});
      annotations.append(el("label", label, {htmlFor: fields[name].id}), fields[name]);
    }
    annotations.append(button(tr("정리 내용 저장"), async () => {
      await api("annotate", {id, ...Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.value]))});
      window.AppI18n.setText(message, () => tr("태그·컬렉션·메모를 저장했습니다."));
    })); detail.append(annotations);
    const sources = el("details", ""); sources.append(el("summary", tr("원본 위치 · 출처")));
    for (const source of item.sources) {
      sources.append(el("p", () => `${source.available ? "" : tr("파일 누락 · ")}${source.path}`, {className: "lib-muted"}));
      if (/^https?:\/\//.test(source.source_url || "")) sources.append(el("a", tr("원본 게시물 열기"), {href: source.source_url, target: "_blank", rel: "noopener noreferrer"}));
    }
    detail.append(sources);
    detail.scrollTop = 0;
    if (matchMedia("(max-width:900px)").matches) detail.scrollIntoView({block: "start"});
  }

  const folders = el("textarea", "", {placeholder: tr("폴더의 전체 경로를 한 줄에 하나씩 입력"), ariaLabel: tr("가져올 폴더")});
  const progress = el("p", "", {className: "lib-muted"}), stats = el("p", "", {className: "lib-muted"});
  const build = button(tr("VRS 색인 준비"), async () => {await api("import", {kind: "vrs"}); await status();});
  const cancel = button(tr("작업 취소"), async () => {await api("cancel", {}); await status();});
  const settings = el("details", ""); settings.append(el("summary", tr("검색 방식 · 라이브러리 관리")), stats, mode, folders,
    row(button(tr("폴더 가져오기"), async () => {
      const roots = folders.value.split("\n").map(s => s.trim()).filter(Boolean);
      if (!roots.length) throw new Error(tr("가져올 폴더를 입력해 주세요."));
      await api("import", {folders: roots, limit: 2000}); await status();
    }), button(tr("앱 생성 이력 연결"), async () => {await api("import", {kind: "sync"}); await status();}), build, cancel), progress);
  referencePanel.append(settings);
  let lastJob = "";
  async function status(refresh = true) {
    if (pollBusy) return; pollBusy = true;
    try {
      const data = await api("status");
      window.AppI18n.setText(stats, () => tr`${data.items} / ${data.capacity}장 · 작가 조합 ${data.artist_sequences}종 · VRS 색인 ${data.vrs_indexed}장 · 평가 ${data.feedback}건`);
      const ready = Boolean(data.vrs_contract && data.vrs_indexed === data.items && data.items);
      mode.options[1].disabled = !ready; window.AppI18n.setText(mode.options[1], () => ready ? tr("VRS 이미지 검색 · 준비됨") : tr("VRS 이미지 검색 · 색인 준비 필요"));
      if (!modeChosen) mode.value = ready ? "vrs" : "visual";
      build.disabled = !data.vrs_contract || data.job.status === "running"; cancel.disabled = data.job.status !== "running";
      window.AppI18n.setText(progress, () => data.job.status === "idle" ? "" : tr`${data.job.status} · 처리 ${data.job.processed || 0} · 추가 ${data.job.added || 0} · 오류 ${data.job.errors || 0} ${data.job.message || ""}`);
      if (refresh && lastJob === "running" && data.job.status !== "running" && !search && !pendingSearches && !selectedId && tab === "discover") await browse();
      lastJob = data.job.status;
    } finally {pollBusy = false;}
  }
  const all = async () => {combination = ""; query.value = ""; favorites.checked = false; await browse();};
  const textSearch = async () => {combination = ""; await browse();};
  const backToSearch = button(tr("유사사례로 돌아가기"), () => {
    if (!search) return;
    ++revision; combination = ""; query.value = ""; favorites.checked = false;
    items = search.items; clearSelection(); renderCards(); more.hidden = true; backToSearch.hidden = true;
    window.AppI18n.setText(count, () => tr`${search.total_indexed}장에서 유사사례 ${items.length}장 · ${search.mode === "vrs" ? "VRS" : "CPU"} 검색`);
    window.AppI18n.setText(message, () => tr("기준 그림의 검색 결과로 돌아왔습니다."));
  }, {hidden: true});
  const searchForm = el("form", "", {className: "lib-toolbar"});
  searchForm.append(query, button(tr("검색"), textSearch), button(tr("전체 보기"), all), backToSearch, favoriteLabel, size);
  searchForm.addEventListener("submit", e => {e.preventDefault(); textSearch().catch(report);});
  favorites.addEventListener("change", () => textSearch().catch(report));
  discover.append(searchForm, count, groups, grid, more);
  const header = el("header", "", {className: "lib-header"});
  const locale = document.getElementById("nai-language").cloneNode(true);
  locale.removeAttribute("id");
  window.AppI18n.setAttribute(locale, "aria-label", tr("앱 언어"));
  locale.addEventListener("change", () => window.AppI18n.setLanguage(locale.value));
  header.append(el("h2", tr("Anima · 이미지 작업실")), nav, locale, el("p", tr("그림 → 사례 → 조합 → 프롬프트"), {className: "lib-muted"}), button(tr("생성 화면으로"), () => dialog.close()));
  const main = el("main", "", {className: "lib-main"}); main.append(discover, compare, compose);
  const layout = el("div", "", {className: "lib-layout"}); layout.append(referencePanel, main, detail);
  const queue = el("span", "", {className: "lib-queue"});
  const footer = el("footer", "", {className: "lib-footer"}); footer.append(message, queue);
  dialog.append(header, layout, footer); document.body.append(dialog);
  const queueStatus = document.getElementById("queue-status");
  const updateQueue = () => {window.AppI18n.setText(queue, () => tr`생성: ${queueStatus?.textContent || tr("대기")}`);};
  if (queueStatus) new MutationObserver(updateQueue).observe(queueStatus, {childList: true, characterData: true, subtree: true});
  updateQueue();
  const entry = button(tr("이미지 라이브러리 열기"), async () => {
    if (dialog.open) return;
    if (!draft || !draftDirty) {draft = readDraft(); draftHistory = [];}
    renderDraft();
    dialog.showModal(); await status(false); if (!loaded) await browse();
  }, {id: "open-library", className: "secondary-button"});
  document.querySelector(".control-frame h1")?.after(entry);
  window.animaLibraryOpenItem = async (id, recordId = "") => {
    try {
      if (!draft || !draftDirty) {draft = readDraft(); draftHistory = [];}
      renderDraft();
      if (!dialog.open) dialog.showModal();
      setTab("discover"); await showDetail(id, recordId);
    } catch (error) {report(error);}
  };
  dialog.addEventListener("keydown", e => {
    if (zoom.open || e.target.matches("input,textarea,select") || e.ctrlKey || e.metaKey || e.altKey || tab !== "discover" || detailLoading) return;
    if (!["ArrowLeft", "ArrowRight"].includes(e.key) || !items.length) return;
    e.preventDefault(); const index = items.findIndex(i => i.id === selectedId);
    const next = Math.max(0, Math.min(items.length - 1, index + (e.key === "ArrowRight" ? 1 : -1)));
    showDetail(items[next].id).then(() => grid.querySelector(`[data-id="${selectedId}"] button`)?.focus()).catch(report);
  });
  window.setInterval(() => {if (dialog.open && !document.hidden) status().catch(report);}, 4000);
})();
