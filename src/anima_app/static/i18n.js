// SPDX-License-Identifier: GPL-3.0-only
// Only source-authored UI messages are translated. User data is never scanned.
(() => {
  "use strict";
  const catalog = window.AnimaMessages;
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const storageKey = "anima.locale", legacyKey = "anima.nai.language";
  const normalize = value => /^(en|ko|ja)(?:[-_].*)?$/i.exec(String(value || ""))?.[1].toLowerCase() || "en";
  const valid = value => /^(en|ko|ja)(?:[-_].*)?$/i.test(String(value || ""));
  const browserLanguage = () => (navigator.languages || [navigator.language]).find(valid) || "en";
  let language = normalize(browserLanguage()), storageAvailable = true;
  try {
    const saved = localStorage.getItem(storageKey) ?? localStorage.getItem(legacyKey);
    if (valid(saved)) language = normalize(saved);
  } catch { storageAvailable = false; }
  const render = (key, params = {}) => {
    const entry = own(catalog, key) ? catalog[key] : null;
    const source = language === "ko" ? key : entry?.[language] || key;
    return source.replace(/\{(\w+)\}/g, (match, name) => own(params, name) ? String(params[name]) : match);
  };
  // A message retains its source and arguments when passed through UI helpers.
  // String coercion occurs at the DOM boundary; prompt/API strings stay ordinary strings.
  class Message extends String {
    constructor(key, params = {}) { super(render(key, params)); this.key = key; this.params = params; }
    toString() { return render(this.key, this.params); }
    toJSON() { return this.toString(); }
    [Symbol.toPrimitive]() { return this.toString(); }
  }
  function msg(source, ...values) {
    if (Array.isArray(source)) {
      const key = source.map((part, i) => part + (i < values.length ? `{${i}}` : "")).join("");
      return new Message(key, Object.fromEntries(values.map((value, i) => [i, value])));
    }
    return new Message(source, values[0]);
  }
  const bindings = new Map();
  let cleanupScheduled = false;
  function collectDetached() {
    if (cleanupScheduled || bindings.size < 512) return;
    cleanupScheduled = true;
    queueMicrotask(() => {
      for (const node of bindings.keys()) if (!node.isConnected) bindings.delete(node);
      cleanupScheduled = false;
    });
  }
  const resolve = source => typeof source === "function" ? resolve(source()) : String(source ?? "");
  function setText(element, source) {
    const value = resolve(source);
    // Bind the text node, not its parent: labels/summaries may gain input children.
    element.textContent = value;
    if (!element.firstChild) element.append(document.createTextNode(""));
    bindings.set(element.firstChild, {source, rendered: value});
    collectDetached();
    return value;
  }
  function setProperty(element, property, source) {
    const value = resolve(source);
    element[property] = value;
    let attrs = bindings.get(element);
    if (!attrs) { attrs = new Map(); bindings.set(element, attrs); }
    attrs.set(property, {source, rendered: value});
    return value;
  }
  function setAttribute(element, name, source) {
    const property = {"aria-label": "ariaLabel", "placeholder": "placeholder", "title": "title", "alt": "alt"}[name];
    if (property) return setProperty(element, property, source);
    element.setAttribute(name, resolve(source));
  }
  function textNode(source) {
    const node = document.createTextNode(resolve(source));
    bindings.set(node, {source, rendered: node.textContent});
    collectDetached();
    return node;
  }
  function apply() {
    document.documentElement.lang = language;
    document.getElementById("nai-language").value = language;
    for (const select of document.querySelectorAll("[data-app-locale]")) select.value = language;
    for (const [node, binding] of bindings) {
      if (!node.isConnected) { bindings.delete(node); continue; }
      if (binding instanceof Map) {
        for (const [property, item] of binding) {
          if (node[property] !== item.rendered) { binding.delete(property); continue; }
          const value = resolve(item.source);
          if (node[property] !== value) node[property] = value;
          item.rendered = value;
        }
      } else {
        if (node.textContent !== binding.rendered) { bindings.delete(node); continue; }
        const value = resolve(binding.source);
        if (node.textContent !== value) node.textContent = value;
        binding.rendered = value;
      }
    }
    const status = document.getElementById("nai-language-status");
    status.textContent = storageAvailable ? "" : render("이 브라우저에서는 언어를 저장할 수 없습니다. 현재 화면에만 적용합니다.");
    window.dispatchEvent(new CustomEvent("nai-language-change", {detail: {language}}));
    window.dispatchEvent(new CustomEvent("anima-locale-change", {detail: {language}}));
  }
  function setLanguage(value, persist = true) {
    language = normalize(value);
    if (persist) {
      try { localStorage.setItem(storageKey, language); storageAvailable = true; }
      catch { storageAvailable = false; }
    }
    apply();
  }
  // Capture the server-authored HTML once, before app code inserts any user data.
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const initial = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest("textarea,pre,script,style,[data-nai-i18n]")) continue;
    const key = node.textContent.trim().replace(/\s+/g, " ");
    if (own(catalog, key)) initial.push([node, msg(key)]);
  }
  for (const [node, source] of initial) {node.textContent = resolve(source); bindings.set(node, {source, rendered: node.textContent});}
  for (const element of document.querySelectorAll("[aria-label],[title],[alt],[placeholder]")) {
    for (const name of ["aria-label", "title", "alt", "placeholder"]) {
      const key = element.getAttribute(name);
      if (own(catalog, key)) setAttribute(element, name, msg(key));
    }
  }
  window.AppI18n = Object.freeze({msg, render, setText, setProperty, setAttribute, textNode, setLanguage, normalize,
    get language() { return language; }, get locale() { return {en: "en-US", ko: "ko-KR", ja: "ja-JP"}[language]; }});
  document.getElementById("nai-language").addEventListener("change", event => setLanguage(event.target.value));
  window.addEventListener("storage", event => {
    if (event.key === storageKey || event.key === null) setLanguage(valid(event.newValue) ? event.newValue : browserLanguage(), false);
  });
  apply();
})();
