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
)
from anima_app.health import build_health_payload
from anima_app.manifests import read_manifest, read_t2i_history
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2ILoraConfig, T2IRequest, UpscaleSettings, VaeDecodeSettings
from anima_app.runtime.pipeline import T2IRenderer, run_t2i
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
              <label for="checkpoint-select">베이스 체크포인트</label>
              <select id="checkpoint-select" name="checkpoint" form="generate-form">
                <option value="__DEFAULT_T2I_CHECKPOINT__">__DEFAULT_T2I_CHECKPOINT__</option>
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
                    <option value="euler">Euler Ancestral</option>
                    <option value="dpmpp_2m">DPM++ 2M</option>
                    <option value="dpmpp_sde">DPM++ SDE</option>
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
                  <input id="upscale-steps" name="upscale_steps" type="number" min="1" value="12" form="generate-form">
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
                  <input id="upscale-tile-size" name="upscale_tile_size" type="number" min="1" value="64" form="generate-form">
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
                  <input id="vae-tile-size" name="vae_tile_size" type="number" min="1" value="64" form="generate-form">
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
                  <input id="face-steps" name="face_steps" type="number" min="1" value="12" form="generate-form">
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
        <details class="result-json">
          <summary>상세 생성 정보</summary>
          <pre id="result">준비됨.</pre>
        </details>
      </section>
    </main>
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
  <script>
    const form = document.getElementById("generate-form");
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
    const wildcardSelect = document.getElementById("wildcard-select");
    const insertWildcardButton = document.getElementById("insert-wildcard");
    const presetWildcardSelect = document.getElementById("preset-wildcard-select");
    const insertPresetWildcardButton = document.getElementById("insert-preset-wildcard");
    const previewWildcardsButton = document.getElementById("preview-wildcards");
    const wildcardPreview = document.getElementById("wildcard-preview");
    const startingSizeButtons = Array.from(document.querySelectorAll("[data-size-preset]"));
    const orientationButtons = Array.from(document.querySelectorAll("[data-orientation]"));
    const referenceImageSection = document.getElementById("reference-image-section");
    const faceDetailerSection = document.getElementById("face-detailer-section");
    let presets = [];
    let currentManifest = null;
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
      const face = payload.face_detailer?.enabled ? `${payload.face_detailer.steps || "자동"} 스텝` : "꺼짐";
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
      return [
        {key: "original", label: "원본"},
        {key: "upscale", label: "업스케일"},
        {key: "face_detailer", label: "페이스 디테일러"}
      ].map((slot) => {
        const variant = variants[slot.key] || {};
        return {
          ...slot,
          ...variant,
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
        {key: "face_detailer", label: "페이스 디테일러", optional: !data.face_detailer?.enabled},
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
      preview.removeAttribute("src");
      preview.hidden = true;
      outputLink.removeAttribute("href");
      outputLink.hidden = true;
    }
    function showOutputPreview(url) {
      preview.src = url + "?t=" + Date.now();
      preview.hidden = false;
      outputLink.href = url;
      outputLink.hidden = false;
    }
    function setSelectValue(select, value) {
      if (value && ![...select.options].some((option) => option.value === value)) {
        select.add(new Option(`${value} (누락)`, value));
      }
      select.value = value || "";
    }
    function renderCheckpointOptions(inventory, selectedCheckpoint) {
      const defaultCheckpoint = inventory.default || "__DEFAULT_T2I_CHECKPOINT__";
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
      const manifestName = item.manifest_path.split(/[\\/]/).pop();
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
      const currentName = currentManifest?.manifest_path?.split(/[\\/]/).pop();
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
      wildcardPreview.textContent = lines.join("\\n");
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
    function buildRequestData() {
      const data = Object.fromEntries(new FormData(form).entries());
      data.width = Number(data.width);
      data.height = Number(data.height);
      data.steps = Number(data.steps);
      data.cfg = Number(data.cfg);
      data.checkpoint = data.checkpoint || "__DEFAULT_T2I_CHECKPOINT__";
      if (data.i2i_image) {
        data.i2i = {enabled: true, image_path: data.i2i_image, denoise: Number(data.i2i_denoise || 0.35)};
      }
      if (data.upscale_enabled) {
        data.upscale = {
          enabled: true,
          scale: Number(data.upscale_scale || 1.5),
          steps: Number(data.upscale_steps || 12),
          denoise: Number(data.upscale_denoise || 0.35),
          method: data.upscale_method || "bicubic",
          tiled: Boolean(data.upscale_tiled),
          tile_size: Number(data.upscale_tile_size || 64),
          overlap: Number(data.upscale_overlap || 8)
        };
      }
      data.vae_decode = {
        mode: data.vae_decode_mode || "auto",
        tile_size: Number(data.vae_tile_size || 64),
        overlap: Number(data.vae_overlap || 8)
      };
      if (data.face_detailer_enabled) {
        data.face_detailer = {
          enabled: true,
          detector: data.face_detector || "default",
          threshold: Number(data.face_threshold || 0.5),
          crop_scale: Number(data.face_crop_scale || 1.5),
          padding: Number(data.face_padding || 32),
          feather: Number(data.face_feather || 24),
          exclude_forehead_ratio: Number(data.face_exclude_forehead || 0),
          steps: Number(data.face_steps || 12),
          denoise: Number(data.face_denoise || 0.28)
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
      delete data.face_threshold;
      delete data.face_crop_scale;
      delete data.face_padding;
      delete data.face_feather;
      delete data.face_exclude_forehead;
      delete data.face_steps;
      delete data.face_denoise;
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
    function applyPreset(item) {
      const request = item.request || {};
      const wildcardInfo = request.wildcards || {};
      form.elements.prompt.value = wildcardInfo.original_prompt || request.prompt || "";
      form.elements.negative_prompt.value = wildcardInfo.original_negative_prompt || request.negative_prompt || "";
      form.elements.width.value = request.width || __DEFAULT_T2I_WIDTH__;
      form.elements.height.value = request.height || __DEFAULT_T2I_HEIGHT__;
      form.elements.steps.value = request.steps || __DEFAULT_T2I_STEPS__;
      form.elements.cfg.value = request.cfg || __DEFAULT_T2I_CFG__;
      form.elements.sampler.value = request.sampler || "__DEFAULT_T2I_SAMPLER__";
      form.elements.scheduler.value = request.scheduler || "__DEFAULT_T2I_SCHEDULER__";
      form.elements.seed.value = request.seed ?? "";
      setSelectValue(checkpointSelect, request.checkpoint || "__DEFAULT_T2I_CHECKPOINT__");
      const wildcardMode = request.wildcard_mode || wildcardInfo.mode || "random";
      form.elements.wildcard_mode.value = wildcardMode === "off" ? "random" : wildcardMode;
      form.elements.i2i_image.value = request.i2i?.image_path || "";
      form.elements.i2i_denoise.value = request.i2i?.denoise ?? 0.35;
      form.elements.upscale_enabled.checked = Boolean(request.upscale?.enabled);
      form.elements.upscale_scale.value = request.upscale?.scale ?? 1.5;
      form.elements.upscale_steps.value = request.upscale?.steps ?? 12;
      form.elements.upscale_denoise.value = request.upscale?.denoise ?? 0.35;
      form.elements.upscale_method.value = request.upscale?.method || "bicubic";
      form.elements.upscale_tiled.checked = Boolean(request.upscale?.tiled);
      form.elements.upscale_tile_size.value = request.upscale?.tile_size ?? 64;
      form.elements.upscale_overlap.value = request.upscale?.overlap ?? 8;
      form.elements.vae_decode_mode.value = request.vae_decode?.mode || "auto";
      form.elements.vae_tile_size.value = request.vae_decode?.tile_size ?? 64;
      form.elements.vae_overlap.value = request.vae_decode?.overlap ?? 8;
      form.elements.face_detailer_enabled.checked = Boolean(request.face_detailer?.enabled);
      form.elements.face_detector.value = request.face_detailer?.detector || "default";
      form.elements.face_threshold.value = request.face_detailer?.threshold ?? 0.5;
      form.elements.face_crop_scale.value = request.face_detailer?.crop_scale ?? 1.5;
      form.elements.face_padding.value = request.face_detailer?.padding ?? 32;
      form.elements.face_feather.value = request.face_detailer?.feather ?? 24;
      form.elements.face_exclude_forehead.value = request.face_detailer?.exclude_forehead_ratio ?? 0;
      form.elements.face_steps.value = request.face_detailer?.steps ?? 12;
      form.elements.face_denoise.value = request.face_detailer?.denoise ?? 0.28;
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
          const manifestName = payload.manifest_path.split(/[\\/]/).pop();
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
        const manifestName = latest.result.manifest_path.split(/[\\/]/).pop();
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
    syncStartingPointButtons();
    applyManifestButton.addEventListener("click", applyManifest);
    toggleCompareButton.addEventListener("click", () => {
      compareVisible = !compareVisible;
      syncCompareControls(currentManifest);
    });
    insertWildcardButton.addEventListener("click", insertWildcard);
    insertPresetWildcardButton.addEventListener("click", insertPresetWildcard);
    previewWildcardsButton.addEventListener("click", previewWildcards);
    checkUpdateButton.addEventListener("click", checkForUpdates);
    addLoraButton.addEventListener("click", () => addLoraRow());
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
    loadStatus().catch(() => {});
    loadHistory().catch(() => {});
    loadPresets().catch(() => {});
    loadWildcards().catch(() => {});
    renderResultSummary();
  </script>
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


_PROGRESS_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_PROGRESS_STAGE_LABELS = {
    "request": "요청",
    "wildcards": "프롬프트 / 와일드카드",
    "text_encode": "텍스트 인코드",
    "base_t2i": "기본 렌더",
    "high_res_fix": "고해상도 / 업스케일",
    "vae_decode": "VAE 디코드",
    "face_detailer": "페이스 디테일러",
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
    return {"count": len(items), "default": DEFAULT_T2I_CHECKPOINT, "items": items}


def handle_wildcards(*, paths: AppPaths) -> dict[str, Any]:
    items = list_wildcards(paths)
    presets = list_prompt_presets(paths)
    return {"count": len(items), "items": items, "preset_count": len(presets), "presets": presets}


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
) -> ThreadingHTTPServer:
    progress_store = ProgressStore()
    generation_lock = threading.Lock()
    job_queue = JobQueue(
        paths=paths,
        renderer=renderer,
        default_dry_run=default_dry_run,
        progress_store=progress_store,
        generation_lock=generation_lock,
    )

    class AnimaRequestHandler(BaseHTTPRequestHandler):
        server_version = "AnimaAPP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_bytes(HTTPStatus.OK, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
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
            if parsed.path == "/api/loras":
                self._send_json(HTTPStatus.OK, handle_loras(paths=paths))
                return
            if parsed.path == "/api/checkpoints":
                self._send_json(HTTPStatus.OK, handle_checkpoints(paths=paths))
                return
            if parsed.path == "/api/wildcards":
                self._send_json(HTTPStatus.OK, handle_wildcards(paths=paths))
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
        parts = [part.strip() for part in value.split("|")]
        if len(parts) == 1:
            return T2ILoraConfig(path=parts[0])
        if len(parts) == 2:
            strength = float(parts[1])
            return T2ILoraConfig(path=parts[0], model_strength=strength, clip_strength=strength)
        if len(parts) == 3:
            return T2ILoraConfig(path=parts[0], model_strength=float(parts[1]), clip_strength=float(parts[2]))
        raise ValueError("lora spec must be path | path|strength | path|strength|strength")
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
        steps=int(value.get("steps", 12)),
        denoise=float(value.get("denoise", 0.35)),
        method=str(value.get("method", "bicubic")),
        tiled=bool(value.get("tiled", False)),
        tile_size=int(value.get("tile_size", 64)),
        overlap=int(value.get("overlap", 8)),
    )


def _vae_decode_from_payload(value: Any) -> VaeDecodeSettings:
    if not isinstance(value, dict):
        value = {}
    return VaeDecodeSettings(
        mode=str(value.get("mode", "auto")),
        tile_size=int(value.get("tile_size", 64)),
        overlap=int(value.get("overlap", 8)),
    )


def _face_detailer_from_payload(value: Any) -> FaceDetailerSettings:
    if not isinstance(value, dict):
        value = {}
    return FaceDetailerSettings(
        enabled=bool(value.get("enabled", False)),
        detector=str(value.get("detector", "default")),
        threshold=float(value.get("threshold", 0.5)),
        crop_scale=float(value.get("crop_scale", 1.5)),
        padding=int(value.get("padding", 32)),
        feather=int(value.get("feather", 24)),
        exclude_forehead_ratio=float(value.get("exclude_forehead_ratio", 0)),
        steps=int(value.get("steps", 12)),
        denoise=float(value.get("denoise", 0.28)),
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
    if name == "face-detailer-detectors":
        return "Face Detectors"
    return name


def _bounded_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        return 20
    return max(1, min(limit, 100))


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
