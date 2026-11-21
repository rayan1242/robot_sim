#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
venv="${SIM_VENV:-$HOME/robot_sim_perception_venv}"
case "${SIM_DEPTH_DEVICE:-cuda}" in
    cuda) wheel_variant=cu118 ;;
    cpu) wheel_variant=cpu ;;
    *) printf 'SIM_DEPTH_DEVICE must be cuda or cpu\n' >&2; exit 2 ;;
esac
python3 -m venv --system-site-packages "$venv"
"$venv/bin/python" -m pip install "torch==2.5.1+$wheel_variant" "torchvision==0.20.1+$wheel_variant" --index-url "https://download.pytorch.org/whl/$wheel_variant"
"$venv/bin/python" -m pip install 'transformers==4.52.4' 'pillow>=10,<12' 'numpy<2'
if [[ "$wheel_variant" == cu118 ]]; then
    "$venv/bin/python" -c 'import torch; torch.empty(1, device="cuda"); print(torch.cuda.get_device_name(0))'
fi
printf 'Depth environment ready: %s\n' "$venv"
