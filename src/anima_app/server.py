from __future__ import annotations

import copy
import json
import re
import threading
import time
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
from anima_app.wildcards import expand_request_wildcards, list_wildcards


_INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
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
      grid-template-columns: minmax(300px, 360px) minmax(0, 1fr) minmax(280px, 340px);
      background: #18191f;
    }
    .control-frame,
    .history-frame {
      height: 100vh;
      min-width: 0;
      overflow: auto;
      background: #22252b;
      padding: 18px;
    }
    .control-frame {
      border-right: 1px solid #373b44;
    }
    .history-frame {
      border-left: 1px solid #373b44;
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
      font-size: 21px;
      margin: 0 0 12px;
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
      margin: 14px 0 6px;
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
      padding: 10px;
      font: inherit;
    }
    textarea {
      min-height: 104px;
      resize: vertical;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    button {
      width: 100%;
      margin-top: 18px;
      border: 0;
      border-radius: 6px;
      background: #d8b45f;
      color: #151515;
      padding: 11px 14px;
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
    .form-section {
      margin-top: 18px;
      padding-top: 14px;
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
    .toggle-switch {
      position: relative;
      display: grid;
      grid-template-columns: auto 1fr;
      align-items: center;
      gap: 10px;
      min-height: 48px;
      margin-top: 14px;
      padding: 10px;
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
    .preset-strip {
      margin: 12px 0;
      padding: 10px;
      border: 1px solid #373b44;
      border-radius: 6px;
      background: #171b22;
    }
    .preset-strip .row {
      margin-top: 0;
    }
    .control-groups {
      display: grid;
      gap: 10px;
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
      gap: 10px;
      padding: 11px 12px;
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
      padding: 0 12px 12px;
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
    <aside class="control-frame" aria-label="Generation controls">
      <h1>Anima APP</h1>
      <form id="generate-form"></form>
      <div id="control-groups" class="control-groups">
        <details class="control-group" data-control-group="prompt-generate" open>
          <summary>Prompt & Generate</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>Prompt</h2>
              <label for="prompt">Prompt</label>
              <textarea id="prompt" name="prompt" form="generate-form" required>anime portrait, clean lineart</textarea>
              <label for="negative">Negative</label>
              <input id="negative" name="negative_prompt" value="low quality" form="generate-form">
            </section>
            <section class="preset-strip" aria-label="Starting point presets">
              <h2>Starting Point</h2>
              <div class="row">
                <button type="button" id="preset-standard" class="secondary-button">Standard</button>
                <button type="button" id="preset-reference" class="secondary-button">Reference Quality</button>
              </div>
            </section>
            <section class="form-section">
              <h2>Generate</h2>
              <button id="generate-button" class="primary-action" type="submit" form="generate-form">Generate</button>
              <section class="auto-queue-panel" id="auto-queue-panel" aria-label="Auto queue">
                <h2>Auto Queue</h2>
                <div class="row">
                  <div>
                    <label for="queue-count">Queue Count</label>
                    <input id="queue-count" name="queue_count" type="number" min="1" max="99" value="4">
                  </div>
                  <div>
                    <label for="queue-seed-mode">Seed Mode</label>
                    <select id="queue-seed-mode" name="queue_seed_mode">
                      <option value="fixed">Fixed</option>
                      <option value="increment" selected>Increment</option>
                      <option value="random">Random</option>
                    </select>
                  </div>
                </div>
                <label for="queue-delay">Delay Seconds</label>
                <input id="queue-delay" name="queue_delay" type="number" min="0" max="60" step="0.5" value="0">
                <div class="queue-actions">
                  <button type="button" id="start-queue" class="secondary-button">Start Queue</button>
                  <button type="button" id="stop-queue" class="secondary-button" disabled>Stop</button>
                </div>
                <p id="queue-status" class="queue-status" aria-live="polite">Idle</p>
              </section>
            </section>
          </div>
        </details>
        <details class="control-group" data-control-group="model-style" open>
          <summary>Model & Style</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>LoRA Style</h2>
              <label for="checkpoint-select">Base Checkpoint</label>
              <select id="checkpoint-select" name="checkpoint" form="generate-form">
                <option value="__DEFAULT_T2I_CHECKPOINT__">__DEFAULT_T2I_CHECKPOINT__</option>
              </select>
              <div class="row">
                <div>
                  <label for="lora-select">Selected LoRA</label>
                  <select id="lora-select" name="lora_path" form="generate-form">
                    <option value="">None</option>
                  </select>
                </div>
                <div>
                  <label for="lora-strength">LoRA Strength</label>
                  <input id="lora-strength" name="lora_strength" type="number" min="0" step="0.05" value="1" form="generate-form">
                </div>
              </div>
            </section>
            <form id="lora-import-form" class="form-section">
              <h2>Import LoRA</h2>
              <label for="lora-path">Import LoRA File</label>
              <input id="lora-path" name="path" placeholder="D:\\Models\\style.safetensors">
              <button type="submit" class="secondary-button">Copy LoRA into App</button>
            </form>
          </div>
        </details>
        <details class="control-group" data-control-group="image-settings" open>
          <summary>Image Settings</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>Image Settings</h2>
              <div class="row">
                <div>
                  <label for="width">Width</label>
                  <input id="width" name="width" type="number" min="8" step="8" value="__DEFAULT_T2I_WIDTH__" form="generate-form">
                </div>
                <div>
                  <label for="height">Height</label>
                  <input id="height" name="height" type="number" min="8" step="8" value="__DEFAULT_T2I_HEIGHT__" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="steps">Steps</label>
                  <input id="steps" name="steps" type="number" min="1" value="__DEFAULT_T2I_STEPS__" form="generate-form">
                </div>
                <div>
                  <label for="cfg">CFG</label>
                  <input id="cfg" name="cfg" type="number" min="0" step="0.1" value="__DEFAULT_T2I_CFG__" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="sampler">Sampler</label>
                  <select id="sampler" name="sampler" form="generate-form">
                    <option value="euler_ancestral_cfg_pp" selected>Euler Ancestral CFG++</option>
                    <option value="euler">Euler Ancestral</option>
                    <option value="dpmpp_2m">DPM++ 2M</option>
                    <option value="dpmpp_sde">DPM++ SDE</option>
                  </select>
                </div>
                <div>
                  <label for="scheduler">Scheduler</label>
                  <select id="scheduler" name="scheduler" form="generate-form">
                    <option value="sgm_uniform" selected>SGM Uniform</option>
                    <option value="normal">Normal</option>
                    <option value="simple">Simple</option>
                    <option value="karras">Karras</option>
                  </select>
                </div>
              </div>
              <label for="seed">Seed</label>
              <input id="seed" name="seed" type="number" placeholder="random" form="generate-form">
            </section>
          </div>
        </details>
        <details class="control-group" data-control-group="enhance">
          <summary>Enhance</summary>
          <div class="control-group-body">
            <details id="reference-image-section" class="form-section">
              <summary>Reference Image and Upscale</summary>
              <label for="i2i-image">Reference Image Path</label>
              <input id="i2i-image" name="i2i_image" placeholder="inputs\\reference.png" form="generate-form">
              <div class="row">
                <label class="toggle-switch" for="upscale-enabled">
                  <input id="upscale-enabled" name="upscale_enabled" type="checkbox" value="1" form="generate-form">
                  <span class="toggle-track" aria-hidden="true"></span>
                  <span class="toggle-copy">
                    <span class="toggle-title">Enable Upscale</span>
                    <span class="toggle-state" aria-hidden="true"></span>
                  </span>
                </label>
                <label class="toggle-switch" for="upscale-tiled">
                  <input id="upscale-tiled" name="upscale_tiled" type="checkbox" value="1" form="generate-form">
                  <span class="toggle-track" aria-hidden="true"></span>
                  <span class="toggle-copy">
                    <span class="toggle-title">Tile Upscale</span>
                    <span class="toggle-state" aria-hidden="true"></span>
                  </span>
                </label>
              </div>
              <div class="row">
                <div>
                  <label for="i2i-denoise">Image Denoise</label>
                  <input id="i2i-denoise" name="i2i_denoise" type="number" min="0" max="1" step="0.05" value="0.35" form="generate-form">
                </div>
                <div>
                  <label for="upscale-scale">Upscale Scale</label>
                  <input id="upscale-scale" name="upscale_scale" type="number" min="0.1" step="0.1" value="1.5" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="upscale-steps">Upscale Steps</label>
                  <input id="upscale-steps" name="upscale_steps" type="number" min="1" value="12" form="generate-form">
                </div>
                <div>
                  <label for="upscale-denoise">Upscale Denoise</label>
                  <input id="upscale-denoise" name="upscale_denoise" type="number" min="0" max="1" step="0.01" value="0.35" form="generate-form">
                </div>
              </div>
              <label for="upscale-method">Upscale Method</label>
              <select id="upscale-method" name="upscale_method" form="generate-form">
                <option value="bicubic">Bicubic</option>
                <option value="bilinear">Bilinear</option>
                <option value="nearest-exact">Nearest Exact</option>
                <option value="area">Area</option>
              </select>
              <div class="row">
                <div>
                  <label for="upscale-tile-size">Upscale Tile</label>
                  <input id="upscale-tile-size" name="upscale_tile_size" type="number" min="1" value="64" form="generate-form">
                </div>
                <div>
                  <label for="upscale-overlap">Upscale Overlap</label>
                  <input id="upscale-overlap" name="upscale_overlap" type="number" min="0" value="8" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="vae-decode-mode">VAE Decode</label>
                  <select id="vae-decode-mode" name="vae_decode_mode" form="generate-form">
                    <option value="auto">Auto</option>
                    <option value="tiled">Tiled</option>
                    <option value="standard">Standard</option>
                  </select>
                </div>
                <div>
                  <label for="vae-tile-size">VAE Tile</label>
                  <input id="vae-tile-size" name="vae_tile_size" type="number" min="1" value="64" form="generate-form">
                </div>
              </div>
              <label for="vae-overlap">VAE Overlap</label>
              <input id="vae-overlap" name="vae_overlap" type="number" min="0" value="8" form="generate-form">
            </details>
            <details id="face-detailer-section" class="form-section">
              <summary>Face Detailer</summary>
              <label class="toggle-switch" for="face-detailer-enabled">
                <input id="face-detailer-enabled" name="face_detailer_enabled" type="checkbox" value="1" form="generate-form">
                <span class="toggle-track" aria-hidden="true"></span>
                <span class="toggle-copy">
                  <span class="toggle-title">Enable Face Detailer</span>
                  <span class="toggle-state" aria-hidden="true"></span>
                </span>
              </label>
              <label for="face-detector">Face Detector</label>
              <input id="face-detector" name="face_detector" value="default" form="generate-form">
              <div class="row">
                <div>
                  <label for="face-threshold">Face Threshold</label>
                  <input id="face-threshold" name="face_threshold" type="number" min="0" max="1" step="0.01" value="0.5" form="generate-form">
                </div>
                <div>
                  <label for="face-denoise">Face Denoise</label>
                  <input id="face-denoise" name="face_denoise" type="number" min="0" max="1" step="0.01" value="0.28" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="face-steps">Face Steps</label>
                  <input id="face-steps" name="face_steps" type="number" min="1" value="12" form="generate-form">
                </div>
                <div>
                  <label for="face-crop-scale">Face Crop</label>
                  <input id="face-crop-scale" name="face_crop_scale" type="number" min="0.1" step="0.05" value="1.5" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="face-padding">Face Padding</label>
                  <input id="face-padding" name="face_padding" type="number" min="0" value="32" form="generate-form">
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="face-feather">Face Feather</label>
                  <input id="face-feather" name="face_feather" type="number" min="0" value="24" form="generate-form">
                </div>
                <div>
                  <label for="face-exclude-forehead">Forehead Exclude</label>
                  <input id="face-exclude-forehead" name="face_exclude_forehead" type="number" min="0" max="0.75" step="0.01" value="0" form="generate-form">
                </div>
              </div>
            </details>
          </div>
        </details>
        <details class="control-group" data-control-group="prompt-tools">
          <summary>Prompt Tools</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>Prompt Tools</h2>
              <label for="wildcard-mode">Wildcard Mode</label>
              <select id="wildcard-mode" name="wildcard_mode" form="generate-form">
                <option value="random" selected>Random</option>
                <option value="sequential">Sequential</option>
                <option value="reverse">Reverse</option>
              </select>
              <label for="wildcard-select">Insert Wildcard</label>
              <div class="row">
                <select id="wildcard-select">
                  <option value="">No wildcard files</option>
                </select>
                <button type="button" id="insert-wildcard" class="secondary-button">Insert</button>
              </div>
            </section>
          </div>
        </details>
        <details class="control-group" data-control-group="settings">
          <summary>Settings</summary>
          <div class="control-group-body">
            <section class="form-section">
              <h2>Saved Settings</h2>
              <label for="preset-name">Settings Name</label>
              <input id="preset-name" placeholder="portrait draft">
              <label for="preset-select">Saved Settings</label>
              <select id="preset-select">
                <option value="">No saved presets</option>
              </select>
              <div class="row">
                <button type="button" id="save-preset" class="secondary-button">Save Settings</button>
                <button type="button" id="apply-preset" class="secondary-button">Load Settings</button>
              </div>
              <input id="preset-import-file" type="file" accept="application/json,.json" hidden>
              <div class="row">
                <button type="button" id="export-presets" class="secondary-button">Export Settings</button>
                <button type="button" id="import-presets" class="secondary-button">Import Settings</button>
              </div>
            </section>
          </div>
        </details>
      </div>
    </aside>
    <main class="workspace-frame" aria-label="Image workspace">
      <section class="generation-stages compact" id="generation-stages" aria-live="polite" aria-busy="false" hidden>
        <div class="stage-header">
          <strong>Generation</strong>
          <span id="generation-stage-summary">Idle</span>
        </div>
        <ol class="stage-list" id="generation-stage-list"></ol>
      </section>
      <section class="result-panel" aria-label="Current result">
        <div class="result-header">
          <h2 id="result-title">Current Result</h2>
          <span id="result-status">Ready</span>
        </div>
        <div id="result-summary" class="result-summary"></div>
        <img id="preview" alt="" hidden>
        <div class="result-actions">
          <a id="output-link" href="" hidden>Open Output</a>
          <button type="button" id="apply-manifest" class="secondary-button">Use Current Manifest</button>
        </div>
        <details class="result-json">
          <summary>Manifest JSON</summary>
          <pre id="result">Ready.</pre>
        </details>
      </section>
    </main>
    <aside class="history-frame" aria-label="Generation history">
      <details class="side-status-panel" id="side-status-panel">
        <summary>Runtime Status</summary>
        <section class="status-panel compact" id="status-panel" aria-label="Runtime status"></section>
        <section class="readiness-panel compact" id="readiness-panel" aria-label="Model readiness"></section>
      </details>
      <h2 class="frame-title">History</h2>
      <section class="history-panel" aria-label="Recent generations">
        <div class="history-header">
          <h2>Recent</h2>
          <span id="history-count">0 results</span>
        </div>
        <div class="history-tabs" role="group" aria-label="History filters">
          <button type="button" class="history-filter active" data-history-filter="all">All</button>
          <button type="button" class="history-filter" data-history-filter="images">Images</button>
          <button type="button" class="history-filter" data-history-filter="dry-run">Dry-run</button>
        </div>
        <section class="history" id="history" aria-label="History cards"></section>
      </section>
    </aside>
  </div>
  <script>
    const form = document.getElementById("generate-form");
    const loraImportForm = document.getElementById("lora-import-form");
    const generateButton = document.getElementById("generate-button");
    const autoQueuePanel = document.getElementById("auto-queue-panel");
    const queueCountInput = document.getElementById("queue-count");
    const queueSeedMode = document.getElementById("queue-seed-mode");
    const queueDelayInput = document.getElementById("queue-delay");
    const startQueueButton = document.getElementById("start-queue");
    const stopQueueButton = document.getElementById("stop-queue");
    const queueStatus = document.getElementById("queue-status");
    const result = document.getElementById("result");
    const resultTitle = document.getElementById("result-title");
    const resultStatus = document.getElementById("result-status");
    const resultSummary = document.getElementById("result-summary");
    const preview = document.getElementById("preview");
    const outputLink = document.getElementById("output-link");
    const statusPanel = document.getElementById("status-panel");
    const readinessPanel = document.getElementById("readiness-panel");
    const generationStages = document.getElementById("generation-stages");
    const generationStageList = document.getElementById("generation-stage-list");
    const generationStageSummary = document.getElementById("generation-stage-summary");
    const history = document.getElementById("history");
    const historyCount = document.getElementById("history-count");
    const historyFilters = [...document.querySelectorAll("[data-history-filter]")];
    const checkpointSelect = document.getElementById("checkpoint-select");
    const loraSelect = document.getElementById("lora-select");
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
    const standardPresetButton = document.getElementById("preset-standard");
    const referencePresetButton = document.getElementById("preset-reference");
    const referenceImageSection = document.getElementById("reference-image-section");
    const faceDetailerSection = document.getElementById("face-detailer-section");
    let presets = [];
    let currentManifest = null;
    let historyItems = [];
    let historyFilter = "all";
    let stageTimer = null;
    let stageHideTimer = null;
    let progressPollTimer = null;
    let activeProgressId = "";
    let activeStageItems = [];
    let activeStageIndex = 0;
    let queueRunning = false;
    let queueStopRequested = false;
    let queueCompleted = 0;
    let queueFailed = 0;
    const stageStateLabels = {
      pending: "Waiting",
      active: "Running",
      completed: "Done",
      skipped: "Skipped",
      failed: "Failed"
    };
    const stageVisibleStateLabels = {
      pending: "",
      active: "Running",
      completed: "",
      skipped: "",
      failed: "Failed"
    };
    const quickPresets = {
      standard: {
        name: "standard",
        request: {
          width: __DEFAULT_T2I_WIDTH__,
          height: __DEFAULT_T2I_HEIGHT__,
          steps: __DEFAULT_T2I_STEPS__,
          cfg: __DEFAULT_T2I_CFG__,
          sampler: "__DEFAULT_T2I_SAMPLER__",
          scheduler: "__DEFAULT_T2I_SCHEDULER__",
          i2i: {image_path: "", denoise: 0.35},
          upscale: {
            enabled: false,
            scale: 1.5,
            steps: 12,
            denoise: 0.35,
            method: "bicubic",
            tiled: false,
            tile_size: 64,
            overlap: 8
          },
          vae_decode: {mode: "auto", tile_size: 64, overlap: 8},
          face_detailer: {
            enabled: false,
            detector: "default",
            threshold: 0.5,
            crop_scale: 1.5,
            padding: 32,
            feather: 24,
            exclude_forehead_ratio: 0,
            steps: 12,
            denoise: 0.28
          }
        }
      },
      reference_quality: {
        name: "reference quality",
        request: {
          width: 768,
          height: 1152,
          steps: 24,
          cfg: 3.5,
          sampler: "euler_ancestral_cfg_pp",
          scheduler: "sgm_uniform",
          i2i: {image_path: "", denoise: 0.35},
          upscale: {
            enabled: true,
            scale: 1.5,
            steps: 10,
            denoise: 0.28,
            method: "bicubic",
            tiled: true,
            tile_size: 64,
            overlap: 8
          },
          vae_decode: {mode: "tiled", tile_size: 96, overlap: 16},
          face_detailer: {
            enabled: true,
            detector: "default",
            threshold: 0.08,
            crop_scale: 1.35,
            padding: 24,
            feather: 12,
            exclude_forehead_ratio: 0.12,
            steps: 4,
            denoise: 0.10
          }
        }
      }
    };
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
    function readinessActionLabel(profile) {
      if (profile.ready) {
        return "Ready";
      }
      return profile.name === "face-detailer-detectors" ? "Copy Detectors" : "Copy / Download";
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
        summary.textContent = profile.ready ? "Ready" : `${profile.missing_count} missing`;
        const files = document.createElement("ul");
        files.className = "readiness-files";
        for (const item of profile.files || []) {
          const file = document.createElement("li");
          file.textContent = `${item.exists ? "ok" : "missing"} ${item.relative_path}`;
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
      button.textContent = "Preparing...";
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
        return "Failed";
      }
      if (payload?.dry_run || payload?.status === "dry_run") {
        return "Dry run";
      }
      if (payload?.status) {
        return payload.status;
      }
      return "Ready";
    }
    function renderResultSummary(payload = null) {
      if (!payload) {
        resultTitle.textContent = "Current Result";
        resultStatus.textContent = "Ready";
        resultSummary.replaceChildren(summaryItem("Status", "Ready"));
        return;
      }
      if (payload.error) {
        resultTitle.textContent = "Request Failed";
        resultStatus.textContent = "Failed";
        resultSummary.replaceChildren(summaryItem("Error", payload.error));
        return;
      }
      const size = payload.width && payload.height ? `${payload.width}x${payload.height}` : "unknown";
      const seed = payload.seed ?? "random";
      const upscale = payload.upscale?.enabled ? `${payload.upscale.scale || 1}x${payload.upscale.tiled ? " tiled" : ""}` : "off";
      const face = payload.face_detailer?.enabled ? `${payload.face_detailer.steps || "auto"} steps` : "off";
      resultTitle.textContent = payload.prompt || "Current Result";
      resultStatus.textContent = resultMode(payload);
      const items = [
        summaryItem("Status", resultMode(payload)),
        summaryItem("Size", size),
        summaryItem("Steps / CFG", `${payload.steps ?? "?"} / ${payload.cfg ?? "?"}`),
        summaryItem("Sampler", payload.sampler || "?"),
        summaryItem("Seed", seed)
      ];
      if (payload.upscale?.enabled) {
        items.push(summaryItem("Upscale", upscale));
      }
      if (payload.face_detailer?.enabled) {
        items.push(summaryItem("Face Detailer", face));
      }
      resultSummary.replaceChildren(...items);
    }
    function setResultPayload(payload) {
      result.textContent = JSON.stringify(payload, null, 2);
      renderResultSummary(payload);
    }
    function setResultMessage(message) {
      result.textContent = message;
      resultTitle.textContent = "Current Result";
      resultStatus.textContent = message;
      resultSummary.replaceChildren(summaryItem("Status", message));
    }
    function buildGenerationStages(data) {
      return [
        {key: "request", label: "Request"},
        {key: "wildcards", label: "Prompt / Wildcards"},
        {key: "text_encode", label: "Text Encode"},
        {key: "base_t2i", label: "Base Render"},
        {key: "high_res_fix", label: "High-res / Upscale", optional: !data.upscale?.enabled},
        {key: "vae_decode", label: "VAE Decode"},
        {key: "face_detailer", label: "Face Detailer", optional: !data.face_detailer?.enabled},
        {key: "metadata", label: "Save Metadata"}
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
      generationStageSummary.textContent = finalState === "running" ? "Working" : (finalState === "failed" ? (message ? `Failed: ${message}` : "Failed") : "");
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
        select.add(new Option(`${value} (missing)`, value));
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
    async function loadStatus() {
      const [healthResponse, loraResponse, checkpointResponse, readinessResponse] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/loras"),
        fetch("/api/checkpoints"),
        fetch("/api/readiness")
      ]);
      const health = await healthResponse.json();
      const loras = await loraResponse.json();
      const checkpoints = await checkpointResponse.json();
      const readiness = await readinessResponse.json();
      const selectedCheckpoint = checkpointSelect.value;
      const selectedLora = loraSelect.value;
      renderCheckpointOptions(checkpoints, selectedCheckpoint);
      loraSelect.replaceChildren(new Option("None", ""), ...loras.items.map((item) => new Option(item.relative_path, item.relative_path)));
      if ([...loraSelect.options].some((option) => option.value === selectedLora)) {
        loraSelect.value = selectedLora;
      }
      statusPanel.replaceChildren(
        statusCard("Model", health.models.ready ? "ready" : `${health.models.missing.length} missing`),
        statusCard("Checkpoints", `${checkpoints.count} local`),
        statusCard("LoRA", `${loras.count} available`),
        statusCard("Output", health.outputs.image_root)
      );
      renderReadiness(readiness);
    }
    function historyType(item) {
      return item.output_url ? "images" : "dry-run";
    }
    function historyTypeLabel(item) {
      return item.output_url ? "Image" : "Dry-run";
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
        placeholder.textContent = "Manifest";
        card.append(placeholder);
      }
      const body = document.createElement("div");
      body.className = "history-card-body";
      const title = document.createElement("strong");
      title.textContent = item.prompt || "(empty prompt)";
      const type = document.createElement("span");
      type.className = "history-type";
      type.textContent = historyTypeLabel(item);
      const meta = document.createElement("span");
      meta.textContent = `${item.status || "unknown"} / ${item.output_url || "manifest only"}`;
      body.append(title, type, meta);
      card.append(body);
      const actions = document.createElement("div");
      actions.className = "history-actions";
      actions.addEventListener("click", (event) => event.stopPropagation());
      const manifestButton = document.createElement("button");
      manifestButton.type = "button";
      manifestButton.className = "history-action";
      manifestButton.textContent = "Manifest";
      manifestButton.title = "Open manifest details";
      manifestButton.addEventListener("click", () => openManifest(manifestName));
      actions.append(manifestButton);
      if (item.output_url) {
        const openOutput = document.createElement("a");
        openOutput.className = "history-action";
        openOutput.href = item.output_url;
        openOutput.target = "_blank";
        openOutput.rel = "noopener";
        openOutput.textContent = "Open";
        openOutput.title = "Open output image";
        actions.append(openOutput);
      }
      const exportButton = document.createElement("button");
      exportButton.type = "button";
      exportButton.className = "history-action";
      exportButton.textContent = "Export";
      exportButton.title = "Download manifest JSON";
      exportButton.addEventListener("click", () => exportManifest(manifestName));
      actions.append(exportButton);
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "history-action danger";
      deleteButton.textContent = "Delete";
      deleteButton.title = "Delete manifest and managed output image";
      deleteButton.addEventListener("click", () => deleteHistoryItem(manifestName));
      actions.append(deleteButton);
      card.append(actions);
      card.addEventListener("click", () => openManifest(manifestName));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openManifest(manifestName);
        }
      });
      return card;
    }
    function renderHistory() {
      const visibleItems = filteredHistoryItems();
      historyFilters.forEach((button) => {
        button.classList.toggle("active", button.dataset.historyFilter === historyFilter);
      });
      historyCount.textContent = `${visibleItems.length} / ${historyItems.length} shown`;
      if (!visibleItems.length) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        empty.textContent = "No matching history yet.";
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
    async function openManifest(name) {
      const response = await fetch("/api/manifests/" + encodeURIComponent(name));
      const payload = await response.json();
      currentManifest = payload;
      setResultPayload(payload);
      clearOutputPreview();
      if (payload.output_url) {
        showOutputPreview(payload.output_url);
      }
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
      if (!window.confirm(`Delete ${name} and its managed output image if present?`)) {
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
        new Option(presets.length ? "Select preset" : "No saved presets", ""),
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
      wildcardSelect.replaceChildren(
        new Option(items.length ? "Select wildcard" : "No wildcard files", ""),
        ...items.map((item) => new Option(`${item.name} (${item.value_count})`, item.token))
      );
    }
    function insertWildcard() {
      const token = wildcardSelect.value;
      if (!token) {
        return;
      }
      const prompt = form.elements.prompt;
      const start = prompt.selectionStart ?? prompt.value.length;
      const end = prompt.selectionEnd ?? prompt.value.length;
      const before = prompt.value.slice(0, start);
      const after = prompt.value.slice(end);
      prompt.value = before + token + after;
      const nextCursor = start + token.length;
      prompt.focus();
      prompt.setSelectionRange(nextCursor, nextCursor);
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
      if (data.lora_path) {
        const strength = Number(data.lora_strength || 1);
        data.loras = [{path: data.lora_path, model_strength: strength, clip_strength: strength}];
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
      const lora = (request.loras || [])[0] || {};
      form.elements.lora_path.value = lora.path || "";
      form.elements.lora_strength.value = lora.model_strength ?? 1;
      presetName.value = item.name || "";
    }
    function applyQuickPreset(key) {
      const preset = quickPresets[key];
      if (!preset) {
        return;
      }
      const current = buildRequestData();
      const fallbackPrompt = form.elements.prompt.defaultValue;
      const fallbackNegativePrompt = form.elements.negative_prompt.defaultValue;
      const request = {
        prompt: current.prompt.trim() ? current.prompt : fallbackPrompt,
        negative_prompt: current.negative_prompt.trim() ? current.negative_prompt : fallbackNegativePrompt,
        wildcard_mode: current.wildcard_mode,
        seed: current.seed,
        checkpoint: current.checkpoint || "__DEFAULT_T2I_CHECKPOINT__",
        loras: current.loras || [],
        ...preset.request
      };
      applyPreset({name: preset.name, request});
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
    function queueDelayMs() {
      const value = Number(queueDelayInput.value || 0);
      return Math.max(0, Math.min(60, Number.isFinite(value) ? value : 0)) * 1000;
    }
    function sleep(ms) {
      return new Promise((resolve) => window.setTimeout(resolve, ms));
    }
    function setQueueStatus(message) {
      queueStatus.textContent = message;
    }
    function setQueueControlsRunning(running) {
      queueRunning = running;
      queueCountInput.disabled = running;
      queueSeedMode.disabled = running;
      queueDelayInput.disabled = running;
      startQueueButton.disabled = running;
      stopQueueButton.disabled = !running;
      generateButton.disabled = running;
    }
    function queueSeedForIndex(baseSeed, index, originalSeedProvided) {
      const mode = queueSeedMode.value;
      if (mode === "random") {
        return Math.floor(Math.random() * 2147483647);
      }
      if (mode === "increment") {
        const seed = Number.isFinite(baseSeed) ? baseSeed : Math.floor(Date.now() % 2147483647);
        return seed + index;
      }
      if (mode === "fixed" && originalSeedProvided && Number.isFinite(baseSeed)) {
        return baseSeed;
      }
      return null;
    }
    async function submitGenerateRequest(data, message = "Generating...") {
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
    async function runQueuedGenerate(baseData, index, total, baseSeed, originalSeedProvided) {
      const data = JSON.parse(JSON.stringify(baseData));
      const seed = queueSeedForIndex(baseSeed, index, originalSeedProvided);
      if (seed === null) {
        delete data.seed;
      } else {
        data.seed = seed;
      }
      setQueueStatus(`Running ${index + 1} / ${total}...`);
      const result = await submitGenerateRequest(data, `Queue ${index + 1} / ${total} generating...`);
      if (result.ok) {
        queueCompleted += 1;
      } else {
        queueFailed += 1;
      }
      setQueueStatus(`Done ${queueCompleted}, failed ${queueFailed}, remaining ${Math.max(0, total - index - 1)}`);
      return result;
    }
    async function startAutoQueue() {
      if (queueRunning) {
        return;
      }
      const total = queueCount();
      const delay = queueDelayMs();
      const baseData = buildRequestData();
      const originalSeedProvided = Object.prototype.hasOwnProperty.call(baseData, "seed");
      const baseSeed = originalSeedProvided ? Number(baseData.seed) : null;
      queueCompleted = 0;
      queueFailed = 0;
      queueStopRequested = false;
      setQueueControlsRunning(true);
      setQueueStatus(`Queued ${total} jobs`);
      try {
        for (let index = 0; index < total; index += 1) {
          if (queueStopRequested) {
            break;
          }
          await runQueuedGenerate(baseData, index, total, baseSeed, originalSeedProvided);
          if (!queueStopRequested && index < total - 1 && delay > 0) {
            setQueueStatus(`Waiting ${delay / 1000}s before ${index + 2} / ${total}...`);
            await sleep(delay);
          }
        }
      } finally {
        const stopped = queueStopRequested;
        setQueueControlsRunning(false);
        queueStopRequested = false;
        setQueueStatus(stopped ? `Stopped. Done ${queueCompleted}, failed ${queueFailed}.` : `Queue complete. Done ${queueCompleted}, failed ${queueFailed}.`);
      }
    }
    function stopAutoQueue() {
      if (!queueRunning) {
        return;
      }
      queueStopRequested = true;
      stopQueueButton.disabled = true;
      setQueueStatus("Stopping after current job...");
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (queueRunning) {
        return;
      }
      const button = generateButton;
      button.disabled = true;
      await submitGenerateRequest(buildRequestData(), "Generating...");
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
    standardPresetButton.addEventListener("click", () => applyQuickPreset("standard"));
    referencePresetButton.addEventListener("click", () => applyQuickPreset("reference_quality"));
    applyManifestButton.addEventListener("click", applyManifest);
    insertWildcardButton.addEventListener("click", insertWildcard);
    startQueueButton.addEventListener("click", () => {
      startAutoQueue().catch((error) => {
        setQueueControlsRunning(false);
        setQueueStatus(`Queue failed: ${String(error)}`);
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
    "request": "Request",
    "wildcards": "Prompt / Wildcards",
    "text_encode": "Text Encode",
    "base_t2i": "Base Render",
    "high_res_fix": "High-res / Upscale",
    "vae_decode": "VAE Decode",
    "face_detailer": "Face Detailer",
    "metadata": "Save Metadata",
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
                "summary": "Starting",
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
            item["summary"] = "Complete"
            item["result"] = copy.deepcopy(result)
            item["stages"] = _completed_progress_stages(item["stages"], result.get("stages", {}))
            item["updated_at"] = time.time()

    def fail(self, progress_id: str, error: str) -> None:
        with self._lock:
            item = self._items.get(progress_id)
            if item is None:
                return
            item["status"] = "failed"
            item["summary"] = f"Failed: {error}"
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
        progress_store.update_summary(progress_id, "Validating request")
    try:
        request = request_from_payload(payload)
        if progress_store is not None and progress_id is not None:
            progress_store.update_stage(progress_id, "request", "completed")
            progress_store.update_stage(progress_id, "wildcards", "active")
            progress_store.update_summary(progress_id, "Preparing prompt")
        wildcard_mode = str(payload.get("wildcard_mode", payload.get("wildcards", "random")))
        request, wildcard_expansion = expand_request_wildcards(request, paths=paths, mode=wildcard_mode)
        if progress_store is not None and progress_id is not None:
            progress_store.update_stage(progress_id, "wildcards", "completed", mode=wildcard_expansion.get("mode", "random"))
            progress_store.update_stage(progress_id, "text_encode", "completed")
            progress_store.update_stage(progress_id, "base_t2i", "active")
            progress_store.update_summary(progress_id, "Rendering")
        dry_run = bool(payload.get("dry_run", default_dry_run))
        result = run_t2i(request, paths=paths, dry_run=dry_run, renderer=None if dry_run else renderer, wildcards=wildcard_expansion)
        manifest = read_manifest(result.manifest_path)
        output_path = str(result.output_path) if result.output_path else None
        response = {
            "status": result.status,
            "manifest_path": str(result.manifest_path),
            "output_path": output_path,
            "output_url": _output_url(result.output_path, paths) if result.output_path else None,
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
    return {"count": len(items), "items": items}


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
            if parsed.path not in {"/api/generate", "/api/loras/import", "/api/presets", "/api/presets/import", "/api/models/prepare"}:
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

    return ThreadingHTTPServer((host, port), AnimaRequestHandler)


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
