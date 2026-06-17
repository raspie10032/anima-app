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

Face-detailer support can use local Ultralytics YOLO/SAM detector assets when the optional `face-detailer` extra is installed and the user provides compatible detector files.

Detector weights are user-provided local artifacts. They are not included in this repository and should not be redistributed without checking their source license.

## Model And LoRA Artifacts

Base model assets, alternate checkpoints, LoRA files, input images, and generated output images are local user artifacts. They are ignored by git and are not part of the public source release.

## Wildcards

The `wildcards` folder may include text wildcard files derived from ComfyUI Impact Pack wildcard files.

Relevant upstream project:

- ComfyUI Impact Pack: https://github.com/ltdrdata/ComfyUI-Impact-Pack

Keep Impact Pack attribution and the corresponding license notice with any redistributed build that includes derived wildcard files.
