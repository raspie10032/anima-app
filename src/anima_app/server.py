from __future__ import annotations

import copy
import json
import random
import re
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from anima_app import __version__
from anima_app.autocomplete import autocomplete_payload, warm_autocomplete_index
from anima_app.assets import asset_profile, asset_profiles, copy_asset_profile, import_lora_file, list_local_checkpoints, list_local_loras
from anima_app.config import AppPaths
from anima_app.defaults import (
    DEFAULT_T2I_CHECKPOINT,
    DEFAULT_T2I_CFG,
    DEFAULT_T2I_HEIGHT,
    DEFAULT_T2I_SAMPLER,
    DEFAULT_T2I_SCHEDULER,
    DEFAULT_T2I_STEPS,
    DEFAULT_T2I_WIDTH,
    PREFERRED_T2I_CHECKPOINT,
)
from anima_app.health import build_health_payload
from anima_app.llm_runtime import default_llm_client, llm_generate_payload, llm_status_payload
from anima_app.manifests import read_manifest, read_t2i_history
from anima_app.memory_profiles import resolve_auto_memory_profile
from anima_app.requests import (
    DEFAULT_FACE_DETAILER_STEPS,
    DEFAULT_TILE_SIZE,
    DEFAULT_UPSCALE_STEPS,
    FaceDetailerSettings,
    I2ISettings,
    T2ILoraConfig,
    T2IRequest,
    UpscaleSettings,
    VaeDecodeSettings,
    parse_lora_spec,
)
from anima_app.runtime.pipeline import T2IRenderer, run_t2i
from anima_app.runtime.masked_inpaint import MaskedInpaintSettings, run_masked_inpaint
from anima_app.runtime.sam3_segment import (
    Sam3MaskAdjustmentResult,
    Sam3SegmentResult,
    adjust_segment_mask,
    segment_image_concept,
    segment_image_concepts,
)
from anima_app.updates import check_github_update, version_payload
from anima_app.wildcards import expand_request_wildcards, expand_text_wildcards, list_prompt_presets, list_wildcards


_INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Anima APP</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Arial, sans-serif;
      background: #18191f;
      color: #f4f1ea;
    }
    body {
      margin: 0;
      min-height: 100vh;
      overflow: hidden;
    }
    .app-shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(280px, 320px) minmax(0, 1fr) minmax(280px, 340px);
      background: #18191f;
    }
    .control-frame,
    .history-frame {
      height: 100vh;
      min-width: 0;
      overflow: auto;
      background: #22252b;
    }
    .control-frame {
      border-right: 1px solid #373b44;
      padding: 14px;
    }
    .history-frame {
      border-left: 1px solid #373b44;
      padding: 18px;
    }
    .workspace-frame {
      min-width: 0;
      height: 100vh;
      overflow: auto;
      padding: 16px 18px 20px;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 12px;
    }
    h1 {
      font-size: 19px;
      margin: 0 0 10px;
      letter-spacing: 0;
    }
    .frame-title {
      margin: 0 0 12px;
      color: #f4f1ea;
      font-size: 16px;
      letter-spacing: 0;
    }
    label {
      display: block;
      font-size: 13px;
      margin: 10px 0 5px;
      color: #d8d2c2;
    }
    textarea,
    input,
    select {
      box-sizing: border-box;
      width: 100%;
      border: 1px solid #484d58;
      border-radius: 6px;
      background: #111319;
      color: #f4f1ea;
      padding: 8px;
      font: inherit;
    }
    textarea {
      min-height: 92px;
      resize: vertical;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    button {
      width: 100%;
      margin-top: 12px;
      border: 0;
      border-radius: 6px;
      background: #d8b45f;
      color: #151515;
      padding: 9px 11px;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.6;
      cursor: wait;
    }
    .secondary-button {
      background: #7fa7c9;
    }
    .control-frame button {
      min-height: 26px;
      margin-top: 6px;
      padding: 5px 7px;
      font-size: 12px;
      line-height: 1.2;
    }
    .control-frame button.is-selected {
      background: #d8b45f;
      color: #151515;
    }
    .form-section {
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1px solid #373b44;
    }
    .form-section h2,
    .form-section summary {
      margin: 0 0 10px;
      color: #f4f1ea;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .form-section summary {
      cursor: pointer;
    }
    .form-section[open] summary {
      margin-bottom: 4px;
    }
    .wildcard-preview {
      margin: 12px 0 0;
      min-height: 84px;
      max-height: 220px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #111319;
      color: #d8d2c2;
      padding: 10px;
      font: 12px/1.45 Consolas, "Courier New", monospace;
    }
    .wildcard-preview strong {
      color: #f4d27b;
    }
    .prompt-tools-block {
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid #373b44;
    }
    .prompt-tools-block h2 {
      margin-top: 0;
    }
    .prompt-tools-block .row {
      grid-template-columns: minmax(0, 1fr) 64px;
    }
    .prompt-tools-block .llm-row {
      grid-template-columns: minmax(0, 1fr) 82px;
    }
    .autocomplete-menu {
      position: fixed;
      z-index: 50;
      width: min(420px, calc(100vw - 24px));
      max-height: 260px;
      overflow: auto;
      border: 1px solid #4b5361;
      border-radius: 6px;
      background: #111319;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.42);
      padding: 4px;
    }
    .autocomplete-menu[hidden] {
      display: none;
    }
    .autocomplete-item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      width: 100%;
      margin: 0;
      padding: 6px 8px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: #f4f1ea;
      text-align: left;
      font-size: 12px;
      line-height: 1.25;
    }
    .autocomplete-item:hover,
    .autocomplete-item.active {
      background: #2d3543;
      color: #f4d27b;
    }
    .autocomplete-item-count {
      color: #9da7b7;
      font-variant-numeric: tabular-nums;
    }
    .toggle-switch {
      position: relative;
      display: grid;
      grid-template-columns: auto 1fr;
      align-items: center;
      gap: 8px;
      min-height: 42px;
      margin-top: 10px;
      padding: 8px;
      border: 1px solid #7e343d;
      border-radius: 6px;
      background: #2a171c;
      color: #f4f1ea;
      cursor: pointer;
      transition: background 120ms ease, border-color 120ms ease;
    }
    .toggle-switch:has(input:checked) {
      border-color: #53c978;
      background: #15291c;
    }
    .toggle-switch input {
      position: absolute;
      width: 1px;
      height: 1px;
      margin: 0;
      opacity: 0;
      pointer-events: none;
    }
    .toggle-track {
      position: relative;
      width: 48px;
      height: 26px;
      border-radius: 999px;
      background: #a9444f;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
      transition: background 120ms ease;
    }
    .toggle-track::after {
      content: "";
      position: absolute;
      top: 3px;
      left: 3px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: #f4f1ea;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
      transition: transform 120ms ease;
    }
    .toggle-switch input:focus-visible + .toggle-track {
      outline: 2px solid #f4d27b;
      outline-offset: 3px;
    }
    .toggle-switch:has(input:checked) .toggle-track {
      background: #2f9f55;
    }
    .toggle-switch:has(input:checked) .toggle-track::after {
      transform: translateX(22px);
    }
    .toggle-copy {
      display: grid;
      gap: 2px;
      min-width: 0;
    }
    .toggle-title {
      font-size: 13px;
      font-weight: 700;
      line-height: 1.25;
    }
    .toggle-state {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: #ffb8bd;
    }
    .toggle-state::before {
      content: "OFF";
    }
    .toggle-switch:has(input:checked) .toggle-state {
      color: #92e6aa;
    }
    .toggle-switch:has(input:checked) .toggle-state::before {
      content: "ON";
    }
    .primary-action {
      margin-top: 18px;
    }
    .auto-queue-panel {
      margin-top: 12px;
      padding: 12px;
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #171b22;
    }
    .auto-queue-panel h2 {
      margin: 0 0 10px;
      font-size: 15px;
      letter-spacing: 0;
    }
    .queue-actions {
      display: flex;
      gap: 8px;
      margin-top: 10px;
      flex-wrap: wrap;
    }
    .queue-status {
      min-height: 20px;
      margin: 10px 0 0;
      color: #b9c2d0;
      font-size: 13px;
      word-break: break-word;
    }
    .lora-list {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .lora-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 84px auto;
      gap: 8px;
      align-items: end;
    }
    .lora-row button {
      min-height: 34px;
      padding: 7px 9px;
    }
    .preset-strip {
      margin: 10px 0;
      padding: 8px;
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #171b22;
    }
    .preset-strip .row {
      margin-top: 0;
    }
    .starting-point-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
    }
    .orientation-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
    }
    .control-groups {
      display: grid;
      gap: 8px;
    }
    .control-group {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #1b1f27;
      overflow: hidden;
    }
    .control-group > summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 9px 10px;
      color: #f4f1ea;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      list-style: none;
    }
    .control-group > summary::-webkit-details-marker {
      display: none;
    }
    .control-group > summary::after {
      content: "+";
      color: #d8b45f;
      font-size: 16px;
      line-height: 1;
    }
    .control-group[open] > summary::after {
      content: "-";
    }
    .control-group-body {
      padding: 0 10px 10px;
      border-top: 1px solid #373b44;
    }
    .control-group .form-section:first-child {
      margin-top: 0;
      padding-top: 0;
      border-top: 0;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #111319;
      border: 1px solid #373b44;
      border-radius: 6px;
      padding: 16px;
      min-height: 160px;
    }
    .result-panel {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #151821;
      padding: 14px;
      margin-bottom: 0;
      min-height: 0;
    }
    .result-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .result-header h2 {
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
    }
    .result-header span {
      color: #b9c2d0;
      font-size: 12px;
    }
    .result-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
      gap: 6px;
      margin-bottom: 10px;
    }
    .summary-item {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #111319;
      padding: 8px;
    }
    .summary-item strong {
      display: block;
      color: #b9c2d0;
      font-size: 12px;
      margin-bottom: 4px;
    }
    .summary-item span {
      display: block;
      color: #f4f1ea;
      font-size: 14px;
      word-break: break-word;
    }
    .result-actions {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
      margin-top: 12px;
    }
    .result-actions a {
      box-sizing: border-box;
      display: block;
      width: 100%;
      margin-top: 18px;
      border-radius: 6px;
      background: #7fa7c9;
      color: #151515;
      padding: 11px 14px;
      text-align: center;
      text-decoration: none;
      font-weight: 700;
    }
    .sam3-tools {
      display: grid;
      gap: 8px;
      margin-top: 12px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #151a22;
    }
    .sam3-tools .row {
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: end;
    }
    .sam3-status {
      color: #b9c2d0;
      font-size: 12px;
    }
    .sam3-presets,
    .sam3-results {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .sam3-preset,
    .sam3-result {
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #11161f;
      color: #f4f1ea;
      padding: 6px 8px;
      font-size: 12px;
      cursor: pointer;
    }
    .sam3-result[data-has-mask="true"] {
      border-color: #7ccf91;
    }
    #output-link[hidden] {
      display: none;
    }
    .compare-toolbar {
      display: flex;
      justify-content: flex-end;
      margin: 8px 0 10px;
    }
    .compare-toolbar[hidden] {
      display: none;
    }
    .compare-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin: 0 0 12px;
    }
    .compare-grid[hidden] {
      display: none;
    }
    .compare-cell {
      min-width: 0;
    }
    .compare-cell strong {
      display: block;
      color: #d8d2c2;
      font-size: 12px;
      margin-bottom: 6px;
    }
    .compare-cell img {
      width: 100%;
      max-height: 46vh;
      object-fit: contain;
      background: #0f1117;
    }
    .compare-empty {
      min-height: 120px;
      display: grid;
      place-items: center;
      border: 1px dashed #48505d;
      border-radius: 6px;
      color: #8f98a8;
      font-size: 12px;
    }
    .result-json summary {
      cursor: pointer;
      color: #d8d2c2;
      font-size: 13px;
      font-weight: 700;
      margin: 12px 0 8px;
    }
    img {
      max-width: 100%;
      height: auto;
      border-radius: 6px;
      border: 1px solid #373b44;
    }
    #preview {
      display: block;
      max-height: 72vh;
      margin: 0 auto;
      object-fit: contain;
    }
    #preview[hidden] {
      display: none;
    }
    .history-panel {
      margin-top: 0;
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #151821;
      padding: 14px;
    }
    .history-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 10px;
    }
    .history-header h2 {
      margin: 0;
      font-size: 17px;
    }
    .history-header span {
      color: #b9c2d0;
      font-size: 12px;
    }
    .history-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    .history-filter {
      margin-top: 0;
      border: 1px solid #3f4652;
      background: #10131a;
      color: #d9deea;
      padding: 8px 10px;
      font-size: 12px;
    }
    .history-filter.active {
      border-color: #d8b45f;
      color: #151515;
      background: #d8b45f;
    }
    .history {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .status-panel {
      display: grid;
      gap: 8px;
      margin-bottom: 18px;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    }
    .side-status-panel {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #151821;
      margin-bottom: 12px;
      overflow: hidden;
    }
    .side-status-panel > summary {
      cursor: pointer;
      color: #f4f1ea;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0;
      padding: 10px 12px;
    }
    .side-status-panel[open] {
      padding-bottom: 10px;
    }
    .side-status-panel .status-panel.compact,
    .side-status-panel .readiness-panel.compact {
      padding: 0 10px;
    }
    .side-status-panel .update-panel {
      align-items: center;
      border: 1px solid #373b44;
      border-radius: 6px;
      display: grid;
      gap: 8px;
      grid-template-columns: minmax(0, 1fr) auto auto;
      margin: 8px 10px 0;
      padding: 8px;
    }
    .update-panel strong {
      display: block;
      font-size: 12px;
      color: #c0c5d6;
    }
    .update-panel span {
      color: #f4f1ea;
      overflow-wrap: anywhere;
    }
    .status-panel.compact,
    .readiness-panel.compact {
      margin-bottom: 0;
    }
    .status-panel.compact {
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    }
    .status-panel.compact .status-item,
    .readiness-panel.compact .readiness-card {
      padding: 8px;
    }
    .readiness-panel.compact {
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 8px;
      margin-top: 8px;
    }
    .readiness-panel.compact .readiness-files {
      display: none;
    }
    .readiness-panel.compact .readiness-action {
      min-height: 30px;
      padding: 7px 9px;
      font-size: 12px;
    }
    .status-item {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #151821;
      padding: 10px;
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .status-item strong {
      display: block;
      font-size: 12px;
      color: #b9c2d0;
      margin-bottom: 4px;
    }
    .readiness-panel {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }
    .readiness-card {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #151821;
      padding: 12px;
      display: grid;
      gap: 8px;
    }
    .readiness-card[data-ready="true"] {
      border-color: #4d805a;
    }
    .readiness-card[data-ready="false"] {
      border-color: #816539;
    }
    .readiness-card strong {
      font-size: 14px;
    }
    .readiness-card span {
      color: #b9c2d0;
      font-size: 12px;
    }
    .readiness-files {
      margin: 0;
      padding-left: 18px;
      color: #b9c2d0;
      font-size: 12px;
    }
    .readiness-action {
      margin-top: 0;
    }
    .generation-stages {
      position: sticky;
      top: 12px;
      z-index: 2;
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #151821;
      padding: 14px;
      margin-bottom: 18px;
    }
    .generation-stages.compact {
      top: 8px;
      padding: 10px;
      margin-bottom: 0;
    }
    .generation-stages.compact .stage-list {
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }
    .stage-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .stage-header strong {
      font-size: 14px;
    }
    .stage-header span {
      color: #b9c2d0;
      font-size: 12px;
    }
    .stage-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 8px;
    }
    .stage-item {
      display: grid;
      grid-template-columns: 18px 1fr auto;
      align-items: center;
      gap: 10px;
      color: #b9c2d0;
      font-size: 13px;
    }
    .stage-marker {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      border: 1px solid #626b7a;
      background: #22252b;
    }
    .stage-item[data-state="active"] {
      color: #f4f1ea;
    }
    .stage-item[data-state="active"] .stage-marker {
      border-color: #d8b45f;
      background: #d8b45f;
      animation: stage-pulse 1s ease-in-out infinite;
    }
    .stage-item[data-state="completed"] .stage-marker {
      border-color: #79c58d;
      background: #79c58d;
    }
    .stage-item[data-state="skipped"] {
      opacity: 0.68;
    }
    .stage-item[data-state="failed"] {
      color: #ffb2a6;
    }
    .stage-item[data-state="failed"] .stage-marker {
      border-color: #ff8b7b;
      background: #ff8b7b;
    }
    .stage-state {
      font-size: 12px;
      color: #b9c2d0;
    }
    .stage-state:empty {
      display: none;
    }
    @keyframes stage-pulse {
      0% {
        transform: scale(1);
        opacity: 1;
      }
      50% {
        transform: scale(1.35);
        opacity: 0.62;
      }
      100% {
        transform: scale(1);
        opacity: 1;
      }
    }
    .history-item {
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #10131a;
      padding: 0;
      overflow: hidden;
      cursor: pointer;
    }
    .history-item:focus-visible {
      outline: 2px solid #d8b45f;
      outline-offset: 2px;
    }
    .history-thumb {
      display: block;
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      border: 0;
      border-radius: 0;
      background: #0b0d12;
    }
    .history-thumb-empty {
      display: grid;
      place-items: center;
      color: #b9c2d0;
      font-size: 12px;
      border-bottom: 1px solid #2b3039;
    }
    .history-card-body {
      display: grid;
      gap: 6px;
      padding: 10px;
    }
    .history-item strong {
      display: block;
      font-size: 14px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    .history-item span {
      color: #b9c2d0;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .history-type {
      color: #d8b45f;
      font-weight: 700;
    }
    .history-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      padding: 0 10px 10px;
    }
    .history-action {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 32px;
      margin: 0;
      border: 1px solid #3f4652;
      border-radius: 6px;
      background: #151821;
      color: #d9deea;
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }
    .history-action:hover {
      border-color: #d8b45f;
    }
    .history-action.danger {
      border-color: #7c4147;
      color: #ffb2a6;
      background: #271418;
    }
    .history-empty {
      grid-column: 1 / -1;
      color: #b9c2d0;
      border: 1px dashed #3f4652;
      border-radius: 6px;
      padding: 14px;
      text-align: center;
      font-size: 13px;
    }
    @media (max-width: 1180px) {
      .app-shell {
        grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      }
      .history-frame {
        grid-column: 1 / -1;
        height: auto;
        max-height: 42vh;
        border-left: 0;
        border-top: 1px solid #373b44;
      }
      .history {
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      }
    }
    @media (max-width: 780px) {
      body {
        overflow: auto;
      }
      .app-shell {
        min-height: 100vh;
        display: block;
      }
      .control-frame,
      .workspace-frame,
      .history-frame {
        height: auto;
        max-height: none;
        overflow: visible;
        border-left: 0;
        border-right: 0;
        border-bottom: 1px solid #373b44;
      }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="control-frame" aria-label="생성 컨트롤">
      <h1>Anima APP</h1>
      <form id="generate-form"></form>
      <div id="control-groups" class="control-groups">
        <details class="control-group" data-control-group="prompt-generate" open>
          <summary>프롬프트와 생성</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>프롬프트</h2>
              <label for="prompt">프롬프트</label>
              <textarea id="prompt" name="prompt" form="generate-form" required>anime portrait, clean lineart</textarea>
              <label for="negative">네거티브</label>
              <input id="negative" name="negative_prompt" value="low quality" form="generate-form">
              <div class="prompt-tools-block" aria-label="프롬프트 와일드카드와 프리셋">
                <h2>와일드카드와 프리셋</h2>
                <label for="wildcard-mode">와일드카드 방식</label>
                <select id="wildcard-mode" name="wildcard_mode" form="generate-form">
                  <option value="random" selected>랜덤</option>
                  <option value="sequential">순차</option>
                  <option value="reverse">역순</option>
                </select>
                <label for="wildcard-select">와일드카드 삽입</label>
                <div class="row">
                  <select id="wildcard-select">
                    <option value="">와일드카드 파일 없음</option>
                  </select>
                  <button type="button" id="insert-wildcard" class="secondary-button">삽입</button>
                </div>
                <label for="preset-wildcard-select">프리셋 삽입</label>
                <div class="row">
                  <select id="preset-wildcard-select">
                    <option value="">프롬프트 프리셋 없음</option>
                  </select>
                  <button type="button" id="insert-preset-wildcard" class="secondary-button">삽입</button>
                </div>
                <button type="button" id="preview-wildcards" class="secondary-button">확장 미리보기</button>
                <label for="llm-refine-priority">LLM 정리 기준</label>
                <div class="row llm-row">
                  <select id="llm-refine-priority">
                    <option value="tag" selected>태그 우선</option>
                    <option value="natural">자연어 우선</option>
                  </select>
                  <button type="button" id="llm-refine-prompt" class="secondary-button">보정</button>
                </div>
                <p id="llm-prompt-status" class="queue-status" aria-live="polite"></p>
                <pre id="wildcard-preview" class="wildcard-preview" hidden></pre>
              </div>
            </section>
            <section class="preset-strip" aria-label="시작 설정 프리셋">
              <h2>시작 설정</h2>
              <label>크기</label>
              <div class="starting-point-grid" role="group" aria-label="시작 크기">
                <button type="button" id="starting-square" class="secondary-button" data-size-preset="square">1024x1024</button>
                <button type="button" id="starting-portrait-2x3" class="secondary-button" data-size-preset="portrait_2x3">832x1216</button>
                <button type="button" id="starting-portrait-3x4" class="secondary-button" data-size-preset="portrait_3x4">896x1152</button>
              </div>
              <label>방향</label>
              <div class="orientation-grid" role="group" aria-label="시작 방향">
                <button type="button" id="orientation-portrait" class="secondary-button" data-orientation="portrait">세로</button>
                <button type="button" id="orientation-landscape" class="secondary-button" data-orientation="landscape">가로</button>
              </div>
            </section>
            <section class="form-section">
              <h2>생성</h2>
              <button id="generate-button" class="primary-action" type="submit" form="generate-form">생성하기</button>
              <section class="auto-queue-panel" id="auto-queue-panel" aria-label="자동 큐">
                <h2>자동 큐</h2>
                <div class="row">
                  <div>
                    <label for="queue-count">큐 횟수</label>
                    <input id="queue-count" name="queue_count" type="number" min="1" max="99" value="4">
                  </div>
                  <div>
                    <label for="queue-seed-mode">시드 방식</label>
                    <select id="queue-seed-mode" name="queue_seed_mode">
                      <option value="fixed">고정</option>
                      <option value="increment" selected>증가</option>
                      <option value="random">랜덤</option>
                    </select>
                  </div>
                </div>
                <label class="toggle-switch" for="queue-infinite">
                  <input id="queue-infinite" name="queue_infinite" type="checkbox" value="1">
                  <span class="toggle-track" aria-hidden="true"></span>
                  <span class="toggle-copy">
                    <span class="toggle-title">무한 모드</span>
                    <span class="toggle-state" aria-hidden="true"></span>
                  </span>
                </label>
                <label for="queue-delay">지연(초)</label>
                <input id="queue-delay" name="queue_delay" type="number" min="0" max="60" step="0.5" value="0">
                <div class="queue-actions">
                  <button type="button" id="start-queue" class="secondary-button">큐 시작</button>
                  <button type="button" id="stop-queue" class="secondary-button" disabled>정지</button>
                </div>
                <p id="queue-status" class="queue-status" aria-live="polite">대기</p>
              </section>
            </section>
          </div>
        </details>
        <details class="control-group" data-control-group="model-style" open>
          <summary>모델과 스타일</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>LoRA 스타일</h2>
              <label for="checkpoint-select">체크포인트</label>
              <select id="checkpoint-select" name="checkpoint" form="generate-form">
                <option value="">불러오는 중...</option>
              </select>
              <label>LoRA 스택</label>
              <div id="lora-list" class="lora-list" aria-label="LoRA 스택">
              </div>
              <button type="button" id="add-lora" class="secondary-button">LoRA 추가</button>
            </section>
            <form id="lora-import-form" class="form-section">
              <h2>LoRA 가져오기</h2>
              <label for="lora-path">LoRA 파일 가져오기</label>
              <input id="lora-path" name="path" placeholder="path\\to\\style.safetensors">
              <button type="submit" class="secondary-button">앱으로 LoRA 복사</button>
            </form>
          </div>
        </details>
        <details class="control-group" data-control-group="image-settings" open>
          <summary>이미지 설정</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>이미지 설정</h2>
              <div class="row">
                <div>
                  <label for="width">너비</label>
                  <input id="width" name="width" type="number" min="8" step="8" value="__DEFAULT_T2I_WIDTH__" form="generate-form">
                </div>
                <div>
                  <label for="height">높이</label>
                  <input id="height" name="height" type="number" min="8" step="8" value="__DEFAULT_T2I_HEIGHT__" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="steps">스텝</label>
                  <input id="steps" name="steps" type="number" min="1" value="__DEFAULT_T2I_STEPS__" form="generate-form">
                </div>
                <div>
                  <label for="cfg">CFG</label>
                  <input id="cfg" name="cfg" type="number" min="0" step="0.1" value="__DEFAULT_T2I_CFG__" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="sampler">샘플러</label>
                  <select id="sampler" name="sampler" form="generate-form">
                    <option value="euler_ancestral_cfg_pp" selected>Euler Ancestral CFG++</option>
                  </select>
                </div>
                <div>
                  <label for="scheduler">스케줄러</label>
                  <select id="scheduler" name="scheduler" form="generate-form">
                    <option value="sgm_uniform" selected>SGM Uniform</option>
                    <option value="normal">Normal</option>
                    <option value="simple">Simple</option>
                    <option value="karras">Karras</option>
                  </select>
                </div>
              </div>
              <label for="seed">시드</label>
              <input id="seed" name="seed" type="number" placeholder="랜덤" form="generate-form">
              <div class="row">
                <div>
                  <label for="memory-profile">VRAM 프로필</label>
                  <select id="memory-profile" name="memory_profile" form="generate-form">
                    <option value="auto" selected>자동</option>
                    <option value="balanced">균형</option>
                    <option value="low_vram_highres">저VRAM 고해상도</option>
                  </select>
                </div>
                <div>
                  <label>&nbsp;</label>
                  <button type="button" id="low-vram-highres-preset" class="secondary-button">저VRAM 고해상도</button>
                </div>
              </div>
            </section>
          </div>
        </details>
        <details class="control-group" data-control-group="enhance">
          <summary>보정</summary>
          <div class="control-group-body">
            <details id="reference-image-section" class="form-section">
              <summary>참조 이미지와 업스케일</summary>
              <label for="i2i-image">참조 이미지 경로</label>
              <input id="i2i-image" name="i2i_image" placeholder="inputs\\reference.png" form="generate-form">
              <div class="row">
                <label class="toggle-switch" for="upscale-enabled">
                  <input id="upscale-enabled" name="upscale_enabled" type="checkbox" value="1" form="generate-form">
                  <span class="toggle-track" aria-hidden="true"></span>
                  <span class="toggle-copy">
                    <span class="toggle-title">업스케일 사용</span>
                    <span class="toggle-state" aria-hidden="true"></span>
                  </span>
                </label>
                <label class="toggle-switch" for="upscale-tiled">
                  <input id="upscale-tiled" name="upscale_tiled" type="checkbox" value="1" form="generate-form">
                  <span class="toggle-track" aria-hidden="true"></span>
                  <span class="toggle-copy">
                    <span class="toggle-title">타일 업스케일</span>
                    <span class="toggle-state" aria-hidden="true"></span>
                  </span>
                </label>
              </div>
              <div class="row">
                <div>
                  <label for="i2i-denoise">이미지 디노이즈</label>
                  <input id="i2i-denoise" name="i2i_denoise" type="number" min="0" max="1" step="0.05" value="0.35" form="generate-form">
                </div>
                <div>
                  <label for="upscale-scale">업스케일 배율</label>
                  <input id="upscale-scale" name="upscale_scale" type="number" min="0.1" step="0.1" value="1.5" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="upscale-steps">업스케일 스텝</label>
                  <input id="upscale-steps" name="upscale_steps" type="number" min="1" value="10" form="generate-form">
                </div>
                <div>
                  <label for="upscale-denoise">업스케일 디노이즈</label>
                  <input id="upscale-denoise" name="upscale_denoise" type="number" min="0" max="1" step="0.01" value="0.35" form="generate-form">
                </div>
              </div>
              <label for="upscale-method">업스케일 방식</label>
              <select id="upscale-method" name="upscale_method" form="generate-form">
                <option value="bicubic">바이큐빅</option>
                <option value="bilinear">바이리니어</option>
                <option value="nearest-exact">Nearest Exact</option>
                <option value="area">Area</option>
              </select>
              <div class="row">
                <div>
                  <label for="upscale-tile-size">업스케일 타일</label>
                  <input id="upscale-tile-size" name="upscale_tile_size" type="number" min="1" value="128" form="generate-form">
                </div>
                <div>
                  <label for="upscale-overlap">업스케일 겹침</label>
                  <input id="upscale-overlap" name="upscale_overlap" type="number" min="0" value="8" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="vae-decode-mode">VAE 디코드</label>
                  <select id="vae-decode-mode" name="vae_decode_mode" form="generate-form">
                    <option value="auto">자동</option>
                    <option value="tiled">타일</option>
                    <option value="standard">표준</option>
                  </select>
                </div>
                <div>
                  <label for="vae-tile-size">VAE 타일</label>
                  <input id="vae-tile-size" name="vae_tile_size" type="number" min="1" value="128" form="generate-form">
                </div>
              </div>
              <label for="vae-overlap">VAE 겹침</label>
              <input id="vae-overlap" name="vae_overlap" type="number" min="0" value="8" form="generate-form">
            </details>
            <details id="face-detailer-section" class="form-section">
              <summary>페이스 디테일러</summary>
              <label class="toggle-switch" for="face-detailer-enabled">
                <input id="face-detailer-enabled" name="face_detailer_enabled" type="checkbox" value="1" form="generate-form">
                <span class="toggle-track" aria-hidden="true"></span>
                <span class="toggle-copy">
                  <span class="toggle-title">페이스 디테일러 사용</span>
                  <span class="toggle-state" aria-hidden="true"></span>
                </span>
              </label>
              <label for="face-detector">얼굴 감지 모델</label>
              <input id="face-detector" name="face_detector" value="default" form="generate-form">
              <label for="face-mask-backend">마스크 방식</label>
              <select id="face-mask-backend" name="face_mask_backend" form="generate-form">
                <option value="sam_b">SAM-B</option>
                <option value="sam3">SAM3</option>
              </select>
              <div id="sam3-detailer-controls" hidden>
                <label>SAM3 보정 부위</label>
                <div class="row" id="sam3-detailer-targets">
                  <label class="toggle-switch" for="face-sam3-face-eyes">
                    <input id="face-sam3-face-eyes" name="face_sam3_face_eyes" type="checkbox" value="1" form="generate-form" checked>
                    <span class="toggle-track" aria-hidden="true"></span>
                    <span class="toggle-copy">
                      <span class="toggle-title">얼굴 + 눈</span>
                      <span class="toggle-state" aria-hidden="true"></span>
                    </span>
                  </label>
                  <label class="toggle-switch" for="face-sam3-hands">
                    <input id="face-sam3-hands" name="face_sam3_hands" type="checkbox" value="1" form="generate-form">
                    <span class="toggle-track" aria-hidden="true"></span>
                    <span class="toggle-copy">
                      <span class="toggle-title">손</span>
                      <span class="toggle-state" aria-hidden="true"></span>
                    </span>
                  </label>
                </div>
                <label for="hand-denoise">손 디노이즈</label>
                <input id="hand-denoise" name="hand_denoise" type="number" min="0" max="1" step="0.01" value="0.35" form="generate-form">
              </div>
              <div class="row">
                <div>
                  <label for="face-threshold">얼굴 임계값</label>
                  <input id="face-threshold" name="face_threshold" type="number" min="0" max="1" step="0.01" value="0.5" form="generate-form">
                </div>
                <div>
                  <label for="face-denoise">얼굴 디노이즈</label>
                  <input id="face-denoise" name="face_denoise" type="number" min="0" max="1" step="0.01" value="0.28" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="face-steps">얼굴 스텝</label>
                  <input id="face-steps" name="face_steps" type="number" min="1" value="10" form="generate-form">
                </div>
                <div>
                  <label for="face-crop-scale">얼굴 크롭</label>
                  <input id="face-crop-scale" name="face_crop_scale" type="number" min="0.1" step="0.05" value="1.5" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="face-padding">얼굴 패딩</label>
                  <input id="face-padding" name="face_padding" type="number" min="0" value="32" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="face-feather">얼굴 페더</label>
                  <input id="face-feather" name="face_feather" type="number" min="0" value="24" form="generate-form">
                </div>
                <div>
                  <label for="face-exclude-forehead">이마 제외</label>
                  <input id="face-exclude-forehead" name="face_exclude_forehead" type="number" min="0" max="0.75" step="0.01" value="0" form="generate-form">
                </div>
              </div>
            </details>
          </div>
        </details>
        <details class="control-group" data-control-group="settings">
          <summary>설정</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>저장된 설정</h2>
              <label for="preset-name">설정 이름</label>
              <input id="preset-name" placeholder="세로 초안">
              <label for="preset-select">저장된 설정</label>
              <select id="preset-select">
                <option value="">저장된 프리셋 없음</option>
              </select>
              <div class="row">
                <button type="button" id="save-preset" class="secondary-button">설정 저장</button>
                <button type="button" id="apply-preset" class="secondary-button">설정 불러오기</button>
              </div>
              <input id="preset-import-file" type="file" accept="application/json,.json" hidden>
              <div class="row">
                <button type="button" id="export-presets" class="secondary-button">설정 내보내기</button>
                <button type="button" id="import-presets" class="secondary-button">설정 가져오기</button>
              </div>
            </section>
          </div>
        </details>
      </div>
    </aside>
    <main class="workspace-frame" aria-label="이미지 작업 영역">
      <section class="generation-stages compact" id="generation-stages" aria-live="polite" aria-busy="false" hidden>
        <div class="stage-header">
          <strong>생성 진행</strong>
          <span id="generation-stage-summary">대기</span>
        </div>
        <ol class="stage-list" id="generation-stage-list"></ol>
      </section>
      <section class="result-panel" aria-label="현재 결과">
        <div class="result-header">
          <h2 id="result-title">현재 결과</h2>
          <span id="result-status">준비됨</span>
        </div>
        <div id="result-summary" class="result-summary"></div>
        <div id="compare-toolbar" class="compare-toolbar" hidden>
          <button type="button" id="toggle-compare" class="secondary-button" hidden>단계 비교</button>
        </div>
        <section id="compare-grid" class="compare-grid" aria-label="생성 단계 비교" hidden></section>
        <img id="preview" alt="" hidden>
        <div class="result-actions">
          <a id="output-link" href="" hidden>출력 열기</a>
          <button type="button" id="apply-manifest" class="secondary-button">이 결과 설정 불러오기</button>
        </div>
        <section class="sam3-tools" id="sam3-tools">
          <label for="sam3-prompt">SAM3 마스크</label>
          <div class="row">
            <input id="sam3-prompt" value="clothes" placeholder="clothes, dress, hair, eyes">
            <button type="button" id="sam3-segment" class="secondary-button">마스크 생성</button>
          </div>
          <div class="sam3-presets" id="sam3-presets" aria-label="SAM3 프롬프트 후보"></div>
          <button type="button" id="sam3-compare" class="secondary-button">옷 후보 비교</button>
          <div class="sam3-results" id="sam3-results" aria-label="SAM3 비교 결과"></div>
          <div class="row">
            <div>
              <label for="mask-dilation">마스크 확장</label>
              <input id="mask-dilation" type="number" min="0" max="128" step="1" value="16">
            </div>
            <div>
              <label for="mask-feather">경계 부드럽게</label>
              <input id="mask-feather" type="number" min="0" max="64" step="1" value="8">
            </div>
          </div>
          <button type="button" id="mask-adjust" class="secondary-button">마스크 조정</button>
          <label for="inpaint-prompt">바꿀 내용</label>
          <textarea id="inpaint-prompt" rows="2" placeholder="pastel yellow sundress, light floral pattern, thin shoulder straps"></textarea>
          <label for="inpaint-negative">피할 내용</label>
          <input id="inpaint-negative" value="low quality, bad anatomy, changed face, changed hair, gray blob">
          <div class="row">
            <div>
              <label for="inpaint-method">인페인트 방식</label>
              <select id="inpaint-method">
                <option value="noise_mask">Noise mask</option>
                <option value="vae_inpaint">VAE inpaint</option>
                <option value="crop_i2i_composite">Crop i2i</option>
              </select>
            </div>
            <div>
              <label for="inpaint-denoise">디노이즈</label>
              <input id="inpaint-denoise" type="number" min="0" max="1" step="0.01" value="0.65">
            </div>
          </div>
          <div class="row">
            <div>
              <label for="inpaint-steps">스텝</label>
              <input id="inpaint-steps" type="number" min="1" max="100" step="1" value="20">
            </div>
            <div>
              <label for="inpaint-cfg">CFG</label>
              <input id="inpaint-cfg" type="number" min="0" max="20" step="0.1" value="3.5">
            </div>
          </div>
          <div class="row">
            <input id="inpaint-seed" placeholder="시드 비우면 랜덤">
            <button type="button" id="masked-inpaint" class="secondary-button">인페인트</button>
          </div>
          <span id="sam3-status" class="sam3-status">결과 이미지를 선택하면 마스크를 만들 수 있습니다.</span>
        </section>
        <details class="result-json">
          <summary>상세 생성 정보</summary>
          <pre id="result">준비됨.</pre>
        </details>
      </section>
    </main>
    <div id="autocomplete-menu" class="autocomplete-menu" role="listbox" hidden></div>
    <aside class="history-frame" aria-label="생성 히스토리">
      <details class="side-status-panel" id="side-status-panel">
        <summary>런타임 상태</summary>
        <section class="status-panel compact" id="status-panel" aria-label="런타임 상태"></section>
        <section class="update-panel" id="update-panel" aria-label="업데이트 상태">
          <div>
            <strong>업데이트</strong>
            <span id="update-status">확인 전</span>
          </div>
          <button type="button" id="check-update" class="secondary-button">업데이트 확인</button>
          <a id="update-link" class="secondary-button" href="https://github.com/raspie10032/anima-app" target="_blank" rel="noreferrer">GitHub</a>
        </section>
        <section class="readiness-panel compact" id="readiness-panel" aria-label="모델 준비 상태"></section>
      </details>
      <h2 class="frame-title">히스토리</h2>
      <section class="history-panel" aria-label="최근 생성">
        <div class="history-header">
          <h2>최근</h2>
          <span id="history-count">결과 0개</span>
        </div>
        <div class="history-tabs" role="group" aria-label="히스토리 필터">
          <button type="button" class="history-filter active" data-history-filter="all">전체</button>
          <button type="button" class="history-filter" data-history-filter="images">이미지</button>
          <button type="button" class="history-filter" data-history-filter="dry-run">드라이런</button>
        </div>
        <section class="history" id="history" aria-label="히스토리 카드"></section>
      </section>
    </aside>
  </div>
  <script id="anima-defaults" type="application/json">{"width": __DEFAULT_T2I_WIDTH__, "height": __DEFAULT_T2I_HEIGHT__, "steps": __DEFAULT_T2I_STEPS__, "cfg": __DEFAULT_T2I_CFG__, "sampler": "__DEFAULT_T2I_SAMPLER__", "scheduler": "__DEFAULT_T2I_SCHEDULER__", "checkpoint": "__DEFAULT_T2I_CHECKPOINT__"}</script>
  <script src="/app.js"></script>
</body>
</html>
"""


INDEX_HTML = (
    _INDEX_HTML_TEMPLATE.replace("__DEFAULT_T2I_WIDTH__", str(DEFAULT_T2I_WIDTH))
    .replace("__DEFAULT_T2I_HEIGHT__", str(DEFAULT_T2I_HEIGHT))
    .replace("__DEFAULT_T2I_STEPS__", str(DEFAULT_T2I_STEPS))
    .replace("__DEFAULT_T2I_CFG__", str(DEFAULT_T2I_CFG))
    .replace("__DEFAULT_T2I_SAMPLER__", DEFAULT_T2I_SAMPLER)
    .replace("__DEFAULT_T2I_SCHEDULER__", DEFAULT_T2I_SCHEDULER)
    .replace("__DEFAULT_T2I_CHECKPOINT__", DEFAULT_T2I_CHECKPOINT)
)
APP_JS = (Path(__file__).with_name("static") / "app.js").read_text(encoding="utf-8")


_PROGRESS_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_PROGRESS_STAGE_LABELS = {
    "request": "요청",
    "wildcards": "프롬프트 / 와일드카드",
    "text_encode": "텍스트 인코드",
    "base_t2i": "기본 렌더",
    "high_res_fix": "고해상도 / 업스케일",
    "vae_decode": "VAE 디코드",
    "face_detailer": "페이스 디테일러",
    "face_eye_detailer": "얼굴 + 눈 보정",
    "hand_detailer": "손 보정",
    "metadata": "메타데이터 저장",
}
_PROGRESS_STAGE_ORDER = tuple(_PROGRESS_STAGE_LABELS)


class ProgressStore:
    def __init__(self, *, max_entries: int = 64) -> None:
        self._max_entries = max_entries
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, progress_id: str, payload: dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            self._items[progress_id] = {
                "progress_id": progress_id,
                "status": "running",
                "summary": "시작 중",
                "stages": _initial_progress_stages(payload),
                "result": None,
                "error": "",
                "created_at": now,
                "updated_at": now,
            }
            self._prune_locked()

    def update_stage(self, progress_id: str, key: str, status: str, **details: Any) -> None:
        with self._lock:
            item = self._items.get(progress_id)
            if item is None:
                return
            stage = item["stages"].setdefault(key, {"label": _PROGRESS_STAGE_LABELS.get(key, key)})
            stage.update({"status": status, **details})
            item["updated_at"] = time.time()

    def update_summary(self, progress_id: str, summary: str) -> None:
        with self._lock:
            item = self._items.get(progress_id)
            if item is None:
                return
            item["summary"] = summary
            item["updated_at"] = time.time()

    def complete(self, progress_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            item = self._items.get(progress_id)
            if item is None:
                return
            item["status"] = "completed"
            item["summary"] = "완료"
            item["result"] = copy.deepcopy(result)
            item["stages"] = _completed_progress_stages(item["stages"], result.get("stages", {}))
            item["updated_at"] = time.time()

    def fail(self, progress_id: str, error: str) -> None:
        with self._lock:
            item = self._items.get(progress_id)
            if item is None:
                return
            item["status"] = "failed"
            item["summary"] = f"실패: {error}"
            item["error"] = error
            for key, stage in item["stages"].items():
                if stage.get("status") in {"active", "pending"}:
                    stage["status"] = "failed" if key != "metadata" else "skipped"
            item["updated_at"] = time.time()

    def get(self, progress_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(progress_id)
            return copy.deepcopy(item) if item is not None else None

    def _prune_locked(self) -> None:
        if len(self._items) <= self._max_entries:
            return
        oldest = sorted(self._items.items(), key=lambda pair: pair[1].get("updated_at", 0))
        for key, _ in oldest[: len(self._items) - self._max_entries]:
            self._items.pop(key, None)


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_QUEUE_RANDOM = random.SystemRandom()


class JobQueue:
    def __init__(
        self,
        *,
        paths: AppPaths,
        renderer: T2IRenderer | None,
        default_dry_run: bool,
        progress_store: ProgressStore,
        generation_lock: threading.Lock,
        max_entries: int = 128,
    ) -> None:
        self._paths = paths
        self._renderer = renderer
        self._default_dry_run = default_dry_run
        self._progress_store = progress_store
        self._generation_lock = generation_lock
        self._max_entries = max_entries
        self._jobs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._pending: deque[str] = deque()
        self._batches: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._id_lock = threading.Lock()
        self._counter = 0
        self._closed = False
        self._worker = threading.Thread(target=self._worker_loop, name="anima-job-queue", daemon=True)
        self._worker.start()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def enqueue(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        request = payload.get("request", payload)
        if not isinstance(request, dict):
            return HTTPStatus.BAD_REQUEST, {"error": "job request must be an object"}
        count = _bounded_job_count(payload.get("count", 1))
        infinite = bool(payload.get("infinite", payload.get("queue_infinite", False)))
        seed_mode = str(payload.get("seed_mode", payload.get("queue_seed_mode", "increment"))).strip().lower()
        if seed_mode not in {"fixed", "increment", "random"}:
            return HTTPStatus.BAD_REQUEST, {"error": "seed_mode must be fixed, increment, or random"}
        delay_seconds = _bounded_queue_delay(payload.get("delay_seconds", payload.get("delay", 0)))
        base_seed = _optional_queue_seed(request.get("seed"))
        base_seed_provided = "seed" in request and base_seed is not None
        batch_id = self._new_id("batch")
        created: list[dict[str, Any]] = []
        with self._condition:
            self._batches[batch_id] = {
                "id": batch_id,
                "infinite": infinite,
                "stopped": False,
                "base_request": copy.deepcopy(request),
                "seed_mode": seed_mode,
                "base_seed": base_seed,
                "base_seed_provided": base_seed_provided,
                "delay_seconds": delay_seconds,
                "next_index": 0,
            }
            total = 1 if infinite else count
            for index in range(total):
                created.append(self._append_batch_job_locked(batch_id, index, delay_seconds if index > 0 else 0))
            self._batches[batch_id]["next_index"] = total
            self._prune_locked()
            self._condition.notify_all()
        response = {
            "status": "queued",
            "batch_id": batch_id,
            "count": len(created),
            "infinite": infinite,
            "jobs": created,
        }
        response["summary"] = self.summary()
        return HTTPStatus.ACCEPTED, response

    def list(self) -> dict[str, Any]:
        with self._lock:
            items = [self._public_job_locked(self._jobs[job_id]) for job_id in self._order if job_id in self._jobs]
        return {"count": len(items), "items": items, "summary": self.summary()}

    def get(self, job_id: str) -> tuple[int, dict[str, Any]]:
        job_id = _job_id_from_path(job_id)
        if not _JOB_ID_RE.match(job_id):
            return HTTPStatus.BAD_REQUEST, {"error": "invalid job id"}
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return HTTPStatus.NOT_FOUND, {"error": "job not found"}
            return HTTPStatus.OK, self._public_job_locked(job)

    def cancel(self, job_id: str) -> tuple[int, dict[str, Any]]:
        job_id = _job_id_from_path(job_id)
        if not _JOB_ID_RE.match(job_id):
            return HTTPStatus.BAD_REQUEST, {"error": "invalid job id"}
        interrupt_requested = False
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                return HTTPStatus.NOT_FOUND, {"error": "job not found"}
            batch = self._batches.get(str(job.get("batch_id")))
            if batch is not None:
                batch["stopped"] = True
            if job["status"] in {"queued", "waiting"}:
                job["status"] = "cancelled"
                job["cancel_requested"] = True
                job["updated_at"] = time.time()
            elif job["status"] == "running":
                job["cancel_requested"] = True
                job["updated_at"] = time.time()
                interrupt_requested = _set_runtime_interrupt(True)
            response = self._public_job_locked(job)
            response["interrupt_requested"] = interrupt_requested
            self._condition.notify_all()
        return HTTPStatus.OK, {"status": response["status"], "job": response}

    def summary(self) -> dict[str, int]:
        counts = {"queued": 0, "waiting": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
        with self._lock:
            for job in self._jobs.values():
                status = str(job.get("status", ""))
                if status in counts:
                    counts[status] += 1
        return counts

    def _worker_loop(self) -> None:
        while True:
            job = self._next_job()
            if job is None:
                return
            if not self._wait_before_run(job):
                continue
            self._run_job(job)

    def _next_job(self) -> dict[str, Any] | None:
        with self._condition:
            while not self._closed and not self._pending:
                self._condition.wait()
            if self._closed:
                return None
            job_id = self._pending.popleft()
            job = self._jobs.get(job_id)
            if job is None or job.get("status") == "cancelled":
                return {}
            job["status"] = "waiting" if job.get("delay_seconds", 0) > 0 else "running"
            job["started_at"] = time.time() if job["status"] == "running" else None
            job["updated_at"] = time.time()
            return copy.deepcopy(job)

    def _wait_before_run(self, job: dict[str, Any]) -> bool:
        if not job:
            return False
        delay_seconds = float(job.get("delay_seconds", 0) or 0)
        job_id = str(job["id"])
        if delay_seconds <= 0:
            return True
        deadline = time.time() + delay_seconds
        with self._condition:
            while time.time() < deadline:
                current = self._jobs.get(job_id)
                if current is None or current.get("status") == "cancelled" or current.get("cancel_requested"):
                    return False
                self._condition.wait(timeout=min(0.1, deadline - time.time()))
            current = self._jobs.get(job_id)
            if current is None or current.get("status") == "cancelled" or current.get("cancel_requested"):
                return False
            current["status"] = "running"
            current["started_at"] = time.time()
            current["updated_at"] = time.time()
        return True

    def _run_job(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        payload = copy.deepcopy(job["request"])
        payload["progress_id"] = str(job.get("progress_id", job_id))
        _set_runtime_interrupt(False)
        try:
            with self._generation_lock:
                status, response = handle_generate(
                    payload,
                    paths=self._paths,
                    renderer=self._renderer,
                    default_dry_run=self._default_dry_run,
                    progress_store=self._progress_store,
                )
        except BaseException as exc:
            if exc.__class__.__name__ == "InterruptProcessingException":
                status = 499
                response = {"error": "generation interrupted"}
            else:
                status = 500
                response = {"error": str(exc)}
        finally:
            _set_runtime_interrupt(False)
        self._finish_job(job_id, int(status), response)

    def _finish_job(self, job_id: str, http_status: int, response: dict[str, Any]) -> None:
        enqueue_next = False
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["http_status"] = http_status
            job["result"] = copy.deepcopy(response)
            job["error"] = str(response.get("error", "")) if http_status >= 400 else ""
            job["status"] = "completed" if http_status < 400 else "failed"
            job["finished_at"] = time.time()
            job["updated_at"] = time.time()
            batch = self._batches.get(str(job.get("batch_id")))
            enqueue_next = bool(batch and batch.get("infinite") and not batch.get("stopped") and not job.get("cancel_requested"))
            if enqueue_next:
                index = int(batch.get("next_index", 0))
                self._append_batch_job_locked(str(batch["id"]), index, float(batch.get("delay_seconds", 0) or 0))
                batch["next_index"] = index + 1
            self._prune_locked()
            self._condition.notify_all()

    def _append_batch_job_locked(self, batch_id: str, index: int, delay_seconds: float) -> dict[str, Any]:
        batch = self._batches[batch_id]
        job_id = self._new_id("job")
        request = _request_for_queue_index(
            batch["base_request"],
            index=index,
            seed_mode=str(batch["seed_mode"]),
            base_seed=batch["base_seed"],
            base_seed_provided=bool(batch["base_seed_provided"]),
        )
        now = time.time()
        job = {
            "id": job_id,
            "batch_id": batch_id,
            "index": index,
            "status": "queued",
            "request": request,
            "progress_id": job_id,
            "cancel_requested": False,
            "result": None,
            "error": "",
            "http_status": None,
            "delay_seconds": delay_seconds,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "updated_at": now,
        }
        self._jobs[job_id] = job
        self._order.append(job_id)
        self._pending.append(job_id)
        return self._public_job_locked(job)

    def _new_id(self, prefix: str) -> str:
        with self._id_lock:
            self._counter += 1
            return f"{prefix}-{int(time.time() * 1000)}-{self._counter}"

    def _public_job_locked(self, job: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(job)

    def _prune_locked(self) -> None:
        if len(self._order) <= self._max_entries:
            return
        removable = self._order[: len(self._order) - self._max_entries]
        self._order = self._order[len(removable) :]
        for job_id in removable:
            job = self._jobs.get(job_id)
            if job and job.get("status") not in {"queued", "waiting", "running"}:
                self._jobs.pop(job_id, None)


def _job_id_from_path(value: str) -> str:
    return Path(unquote(value)).name


def _optional_queue_seed(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bounded_job_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 1
    return max(1, min(count, 999))


def _bounded_queue_delay(value: Any) -> float:
    try:
        delay = float(value)
    except (TypeError, ValueError):
        delay = 0.0
    return max(0.0, min(delay, 60.0))


def _request_for_queue_index(
    request: dict[str, Any],
    *,
    index: int,
    seed_mode: str,
    base_seed: int | None,
    base_seed_provided: bool,
) -> dict[str, Any]:
    queued = copy.deepcopy(request)
    if seed_mode == "random":
        queued["seed"] = _QUEUE_RANDOM.randint(0, 2147483646)
    elif seed_mode == "increment":
        seed = base_seed if base_seed is not None else int(time.time() * 1000) % 2147483647
        queued["seed"] = seed + index
    elif base_seed_provided and base_seed is not None:
        queued["seed"] = base_seed
    else:
        queued.pop("seed", None)
    return queued


def _set_runtime_interrupt(value: bool) -> bool:
    try:
        import comfy.model_management as model_management

        model_management.interrupt_current_processing(value)
        return True
    except Exception:
        return False


def _progress_id_from_payload(payload: dict[str, Any]) -> str | None:
    progress_id = str(payload.get("progress_id", "")).strip()
    if not progress_id:
        return None
    return progress_id if _PROGRESS_ID_RE.match(progress_id) else None


def _progress_id_from_path(value: str) -> str:
    return Path(unquote(value)).name


def _initial_progress_stages(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    upscale = payload.get("upscale") if isinstance(payload.get("upscale"), dict) else {}
    face_detailer = payload.get("face_detailer") if isinstance(payload.get("face_detailer"), dict) else {}
    stages: dict[str, dict[str, Any]] = {}
    for key, label in _PROGRESS_STAGE_LABELS.items():
        stages[key] = {"label": label, "status": "pending"}
    if not bool(upscale.get("enabled")):
        stages["high_res_fix"]["status"] = "skipped"
    if not bool(face_detailer.get("enabled")):
        stages["face_detailer"]["status"] = "skipped"
        stages["face_eye_detailer"]["status"] = "skipped"
        stages["hand_detailer"]["status"] = "skipped"
    elif str(face_detailer.get("mask_backend", "sam_b")) == "sam3":
        stages["face_detailer"]["status"] = "skipped"
        if not bool(face_detailer.get("sam3_face_eyes", True)):
            stages["face_eye_detailer"]["status"] = "skipped"
        if not bool(face_detailer.get("sam3_hands", False)):
            stages["hand_detailer"]["status"] = "skipped"
    else:
        stages["face_eye_detailer"]["status"] = "skipped"
        stages["hand_detailer"]["status"] = "skipped"
    return stages


def _completed_progress_stages(
    current_stages: dict[str, dict[str, Any]],
    manifest_stages: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = copy.deepcopy(current_stages)
    for key in _PROGRESS_STAGE_ORDER:
        stage = completed.setdefault(key, {"label": _PROGRESS_STAGE_LABELS[key]})
        manifest_stage = manifest_stages.get(key, {}) if isinstance(manifest_stages, dict) else {}
        if key in {"request", "wildcards", "text_encode", "metadata"}:
            stage["status"] = "completed"
        elif isinstance(manifest_stage, dict) and (
            manifest_stage.get("status") in {"disabled", "skipped"} or manifest_stage.get("method") == "not_run"
        ):
            stage.update(manifest_stage)
            stage["status"] = "skipped"
        elif isinstance(manifest_stage, dict) and manifest_stage.get("status"):
            stage.update(manifest_stage)
        elif stage.get("status") != "skipped":
            stage["status"] = "completed"
    return completed


def request_from_payload(payload: dict[str, Any]) -> T2IRequest:
    return T2IRequest(
        prompt=str(payload.get("prompt", "")),
        negative_prompt=str(payload.get("negative_prompt", payload.get("negative", ""))),
        memory_profile=str(payload.get("memory_profile", "auto")),
        width=int(payload.get("width", DEFAULT_T2I_WIDTH)),
        height=int(payload.get("height", DEFAULT_T2I_HEIGHT)),
        steps=int(payload.get("steps", DEFAULT_T2I_STEPS)),
        cfg=float(payload.get("cfg", DEFAULT_T2I_CFG)),
        seed=_optional_int(payload.get("seed")),
        checkpoint=str(payload.get("checkpoint", DEFAULT_T2I_CHECKPOINT)),
        sampler=str(payload.get("sampler", DEFAULT_T2I_SAMPLER)),
        scheduler=str(payload.get("scheduler", DEFAULT_T2I_SCHEDULER)),
        loras=tuple(_lora_from_payload(item) for item in payload.get("loras", [])),
        i2i=_i2i_from_payload(payload.get("i2i", {}), payload),
        upscale=_upscale_from_payload(payload.get("upscale", {})),
        face_detailer=_face_detailer_from_payload(payload.get("face_detailer", {})),
        vae_decode=_vae_decode_from_payload(payload.get("vae_decode", {})),
    )


def handle_generate(
    payload: dict[str, Any],
    *,
    paths: AppPaths,
    renderer: T2IRenderer | None = None,
    default_dry_run: bool = False,
    progress_store: ProgressStore | None = None,
) -> tuple[int, dict[str, Any]]:
    progress_id = _progress_id_from_payload(payload)
    if progress_store is not None and progress_id is not None:
        progress_store.start(progress_id, payload)
        progress_store.update_stage(progress_id, "request", "active")
        progress_store.update_summary(progress_id, "요청 확인 중")
    try:
        request = request_from_payload(payload)
        request = resolve_auto_memory_profile(request, paths=paths)
        if progress_store is not None and progress_id is not None:
            progress_store.update_stage(progress_id, "request", "completed")
            progress_store.update_stage(progress_id, "wildcards", "active")
            progress_store.update_summary(progress_id, "프롬프트 준비 중")
        wildcard_mode = str(payload.get("wildcard_mode", payload.get("wildcards", "random")))
        request, wildcard_expansion = expand_request_wildcards(request, paths=paths, mode=wildcard_mode)
        if progress_store is not None and progress_id is not None:
            progress_store.update_stage(progress_id, "wildcards", "completed", mode=wildcard_expansion.get("mode", "random"))
            progress_store.update_stage(progress_id, "text_encode", "completed")
            progress_store.update_stage(progress_id, "base_t2i", "active")
            progress_store.update_summary(progress_id, "렌더링 중")
        dry_run = bool(payload.get("dry_run", default_dry_run))
        result = run_t2i(request, paths=paths, dry_run=dry_run, renderer=None if dry_run else renderer, wildcards=wildcard_expansion)
        manifest = read_manifest(result.manifest_path)
        output_path = str(result.output_path) if result.output_path else None
        response = {
            "status": result.status,
            "manifest_path": str(result.manifest_path),
            "output_path": output_path,
            "output_url": _output_url(result.output_path, paths) if result.output_path else None,
            "variants": _variants_with_urls(manifest, paths),
            "warnings": list(result.warnings),
            "stages": manifest.get("stages", {}),
            "wildcards": manifest.get("wildcards", {}),
            "checkpoint": manifest.get("checkpoint", request.checkpoint),
            "dry_run": dry_run,
        }
        if progress_store is not None and progress_id is not None:
            progress_store.complete(progress_id, response)
        return HTTPStatus.OK, response
    except (NotImplementedError, ValueError, TypeError) as exc:
        if progress_store is not None and progress_id is not None:
            progress_store.fail(progress_id, str(exc))
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def handle_progress(name: str, *, progress_store: ProgressStore) -> tuple[int, dict[str, Any]]:
    progress_id = _progress_id_from_path(name)
    if not _PROGRESS_ID_RE.match(progress_id):
        return HTTPStatus.BAD_REQUEST, {"error": "invalid progress id"}
    payload = progress_store.get(progress_id)
    if payload is None:
        return HTTPStatus.NOT_FOUND, {"error": "progress not found"}
    return HTTPStatus.OK, payload


def handle_jobs(*, job_queue: JobQueue) -> dict[str, Any]:
    return job_queue.list()


def handle_job_detail(name: str, *, job_queue: JobQueue) -> tuple[int, dict[str, Any]]:
    return job_queue.get(name)


def handle_job_enqueue(payload: dict[str, Any], *, job_queue: JobQueue) -> tuple[int, dict[str, Any]]:
    return job_queue.enqueue(payload)


def handle_job_cancel(name: str, *, job_queue: JobQueue) -> tuple[int, dict[str, Any]]:
    return job_queue.cancel(name)


def handle_history(*, paths: AppPaths, limit: int = 20) -> dict[str, Any]:
    items = [_history_item(payload, paths) for payload in read_t2i_history(paths, limit=limit)]
    return {"count": len(items), "items": items}


def handle_readiness(*, paths: AppPaths) -> dict[str, Any]:
    profiles = [_readiness_profile(profile, paths) for profile in asset_profiles()]
    return {
        "profiles": profiles,
        "ready": all(profile["ready"] for profile in profiles),
    }


def handle_model_prepare(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    try:
        profile = asset_profile(str(payload.get("profile", "")))
        source = str(payload.get("source", "auto"))
        selected_source, copied_paths = copy_asset_profile(profile, paths, source=source)
        return HTTPStatus.OK, {
            "profile": profile.name,
            "source": selected_source,
            "copied": [str(path) for path in copied_paths],
            "readiness": _readiness_profile(profile, paths),
        }
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def handle_sam3_segment(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    try:
        result = segment_image_concept(
            str(payload.get("image_path", "")),
            prompt=str(payload.get("prompt", "")),
            paths=paths,
            threshold=float(payload.get("threshold", 0.25)),
        )
        return HTTPStatus.OK, {
            "status": "sam3_segmented",
            **_sam3_result_payload(result, paths),
        }
    except (FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def handle_sam3_compare(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    raw_prompts = payload.get("prompts", [])
    if not isinstance(raw_prompts, list):
        raw_prompts = []
    try:
        results = segment_image_concepts(
            str(payload.get("image_path", "")),
            prompts=[str(prompt) for prompt in raw_prompts],
            paths=paths,
            threshold=float(payload.get("threshold", 0.25)),
        )
        items = [_sam3_result_payload(result, paths) for result in results]
        best = max(items, key=lambda item: (len(item["boxes"]), max(item["scores"] or [0.0])), default=None)
        return HTTPStatus.OK, {
            "status": "sam3_compared",
            "count": len(items),
            "best": best,
            "results": items,
        }
    except (FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def handle_mask_adjust(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    try:
        result = adjust_segment_mask(
            str(payload.get("image_path", "")),
            mask_path=str(payload.get("mask_path", "")),
            paths=paths,
            dilation=int(payload.get("dilation", 0)),
            feather=int(payload.get("feather", 0)),
            threshold=int(payload.get("threshold", 8)),
        )
        return HTTPStatus.OK, {
            "status": "mask_adjusted",
            **_mask_adjustment_payload(result, paths),
        }
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def handle_masked_inpaint(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    try:
        result = run_masked_inpaint(
            MaskedInpaintSettings(
                image_path=str(payload.get("image_path", "")),
                mask_path=str(payload.get("mask_path", "")),
                prompt=str(payload.get("prompt", "")),
                checkpoint=str(payload.get("checkpoint") or handle_checkpoints(paths)["default"]),
                negative_prompt=str(payload.get("negative_prompt", "")),
                method=str(payload.get("method", "noise_mask")),
                denoise=float(payload.get("denoise", 0.65)),
                steps=int(payload.get("steps", DEFAULT_T2I_STEPS)),
                cfg=float(payload.get("cfg", DEFAULT_T2I_CFG)),
                seed=_optional_int(payload.get("seed")),
                width=_optional_int(payload.get("width")),
                height=_optional_int(payload.get("height")),
            ),
            paths=paths,
        )
        return HTTPStatus.OK, {
            "status": "masked_inpainted",
            "method": result.method,
            "seed": result.seed,
            "crop_box": list(result.crop_box),
            "output_path": str(result.output_path),
            "output_url": _output_url(result.output_path, paths),
            "crop_path": str(result.crop_path),
            "crop_url": _output_url(result.crop_path, paths),
        }
    except (FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def _sam3_result_payload(result: Sam3SegmentResult, paths: AppPaths) -> dict[str, Any]:
    return {
        "prompt": result.prompt,
        "source_path": str(result.source_path),
        "mask_path": str(result.mask_path),
        "mask_url": _output_url(result.mask_path, paths),
        "overlay_path": str(result.overlay_path),
        "overlay_url": _output_url(result.overlay_path, paths),
        "boxes": [list(box) for box in result.boxes],
        "scores": list(result.scores),
    }


def _mask_adjustment_payload(result: Sam3MaskAdjustmentResult, paths: AppPaths) -> dict[str, Any]:
    return {
        "source_path": str(result.source_path),
        "mask_path": str(result.mask_path),
        "mask_url": _output_url(result.mask_path, paths),
        "overlay_path": str(result.overlay_path),
        "overlay_url": _output_url(result.overlay_path, paths),
        "crop_path": str(result.crop_path),
        "crop_url": _output_url(result.crop_path, paths),
        "crop_mask_path": str(result.crop_mask_path),
        "crop_mask_url": _output_url(result.crop_mask_path, paths),
        "crop_box": list(result.crop_box),
        "dilation": result.dilation,
        "feather": result.feather,
    }


def handle_manifest_detail(name: str, *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    manifest_name = Path(unquote(name)).name
    if not manifest_name.endswith(".json"):
        return HTTPStatus.BAD_REQUEST, {"error": "manifest name must end with .json"}
    manifest_path = (paths.manifest_root / manifest_name).resolve()
    try:
        manifest_path.relative_to(paths.manifest_root.resolve())
    except ValueError:
        return HTTPStatus.FORBIDDEN, {"error": "forbidden"}
    if not manifest_path.is_file():
        return HTTPStatus.NOT_FOUND, {"error": "manifest not found"}
    payload = read_manifest(manifest_path)
    payload["output_url"] = _output_url(Path(str(payload["output_path"])), paths) if payload.get("output_path") else None
    payload["variants"] = _variants_with_urls(payload, paths)
    return HTTPStatus.OK, payload


def handle_manifest_delete(name: str, *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    manifest_name = Path(unquote(name)).name
    if not manifest_name.endswith(".json"):
        return HTTPStatus.BAD_REQUEST, {"error": "manifest name must end with .json"}
    manifest_path = (paths.manifest_root / manifest_name).resolve()
    try:
        manifest_path.relative_to(paths.manifest_root.resolve())
    except ValueError:
        return HTTPStatus.FORBIDDEN, {"error": "forbidden"}
    if not manifest_path.is_file():
        return HTTPStatus.NOT_FOUND, {"error": "manifest not found"}

    try:
        payload = read_manifest(manifest_path)
        deleted_output = False
        output_skip_reason = None
        output_path_value = payload.get("output_path")
        if output_path_value:
            output_path = Path(str(output_path_value)).resolve()
            try:
                output_path.relative_to(paths.image_root.resolve())
            except ValueError:
                output_skip_reason = "output path is outside the managed image root"
            else:
                if output_path.is_file():
                    output_path.unlink()
                    deleted_output = True
                else:
                    output_skip_reason = "output file was already missing"
        for variant in (payload.get("variants", {}) or {}).values():
            if not isinstance(variant, dict):
                continue
            variant_output = variant.get("output_path")
            if not variant_output:
                continue
            variant_path = Path(str(variant_output)).resolve()
            try:
                variant_path.relative_to(paths.image_root.resolve())
            except ValueError:
                continue
            if output_path_value and variant_path == Path(str(output_path_value)).resolve():
                continue
            if variant_path.is_file():
                variant_path.unlink()
        manifest_path.unlink()
    except OSError as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    response: dict[str, Any] = {
        "status": "deleted",
        "manifest_name": manifest_name,
        "deleted_manifest": True,
        "deleted_output": deleted_output,
    }
    if output_skip_reason:
        response["output_skip_reason"] = output_skip_reason
    return HTTPStatus.OK, response


def handle_presets(*, paths: AppPaths) -> dict[str, Any]:
    items = [_read_preset(path) for path in _preset_root(paths).glob("*.json")] if _preset_root(paths).is_dir() else []
    items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"count": len(items), "items": items}


def handle_preset_export(*, paths: AppPaths) -> dict[str, Any]:
    presets_payload = handle_presets(paths=paths)
    return {
        "schema": "anima-app/presets.v1",
        "count": presets_payload["count"],
        "items": presets_payload["items"],
    }


def handle_preset_save(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    try:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("preset name is required")
        request_payload = payload.get("request", {})
        if not isinstance(request_payload, dict):
            raise ValueError("preset request must be an object")
        request_from_payload(request_payload)
        slug = _preset_slug(name)
        if not slug:
            raise ValueError("preset name must contain letters or numbers")
        item = {"name": name, "slug": slug, "request": request_payload}
        root = _preset_root(paths)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{slug}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        return HTTPStatus.OK, item
    except (ValueError, TypeError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def handle_preset_import(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    items_payload = payload.get("items")
    if items_payload is None and {"name", "request"}.issubset(payload):
        items_payload = [payload]
    if not isinstance(items_payload, list):
        return HTTPStatus.BAD_REQUEST, {"error": "preset import requires an items list", "imported_count": 0, "errors": []}

    imported: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(items_payload):
        if not isinstance(item, dict):
            errors.append({"index": index, "error": "preset item must be an object"})
            continue
        status, response = handle_preset_save({"name": item.get("name", ""), "request": item.get("request", {})}, paths=paths)
        if status == HTTPStatus.OK:
            imported.append(response)
        else:
            errors.append({"index": index, "name": item.get("name", ""), "error": response.get("error", "unknown error")})

    response_payload = {
        "status": "settings_imported" if imported else "settings_import_failed",
        "imported_count": len(imported),
        "items": imported,
        "errors": errors,
    }
    return (HTTPStatus.OK if imported else HTTPStatus.BAD_REQUEST), response_payload


def handle_loras(*, paths: AppPaths) -> dict[str, Any]:
    items = list_local_loras(paths)
    return {"count": len(items), "items": items}


def handle_checkpoints(*, paths: AppPaths) -> dict[str, Any]:
    items = list_local_checkpoints(paths)
    available = {str(item["relative_path"]) for item in items}
    default = PREFERRED_T2I_CHECKPOINT if PREFERRED_T2I_CHECKPOINT in available else DEFAULT_T2I_CHECKPOINT
    return {"count": len(items), "default": default, "items": items}


def handle_wildcards(*, paths: AppPaths) -> dict[str, Any]:
    items = list_wildcards(paths)
    presets = list_prompt_presets(paths)
    return {"count": len(items), "items": items, "preset_count": len(presets), "presets": presets}


def handle_autocomplete(*, paths: AppPaths, query: str = "", limit: int = 24) -> dict[str, Any]:
    return autocomplete_payload(paths, query=query, limit=limit)


def handle_wildcard_preview(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    prompt_text = str(payload.get("prompt", ""))
    negative_text = str(payload.get("negative_prompt", ""))
    mode = str(payload.get("wildcard_mode", payload.get("wildcards", "random")))
    seed = _optional_int(payload.get("seed"))
    try:
        prompt = expand_text_wildcards(prompt_text, paths=paths, mode=mode, seed=seed)
        negative = expand_text_wildcards(negative_text, paths=paths, mode=mode, seed=seed, salt="negative")
    except (OSError, ValueError, TypeError) as exc:
        return HTTPStatus.BAD_REQUEST, {
            "enabled": False,
            "mode": mode,
            "original_prompt": prompt_text,
            "original_negative_prompt": negative_text,
            "prompt": prompt_text,
            "negative_prompt": negative_text,
            "selection_count": 0,
            "selections": [],
            "error": str(exc),
        }

    selections = tuple(prompt.selections) + tuple(negative.selections)
    return HTTPStatus.OK, {
        "enabled": bool(selections),
        "mode": mode,
        "original_prompt": prompt_text,
        "original_negative_prompt": negative_text,
        "prompt": prompt.text,
        "negative_prompt": negative.text,
        "selection_count": len(selections),
        "selections": list(selections),
        "error": "",
    }


def handle_version() -> dict[str, Any]:
    return version_payload()


def handle_update_check() -> dict[str, Any]:
    return check_github_update()


def handle_lora_import(payload: dict[str, Any], *, paths: AppPaths) -> tuple[int, dict[str, Any]]:
    try:
        imported = import_lora_file(Path(str(payload.get("path", ""))), paths)
        return HTTPStatus.OK, {
            "imported": str(imported),
            "loras": handle_loras(paths=paths),
        }
    except (FileNotFoundError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def create_http_server(
    host: str,
    port: int,
    *,
    paths: AppPaths,
    renderer: T2IRenderer | None = None,
    default_dry_run: bool = False,
    llm_client: object | None = None,
) -> ThreadingHTTPServer:
    warm_autocomplete_index(paths)
    progress_store = ProgressStore()
    generation_lock = threading.Lock()
    llm_client = default_llm_client() if llm_client is None else llm_client
    job_queue = JobQueue(
        paths=paths,
        renderer=renderer,
        default_dry_run=default_dry_run,
        progress_store=progress_store,
        generation_lock=generation_lock,
    )

    class AnimaRequestHandler(BaseHTTPRequestHandler):
        server_version = f"AnimaAPP/{__version__}"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_bytes(HTTPStatus.OK, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._send_bytes(HTTPStatus.OK, APP_JS.encode("utf-8"), "text/javascript; charset=utf-8")
                return
            if parsed.path == "/favicon.ico":
                self._send_bytes(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
                return
            if parsed.path == "/api/health":
                self._send_json(HTTPStatus.OK, build_health_payload(paths))
                return
            if parsed.path == "/api/version":
                self._send_json(HTTPStatus.OK, handle_version())
                return
            if parsed.path == "/api/update-check":
                self._send_json(HTTPStatus.OK, handle_update_check())
                return
            if parsed.path == "/api/readiness":
                self._send_json(HTTPStatus.OK, handle_readiness(paths=paths))
                return
            if parsed.path == "/api/llm/status":
                self._send_json(HTTPStatus.OK, llm_status_payload(llm_client))
                return
            if parsed.path == "/api/loras":
                self._send_json(HTTPStatus.OK, handle_loras(paths=paths))
                return
            if parsed.path == "/api/checkpoints":
                self._send_json(HTTPStatus.OK, handle_checkpoints(paths=paths))
                return
            if parsed.path == "/api/wildcards":
                self._send_json(HTTPStatus.OK, handle_wildcards(paths=paths))
                return
            if parsed.path == "/api/autocomplete":
                query = parse_qs(parsed.query)
                limit = _bounded_limit(query.get("limit", ["24"])[0], maximum=100)
                self._send_json(
                    HTTPStatus.OK,
                    handle_autocomplete(paths=paths, query=query.get("q", [""])[0], limit=limit),
                )
                return
            if parsed.path == "/api/presets/export":
                self._send_json(HTTPStatus.OK, handle_preset_export(paths=paths))
                return
            if parsed.path == "/api/presets":
                self._send_json(HTTPStatus.OK, handle_presets(paths=paths))
                return
            if parsed.path == "/api/history":
                query = parse_qs(parsed.query)
                limit = _bounded_limit(query.get("limit", ["20"])[0])
                self._send_json(HTTPStatus.OK, handle_history(paths=paths, limit=limit))
                return
            if parsed.path == "/api/jobs":
                self._send_json(HTTPStatus.OK, handle_jobs(job_queue=job_queue))
                return
            if parsed.path.startswith("/api/jobs/"):
                status, response = handle_job_detail(parsed.path.removeprefix("/api/jobs/"), job_queue=job_queue)
                self._send_json(status, response)
                return
            if parsed.path.startswith("/api/progress/"):
                status, response = handle_progress(parsed.path.removeprefix("/api/progress/"), progress_store=progress_store)
                self._send_json(status, response)
                return
            if parsed.path.startswith("/api/manifests/"):
                status, response = handle_manifest_detail(parsed.path.removeprefix("/api/manifests/"), paths=paths)
                self._send_json(status, response)
                return
            if parsed.path.startswith("/outputs/images/"):
                self._send_image(parsed.path)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in {
                "/api/generate",
                "/api/jobs",
                "/api/loras/import",
                "/api/presets",
                "/api/presets/import",
                "/api/wildcards/preview",
                "/api/models/prepare",
                "/api/llm/generate",
                "/api/sam3/segment",
                "/api/sam3/compare",
                "/api/masks/adjust",
                "/api/inpaint/masked",
            } and not parsed.path.startswith("/api/jobs/"):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid json: {exc}"})
                return
            if parsed.path == "/api/loras/import":
                status, response = handle_lora_import(payload, paths=paths)
            elif parsed.path == "/api/presets/import":
                status, response = handle_preset_import(payload, paths=paths)
            elif parsed.path == "/api/presets":
                status, response = handle_preset_save(payload, paths=paths)
            elif parsed.path == "/api/models/prepare":
                status, response = handle_model_prepare(payload, paths=paths)
            elif parsed.path == "/api/llm/generate":
                status, response = llm_generate_payload(llm_client, payload)
            elif parsed.path == "/api/sam3/segment":
                status, response = handle_sam3_segment(payload, paths=paths)
            elif parsed.path == "/api/sam3/compare":
                status, response = handle_sam3_compare(payload, paths=paths)
            elif parsed.path == "/api/masks/adjust":
                status, response = handle_mask_adjust(payload, paths=paths)
            elif parsed.path == "/api/inpaint/masked":
                if not generation_lock.acquire(blocking=False):
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {"error": "generation already running; wait for the current job to finish"},
                    )
                    return
                try:
                    status, response = handle_masked_inpaint(payload, paths=paths)
                finally:
                    generation_lock.release()
            elif parsed.path == "/api/wildcards/preview":
                status, response = handle_wildcard_preview(payload, paths=paths)
            elif parsed.path == "/api/jobs":
                status, response = handle_job_enqueue(payload, job_queue=job_queue)
            elif parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
                status, response = handle_job_cancel(
                    parsed.path.removeprefix("/api/jobs/").removesuffix("/cancel"),
                    job_queue=job_queue,
                )
            elif parsed.path.startswith("/api/jobs/"):
                status, response = HTTPStatus.NOT_FOUND, {"error": "not found"}
            else:
                if not generation_lock.acquire(blocking=False):
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {"error": "generation already running; wait for the current job to finish"},
                    )
                    return
                try:
                    status, response = handle_generate(
                        payload,
                        paths=paths,
                        renderer=renderer,
                        default_dry_run=default_dry_run,
                        progress_store=progress_store,
                    )
                finally:
                    generation_lock.release()
            self._send_json(status, response)

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/manifests/"):
                status, response = handle_manifest_delete(parsed.path.removeprefix("/api/manifests/"), paths=paths)
                self._send_json(status, response)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            self._send_bytes(status, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")

        def _send_image(self, request_path: str) -> None:
            filename = Path(unquote(request_path)).name
            image_path = (paths.image_root / filename).resolve()
            try:
                image_path.relative_to(paths.image_root.resolve())
            except ValueError:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            if not image_path.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "image not found"})
                return
            self._send_bytes(HTTPStatus.OK, image_path.read_bytes(), "image/png")

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            try:
                self.send_response(int(status))
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return

    class AnimaThreadingHTTPServer(ThreadingHTTPServer):
        def server_close(self) -> None:
            job_queue.close()
            super().server_close()

    return AnimaThreadingHTTPServer((host, port), AnimaRequestHandler)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _lora_from_payload(value: Any) -> T2ILoraConfig:
    if isinstance(value, str):
        return parse_lora_spec(value)
    return T2ILoraConfig(
        path=str(value.get("path", "")),
        model_strength=float(value.get("model_strength", 1.0)),
        clip_strength=float(value.get("clip_strength", 1.0)),
    )


def _i2i_from_payload(value: Any, payload: dict[str, Any]) -> I2ISettings:
    if not isinstance(value, dict):
        value = {}
    image_path = str(value.get("image_path", payload.get("image", "")))
    return I2ISettings(
        enabled=bool(value.get("enabled", bool(image_path))),
        image_path=image_path,
        denoise=float(value.get("denoise", payload.get("denoise", 0.35))),
    )


def _upscale_from_payload(value: Any) -> UpscaleSettings:
    if not isinstance(value, dict):
        value = {}
    return UpscaleSettings(
        enabled=bool(value.get("enabled", False)),
        scale=float(value.get("scale", 1.5)),
        steps=int(value.get("steps", DEFAULT_UPSCALE_STEPS)),
        denoise=float(value.get("denoise", 0.35)),
        method=str(value.get("method", "bicubic")),
        tiled=bool(value.get("tiled", False)),
        tile_size=int(value.get("tile_size", DEFAULT_TILE_SIZE)),
        overlap=int(value.get("overlap", 8)),
    )


def _vae_decode_from_payload(value: Any) -> VaeDecodeSettings:
    if not isinstance(value, dict):
        value = {}
    return VaeDecodeSettings(
        mode=str(value.get("mode", "auto")),
        tile_size=int(value.get("tile_size", DEFAULT_TILE_SIZE)),
        overlap=int(value.get("overlap", 8)),
    )


def _face_detailer_from_payload(value: Any) -> FaceDetailerSettings:
    if not isinstance(value, dict):
        value = {}
    return FaceDetailerSettings(
        enabled=bool(value.get("enabled", False)),
        detector=str(value.get("detector", "default")),
        mask_backend=str(value.get("mask_backend", "sam_b")),
        threshold=float(value.get("threshold", 0.5)),
        crop_scale=float(value.get("crop_scale", 1.5)),
        padding=int(value.get("padding", 32)),
        feather=int(value.get("feather", 24)),
        exclude_forehead_ratio=float(value.get("exclude_forehead_ratio", 0)),
        steps=int(value.get("steps", DEFAULT_FACE_DETAILER_STEPS)),
        denoise=float(value.get("denoise", 0.28)),
        sam3_face_eyes=bool(value.get("sam3_face_eyes", True)),
        sam3_hands=bool(value.get("sam3_hands", False)),
        hand_denoise=float(value.get("hand_denoise", 0.35)),
    )


def _output_url(output_path: Path | None, paths: AppPaths) -> str | None:
    if output_path is None:
        return None
    resolved = output_path.resolve()
    resolved.relative_to(paths.image_root.resolve())
    return f"/outputs/images/{resolved.name}"


def _variants_with_urls(payload: dict[str, Any], paths: AppPaths) -> dict[str, dict[str, Any]]:
    raw_variants = payload.get("variants", {})
    if not isinstance(raw_variants, dict):
        return {}
    hydrated: dict[str, dict[str, Any]] = {}
    for key, value in raw_variants.items():
        if not isinstance(value, dict):
            continue
        output_path = value.get("output_path")
        if not output_path:
            continue
        item = dict(value)
        try:
            item["output_url"] = _output_url(Path(str(output_path)), paths)
        except ValueError:
            item["output_url"] = None
        hydrated[str(key)] = item
    return hydrated


def _history_item(payload: dict[str, Any], paths: AppPaths) -> dict[str, Any]:
    output_path = payload.get("output_path")
    resolved_output = Path(str(output_path)) if output_path else None
    return {
        "prompt": payload.get("prompt", ""),
        "status": payload.get("status", ""),
        "created_at": payload.get("created_at", 0),
        "manifest_path": payload.get("manifest_path", ""),
        "output_path": str(resolved_output) if resolved_output else None,
        "output_url": _output_url(resolved_output, paths) if resolved_output else None,
        "width": payload.get("width"),
        "height": payload.get("height"),
        "seed": payload.get("seed"),
        "checkpoint": payload.get("checkpoint", DEFAULT_T2I_CHECKPOINT),
    }


def _readiness_profile(profile: Any, paths: AppPaths) -> dict[str, Any]:
    files = []
    for relative_path in profile.files:
        destination = paths.model_root / relative_path
        exists = destination.is_file()
        files.append(
            {
                "relative_path": relative_path.as_posix(),
                "path": str(destination),
                "exists": exists,
                "size_bytes": destination.stat().st_size if exists else 0,
            }
        )
    missing = [item for item in files if not item["exists"]]
    return {
        "name": profile.name,
        "label": _profile_label(profile.name),
        "ready": not missing,
        "missing_count": len(missing),
        "files": files,
    }


def _profile_label(name: str) -> str:
    if name == "anima-t2i":
        return "Anima Base"
    if name == "anima-aesthetic-v1.1":
        return "Anima Aesthetic v1.1"
    if name == "face-detailer-detectors":
        return "Face Detectors"
    if name == "sam3-detector":
        return "SAM3"
    return name


def _bounded_limit(value: str, *, default: int = 20, maximum: int = 100) -> int:
    try:
        limit = int(value)
    except ValueError:
        return default
    return max(1, min(limit, maximum))


def _preset_root(paths: AppPaths) -> Path:
    return paths.output_root / "presets"


def _preset_slug(name: str) -> str:
    chars: list[str] = []
    last_was_dash = False
    for char in name.lower():
        if char.isalnum():
            chars.append(char)
            last_was_dash = False
        elif not last_was_dash:
            chars.append("-")
            last_was_dash = True
    return "".join(chars).strip("-")


def _read_preset(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
