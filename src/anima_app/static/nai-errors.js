// SPDX-License-Identifier: GPL-3.0-only
// App adaptation of ComfyUI_RS_NAI_API_Request 4de9146 web/errors.js.
(() => {
  const displayed = new Map();
  const labels = {
    ko: {heading: "오류 원인과 다음 조치", detail: "상세 정보", unknown: "원격 결과가 불확실합니다. 자동 재전송하지 않습니다. 다시 실행하기 전에 저장 결과와 계정 상태를 확인하세요.",
      partial: "완료된 이미지 또는 보정 결과는 보존했습니다. 실패한 뒤의 작업 예약은 중지했습니다.",
      validation: "입력 확인", subscription: "Opus 자격 확인", generation: "이미지 생성", response: "이미지 응답 검사", detailer: "영역 보정",
      detailer_prepare: "디테일러 준비", detailer_save: "보정 결과 저장", reference_prepare: "참조 준비", vibe_encoding: "Vibe 인코딩",
      vibe_cache_save: "Vibe 캐시 저장", tagger_prepare: "태거 준비", tagger_download: "태거 파일 준비", tagger_inference: "태거 추론",
      output_save: "이미지 저장", metadata_save: "생성 기록 저장", metadata_import: "메타데이터 가져오기", prompt_conversion: "프롬프트 변환"},
    ja: {heading: "エラーの原因と次の対処", detail: "詳細情報", unknown: "リモート処理の結果は不明です。自動再送しません。再実行前に保存結果とアカウント状態を確認してください。",
      partial: "完了済みの画像・補正結果は保持しました。失敗後の処理予約を停止しました。",
      validation: "入力確認", subscription: "Opus資格確認", generation: "画像生成", response: "画像応答検証", detailer: "領域補正",
      detailer_prepare: "ディテイラー準備", detailer_save: "補正結果保存", reference_prepare: "参照準備", vibe_encoding: "Vibeエンコード",
      vibe_cache_save: "Vibeキャッシュ保存", tagger_prepare: "タガー準備", tagger_download: "タガーファイル準備", tagger_inference: "タガー推論",
      output_save: "画像保存", metadata_save: "生成履歴保存", metadata_import: "メタデータ読み込み", prompt_conversion: "プロンプト変換"},
    en: {heading: "Error and next steps", detail: "Technical details", unknown: "The remote outcome is unknown. This request will not be automatically repeated. Check saved results and account state before retrying.",
      partial: "Completed images or corrections were preserved. Further scheduling has stopped.",
      validation: "Input validation", subscription: "Opus eligibility", generation: "Image generation", response: "Image response validation", detailer: "Region correction",
      detailer_prepare: "Detailer preparation", detailer_save: "Save corrected result", reference_prepare: "Reference preparation", vibe_encoding: "Vibe encoding",
      vibe_cache_save: "Save Vibe cache", tagger_prepare: "Tagger preparation", tagger_download: "Tagger file preparation", tagger_inference: "Tagger inference",
      output_save: "Save image", metadata_save: "Save generation record", metadata_import: "Import metadata", prompt_conversion: "Prompt conversion"}
  };
  function locale() { return labels[window.NaiI18n?.language] ? window.NaiI18n.language : "en"; }
  function collect(payload) {
    const result = [], seen = new Set();
    const regions = payload?.detailer_regions || payload?.novelai?.detailer || [];
    for (const item of [payload, payload?.detailer_failure, payload?.novelai?.detailer_failure, ...regions.map(r => r.failure)]) {
      const detail = item?.error_detail;
      if (!detail?.messages) continue;
      const key = JSON.stringify([detail.code, detail.stage, detail.details]);
      if (!seen.has(key)) { result.push(item); seen.add(key); }
    }
    return result;
  }
  function message(payload, fallback = "") {
    const detail = payload?.error_detail;
    const pair = detail?.messages?.[locale()] || detail?.messages?.en;
    return pair ? pair.join(" ") : payload?.error || fallback;
  }
  function asError(payload, fallback) {
    const error = new Error(message(payload, fallback));
    error.payload = payload;
    return error;
  }
  function render(id, payload) {
    displayed.set(id, payload);
    const root = document.getElementById(id);
    if (!root) return;
    root.replaceChildren();
    const failures = collect(payload);
    root.hidden = !failures.length;
    if (!failures.length) return;
    const lang = locale(), words = labels[lang];
    root.lang = lang;
    const heading = document.createElement("h3");
    heading.textContent = words.heading; root.append(heading);
    for (const failure of failures) {
      const detail = failure.error_detail;
      const [title, action] = detail.messages[lang] || detail.messages.en || [failure.error, ""];
      const box = document.createElement("section");
      const cause = document.createElement("strong"); cause.textContent = title; box.append(cause);
      const next = document.createElement("p"); next.textContent = action; box.append(next);
      if (failure.remote_outcome_unknown) {
        const note = document.createElement("p"); note.textContent = words.unknown; box.append(note);
      }
      const details = document.createElement("details");
      const summary = document.createElement("summary"); summary.textContent = words.detail; details.append(summary);
      const pre = document.createElement("pre");
      pre.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere";
      pre.textContent = `[${detail.code}] ${words[detail.stage] || detail.stage}`
        + (detail.http_status ? ` · HTTP ${detail.http_status}` : "")
        + `\n${detail.exception_type || ""}\n${detail.details || ""}`;
      details.append(pre); box.append(details); root.append(box);
    }
    if (payload?.detailer_failure || payload?.novelai?.detailer_failure) {
      const note = document.createElement("p"); note.textContent = words.partial; root.append(note);
    }
  }
  window.NaiErrors = Object.freeze({render, message, asError});
  window.addEventListener("nai-language-change", () => {
    for (const [id, payload] of displayed) render(id, payload);
  });
})();
