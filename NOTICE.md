# Notices

Anima APP is a lightweight local Anima image-generation app.

## Runtime Code

The `vendor/anima_runtime` tree contains ComfyUI-derived runtime code. Keep the upstream license and attribution notices with redistributed source or packaged builds.

Relevant upstream project:

- ComfyUI: https://github.com/comfyanonymous/ComfyUI

## Vendored Python Packages

The `vendor/python_packages` tree contains selected runtime packages and their metadata:

- `comfy-kitchen` 0.2.8, Apache-2.0, https://github.com/Comfy-Org/comfy-kitchen
- `comfy-aimdo` 0.3.0, repository metadata at https://github.com/Comfy-Org/comfy-aimdo

Keep each package's bundled license files and notices with redistributed builds.

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

The `wildcards` folder may include text wildcard files derived from ComfyUI Impact Pack wildcard files.

Relevant upstream project:

- ComfyUI Impact Pack: https://github.com/ltdrdata/ComfyUI-Impact-Pack

Keep Impact Pack attribution and the corresponding license notice with any redistributed build that includes derived wildcard files.
