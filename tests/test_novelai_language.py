"""Language fallback/storage contract, executed in Node; DOM interaction is browser-tested."""

import json
import shutil
import subprocess

import pytest

from anima_app.server import NAI_I18N_JS


def run_language(expression, navigator="ko-KR", stored=None, blocked=False):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    harness = r"""
const fs = require("node:fs"), vm = require("node:vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const listeners = {}, writes = [], elements = new Map();
const context = {
  navigator: {language: input.navigator},
  localStorage: {
    getItem() {if(input.blocked) throw Error("blocked"); return input.stored;},
    setItem(key, value) {if(input.blocked) throw Error("blocked"); writes.push([key,value]);}
  },
  NodeFilter: {SHOW_TEXT: 4},
  document: {
    body: {}, documentElement: {},
    createTreeWalker() {return {nextNode() {return false;}};},
    querySelectorAll() {return [];},
    getElementById(id) {
      if(!elements.has(id)) elements.set(id,{dataset:{},addEventListener(){}});
      return elements.get(id);
    }
  },
  window: {dispatchEvent(){},addEventListener(name,callback){listeners[name]=callback;}},
  CustomEvent: class {constructor(type,options){this.type=type;this.detail=options.detail;}}
};
context.window.AnimaMessages = undefined;
Object.defineProperty(context, "AnimaMessages", {set(value) {context.window.AnimaMessages = value;}});
vm.runInNewContext(input.source, context);
const api = context.window.NaiI18n;
const result = eval(input.expression);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(
            {
                "source": NAI_I18N_JS,
                "expression": expression,
                "navigator": navigator,
                "stored": stored,
                "blocked": blocked,
            }
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("navigator", "stored", "expected"),
    [
        ("ja-JP", None, "ja"),
        ("JA_jp", None, "ja"),
        ("ko-KR", None, "ko"),
        ("en-US", None, "en"),
        ("ja-JP", "ko", "ko"),
        ("ko-KR", "ja", "ja"),
        ("ja-JP", "unsupported", "ja"),
        ("ja-JP", "", "ja"),
        ("fr-FR", None, "en"),
        ("ko-KR", "en", "en"),
    ],
)
def test_initial_browser_language_and_explicit_saved_preference(
    navigator, stored, expected
):
    assert run_language("api.language", navigator, stored) == expected


def test_catalog_pairs_keep_same_interpolation_parameters():
    result = run_language(r"""(() => {
      const keys = [...input.source.matchAll(/^    (\w+): \[/gm)].map(match=>match[1]);
      const result=[];
      for(const key of keys) {
        api.setLanguage("ko", false); const ko=api.text(key);
        api.setLanguage("ja", false); const ja=api.text(key);
        if(!ko || !ja || ko===key || ja===key ||
          JSON.stringify((ko.match(/\{\w+\}/g)||[]).sort())!==JSON.stringify((ja.match(/\{\w+\}/g)||[]).sort())) result.push(key);
      }
      return {count:keys.length,invalid:result};
    })()""")
    assert result["count"] >= 50
    assert result["invalid"] == []


def test_blocked_storage_and_cross_tab_clear_follow_browser_default():
    result = run_language(
        """(() => {
      api.setLanguage("ko");
      const notice=elements.get("nai-language-status").textContent;
      listeners.storage({key:"unrelated",newValue:"ja"});
      const ignored=api.language;
      listeners.storage({key:"anima.locale",newValue:null});
      const removed=api.language;
      api.setLanguage("ko");
      listeners.storage({key:null,newValue:null});
      return {notice,ignored,removed,cleared:api.language,writes};
    })()""",
        navigator="ja-JP",
        blocked=True,
    )
    assert "저장할 수 없습니다" in result["notice"]
    assert result["ignored"] == "ko"
    assert result["removed"] == result["cleared"] == "ja"
    assert result["writes"] == []


def test_locale_persistence_uses_only_language_and_missing_key_is_literal():
    result = run_language("""(() => {
      api.setLanguage("ja");
      return {writes,missing:api.text("__proto__"),label:api.text("character",{number:22}),
        injection:api.text("character",{number:"<script>foo</script>"})};
    })()""")
    assert result["writes"] == [["anima.locale", "ja"]]
    assert result["missing"] == "__proto__"
    assert result["label"] == "キャラクター 22"
    assert result["injection"] == "キャラクター <script>foo</script>"


def test_app_catalog_has_complete_english_japanese_and_matching_parameters():
    import re
    from anima_app.server import UI_MESSAGES

    assert len(UI_MESSAGES) >= 800
    parameters = re.compile(
        r"\{(?:\d+|number|field|active|limit|model|stored|hidden|warning|operation|width|height|medium|cost|steps)\}"
    )
    for source, translations in UI_MESSAGES.items():
        assert set(translations) == {"en", "ja"}, source
        for language, text in translations.items():
            assert text.strip(), (source, language)
            assert sorted(parameters.findall(text)) == sorted(
                parameters.findall(source)
            ), (source, language)
    assert UI_MESSAGES["앱 언어"]["en"] == "App language"


def test_message_retains_locale_and_never_reinterprets_interpolated_user_text():
    result = run_language(r"""(() => {
      const ui=context.window.AppI18n;
      const user='프롬프트, artist:example, {width}, <img src=x onerror=alert(1)>';
      const message=ui.msg('{0} 불러오기 실패: {1}', {0:'sample',1:user});
      api.setLanguage('en',false);const en=String(message);
      api.setLanguage('ja',false);const ja=String(message);
      api.setLanguage('ko',false);const ko=String(message);
      return {user,en,ja,ko};
    })()""")
    assert result["en"].endswith(result["user"])
    assert result["ja"].endswith(result["user"])
    assert result["ko"].endswith(result["user"])
    assert result["en"] != result["ja"] != result["ko"]
