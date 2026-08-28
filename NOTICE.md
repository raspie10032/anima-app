# Notices

Anima APP is a lightweight local Anima image-generation app.

## Runtime Code

The `vendor/anima_runtime` tree contains a ComfyUI 0.22.2-derived runtime snapshot. The reported version is preserved in `vendor/anima_runtime/comfyui_version.py`; the exact upstream commit was not preserved. Keep the upstream license and attribution notices with redistributed source or packaged builds, and do not claim commit-level reproducibility for this snapshot.

Relevant upstream project:

- ComfyUI: https://github.com/comfyanonymous/ComfyUI

## Vendored Python Packages

The `vendor/python_packages` tree contains selected runtime packages and their metadata:

- `comfy-kitchen` 0.2.8, Apache-2.0, https://github.com/Comfy-Org/comfy-kitchen
- An Anima APP no-native compatibility shim based on `comfy-aimdo` 0.3.0, GPL-3.0, with repository metadata at https://github.com/Comfy-Org/comfy-aimdo

Keep each package's bundled license files and notices with redistributed builds.
The `comfy-aimdo` base version is retained in its metadata, but several Python modules and its `RECORD` are intentionally patched for Anima APP. See `vendor/README.md` for the exact disclosure and remaining native-binary boundary.

## Optional Detector Runtime

Face-detailer support can use Ultralytics YOLO/SAM detector assets when the optional `face-detailer` extra is installed.

The app can download detector weights into the user's local `models` tree:

- `face_yolov8n.pt` from `Bingsu/adetailer`.
- `full_eyes_detect_v1.pt` from `guon/hand-eyes`.
- `sam_b.pt` from Ultralytics assets, with SAM reference material from `facebookresearch/segment-anything`.
- `sam3.pt` from the gated `facebook/sam3` model repository.

Detector weights are not included in this repository. SAM3 access requires accepting the model repository's access conditions. Check each source model card, its access terms, and the optional Ultralytics runtime license before redistributing detector weights or packaged builds that include them.

## Model And LoRA Artifacts

Anima checkpoints are obtained from `circlestone-labs/Anima`, including the preferred Anima Aesthetic v1.1 profile. The model repository currently identifies its license as `circlestone-labs-non-commercial-license`.

Base model assets, alternate checkpoints, LoRA files, detector weights, input images, and generated output images are local user artifacts. They are ignored by git and are not part of the public source release. Review the upstream model license before using or redistributing any downloaded checkpoint.

## Wildcards

The `wildcards` folder includes text wildcard files copied or derived from a local ComfyUI Impact Pack checkout. The observed upstream license was GPL-3.0; the exact source revision was not preserved.

Relevant upstream project:

- ComfyUI Impact Pack: https://github.com/ltdrdata/ComfyUI-Impact-Pack

Keep Impact Pack attribution and the corresponding license notice with any redistributed build that includes derived wildcard files.
