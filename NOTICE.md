# Notices

Anima APP is a standalone Anima image-generation app.

The project reuses selected, attributed runtime code from the verified local `AnimaStudio` app and from ComfyUI-derived runtime pieces. ComfyUI remains a development-time code/model source, not a live server dependency.

The `vendor/anima_runtime` tree contains ComfyUI-derived runtime code copied from the verified local `AnimaStudio` project. Keep source attribution and GPL-3.0-compatible notices with the copied files and in this document.

Optional face-detailer support adapts the detector/mask flow already proven in `AnimaStudio`, including NAI-FaceDetailer-style mask-grid alignment. Keep the upstream detector/runtime license notices with any redistributed build. The detector runtime uses local Ultralytics YOLO/SAM weights when available; Ultralytics license terms apply to that optional runtime path.

Local LoRA files imported into `models\loras` are user-provided local model artifacts. They are ignored by git and should not be redistributed without confirming their source license and permission.

The `wildcards` folder may include `.txt` prompt wildcard files copied from the local ComfyUI Impact Pack installation at `E:\ComfyUI_sage\ComfyUI\custom_nodes\comfyui-impact-pack\wildcards`. The observed upstream license file is GNU GPL version 3. Keep Impact Pack attribution and license notice with any redistributed build that includes those wildcard files.
