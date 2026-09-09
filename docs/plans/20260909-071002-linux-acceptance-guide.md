# vsummary Linux 验收指南(4070m 游戏本 / Ubuntu)

> 配套:`docs/plans/20260909-022541-linux-support.md`(实现计划)与 `feature/linux-support` 分支。
> 目标:在 Intel/AMD + NVIDIA RTX 4070m Laptop GPU 的 Ubuntu 笔记本上,把 vsummary 源码版从零装起来,跑通端到端链路,产出可勾选的验收证据。

## 0. 适用环境

| 项 | 期望 |
|---|---|
| 系统 | Ubuntu 24.04 LTS(22.04 / Debian 12 也可) |
| CPU | x86_64,任意(本次走 GPU) |
| GPU | NVIDIA RTX 4070m(任何支持 CUDA 12 的 NVIDIA 卡都行) |
| 驱动 | `nvidia-smi` 可用,Driver ≥ 535(推荐 555 / 560) |
| CUDA | 系统级 CUDA 12 runtime(由 NVIDIA 驱动自带的 userland runtime 即可,**不一定**要 `nvcc`) |
| 磁盘 | ≥ 30 GB free(`videos/`、`workspace/`、`data/models/faster-whisper`、`data/models/fastembed` 等会持续增长) |
| 网络 | 国内:可访问 `hf-mirror.com`;海外:可访问 `huggingface.co`(在 `.env` 用 `HF_ENDPOINT` 切换) |

## 1. 前置:系统依赖

```bash
sudo apt update
sudo apt install -y \
  ffmpeg libsm6 libxrender1 libxext6 \
  python3-tk curl jq \
  wget ca-certificates
```

预期:
- `ffmpeg -version` 输出 ≥ 6.x
- `python3 -c "import tkinter; print('tk ok')"` 在系统 python 报 `tk ok`(conda 环境里的 python 不共用此包,稍后会单独装)

### 1.1 NVIDIA 驱动与 CUDA

```bash
nvidia-smi
# 期望首行: NVIDIA-SMI 555.xx  Driver Version: 555.xx  CUDA Version: 12.x
ls /usr/local/cuda 2>/dev/null   # 可选;只有装了 toolkit 才有
```

若 `nvidia-smi` 不存在或版本太老:
```bash
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers autoinstall    # 或 sudo apt install nvidia-driver-560
sudo reboot
```

## 2. 装 conda 与创建环境

```bash
# Miniconda 安装到 ~/miniconda3
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p "$HOME/miniconda3"
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda init bash
exec "$SHELL" -l
```

### 2.1 关键:Python 版本必须 3.11

`environment.yml` 锁 `python=3.11`。`requirements.txt` 里的 `litellm==1.74.0` 与 `onnxruntime-gpu<1.27` 在 cp311 上才有官方 cu12 wheel,**不要**用系统 python 或 pyenv/uv 装。

### 2.2 GPU 环境(GPU 包)

```bash
git clone https://github.com/Sticky-Finger/vsummary.git
cd vsummary
git checkout feature/linux-support   # 或者 main(合入之后)
conda env create -f environment.yml
conda activate vsummary
python -c "import sys; print(sys.version)"   # 必须 3.11.x
```

### 2.3 验证 Python 侧 CUDA 工具

```bash
python - <<'PY'
import importlib.metadata as m
for name in ("onnxruntime-gpu", "fastembed-gpu", "nvidia-cublas-cu12",
             "nvidia-cudnn-cu12", "nvidia-cuda-runtime-cu12"):
    print(name, m.version(name))
PY
```

期望:每个包都打出版本号,无 `PackageNotFoundError`。

```bash
python -c "import onnxruntime as ort; print('providers:', ort.get_available_providers())"
# 期望:包含 'CUDAExecutionProvider'
```

## 3. 拉前端依赖

```bash
( cd src/frontend && npm install )
```

期望:无 `EACCES` / `EAI_AGAIN`。**不要用 root**,否则 `node_modules` 权限会让后续 `npm run dev` 失败。

## 4. 配置文件

```bash
cp .env.example .env
cp config/settings.toml.example config/settings.toml
```

`.env` 至少填:
```
OPENAI_API_KEY=sk-...
OPENAI_PROVIDER=openai_compatible
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
HF_ENDPOINT=https://hf-mirror.com
```

`config/settings.toml` GPU 关键字段:
```toml
[asr]
provider = "faster_whisper"

[asr.faster_whisper]
device = "gpu"
compute_type = "float16"

[agent_retrieval]
embedding_device = "gpu"
```

## 5. 启动

```bash
chmod +x start.sh
bash -n start.sh && echo "shell syntax OK"
./start.sh
```

启动脚本会:
1. 探测 conda 与 `vsummary` 环境
2. 用 Python `socket.connect` 探测 8001/4173 端口占用
3. 后端 nohup 写到 `data/logs/backend.log`
4. 前端 nohup 写到 `data/logs/frontend.log`
5. 用 `xdg-open` 打开 `http://127.0.0.1:4173`

如 `xdg-open` 缺失(GNOME 默认有),回退 `$BROWSER`,都没有则只打 URL。

## 6. 验收清单

> 每个验收项都给出**通过判据** + **如何取证**(命令或 UI 路径)。失败时给出**回退指引**。

### 6.1 启动层

- [ ] **A1.** `./start.sh` 退出码 0;两端口都有 nohup 进程。
  - 取证:`pgrep -af 'backend.api.http.server'`,`pgrep -af 'vite'`,`ss -ltn | grep -E '4173|8001'`
- [ ] **A2.** 后端日志无 traceback。
  - 取证:`tail -n 200 data/logs/backend.log | grep -ci traceback` == 0
- [ ] **A3.** 前端 vite 起来后日志里包含 `Local:   http://127.0.0.1:4173/`。
  - 取证:`grep -c 'http://127.0.0.1:4173' data/logs/frontend.log` ≥ 1
- [ ] **A4.** `GET /api/health` 返回 `{"status":"ok"}`。
  - 取证:`curl -s http://127.0.0.1:8001/api/health`
- [ ] **A5.** 前端代理 `/api`、`/mcp` 透传到后端。
  - 取证:`curl -sI http://127.0.0.1:4173/api/health | head -1` 应为 `HTTP/1.1 200`

### 6.2 UI 可用性(浏览器)

- [ ] **B1.** `http://127.0.0.1:4173` 主页加载,无 console error。
- [ ] **B2.** 主题切换生效(亮/暗)。
- [ ] **B3.** 设置页写入一段 `talk_custom_prompt`,刷新后仍存在。
- [ ] **B4.** 「本机文件选择」能弹出原生文件框(需 `python3-tk`)。
  - 取证:点击 UI 按钮,GUI 出现;在 conda 环境里 `python -c "import tkinter; tkinter.Tk().destroy()"` 不报错。
- [ ] **B5.** 「本机能力」展示:
  - `platform = linux`
  - `accelerator = nvidia`
  - `nvidia_cuda_available = true`
  - `faster_whisper_available = true`
  - `gpu_embedding_available = true`
  - `unavailable_reason = null`

### 6.3 媒体链路(关键)

> 用一段 < 30s 的 MP4 测试,放在仓库 `videos/test/sample.mp4`(自己 `mkdir -p` 也行)。这里假设路径 `videos/sample.mp4`。

- [ ] **C1.** ffmpeg 子进程能抽音频:`backend.api.http.server` 进程里读 `data/logs/backend.log` 不应出现 `ffmpeg %s failed`。
- [ ] **C2.** faster-whisper GPU 转写成功。
  - 取证:UI 走完一个视频生成流程后,生成产物里 `workspace/<video>/transcript.json` 存在,segments 数量 > 0。
- [ ] **C3.** 转写期间 GPU 占用真实上升。
  - 取证:另一窗口 `watch -n 1 nvidia-smi`,转写期间 `utilization-gpu` 应 > 30%,显存占用 +0.5 ~ 3 GB(`large-v3-turbo` fp16)。
- [ ] **C4.** FastEmbed embedding 走 CUDA。
  - 取证:`data/logs/backend.log` 无 `CUDAExecutionProvider is not available`;若开启 agent 对话,日志里出现 embedding batch 调用且耗时 < 200ms / 8 docs。
- [ ] **C5.** 截图生成(章节关键帧)成功。
  - 取证:产物里有 `workspace/<video>/chapters/*.jpg`;日志无 `ffmpeg 未生成截图`。

### 6.4 B 站登录(可选,需 Chromium)

```bash
# 推荐装 Google Chrome 的 .deb,避开 snap chromium 的 confinement
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
google-chrome --version
```

- [ ] **D1.** `_resolve_default_browser_path` 能找到 Chrome。
  - 取证:`python -c "from backend.bilibili.ytdlp_bilibili import _resolve_default_browser_path; print(_resolve_default_browser_path())"`
  - 期望:输出 `/usr/bin/google-chrome`(或类似绝对路径)。
- [ ] **D2.** 在 UI「B 站导入」发起二维码扫码,DrissionPage 能拉起 Chrome 窗口。
- [ ] **D3.** 扫码登录成功后 `.env` 写入 `BILIBILI_COOKIE`,关掉再打开仍能拉取订阅。

### 6.5 更新器(POSIX 分支,可选)

> 这一组只在「Pack 形态」下有意义;源码版不会触发 `_restart_pack`。如果要测,把 `updater/apply_and_restart.py` 拿出来手动跑:

```bash
python - <<'PY'
from updater.apply_and_restart import _restart_pack, _is_process_running
import os
print("platform:", os.name)
print("running 1 (self):", _is_process_running(os.getpid()))
print("running 999999 (nonexistent):", _is_process_running(999999))
PY
```

期望:`running 1` 为 `True`,`running 999999` 为 `False`,**不**报 `AttributeError: 'NoneType' object has no attribute 'OpenProcess'`(这是修复前的 bug)。

## 7. 验收失败时的回退指引

| 症状 | 排查命令 | 修复 |
|---|---|---|
| `conda: command not found` | `ls ~/miniconda3/bin/conda` | `eval "$($HOME/miniconda3/bin/conda shell.bash hook)"` |
| `Conda environment 'vsummary' was not found` | `conda env list` | `conda env create -f environment.yml`(GPU) 或 `environment.cpu.yml` |
| `Cannot find module @rollup/...` | `ls src/frontend/node_modules \| head` | 删 `node_modules`,`npm install` 重来 |
| `ONNXRuntime: CUDAExecutionProvider is not available` | `python -c "import onnxruntime as ort; print(ort.get_available_providers())"` | 升级 NVIDIA driver 到 535+;确认 `nvidia-cu12` 全套 wheel 装齐 |
| ffmpeg 抽音频报 `ffmpeg %s failed` | `ffmpeg -version` | `sudo apt install ffmpeg`;检查 `videos/sample.mp4` 是否含音频流(`ffprobe -show_streams videos/sample.mp4`) |
| faster-whisper `float16` 报 `compute type not supported` | `python -c "import ctranslate2; print(ctranslate2.get_supported_compute_types('cuda'))"` | 把 `compute_type` 改为 `int8_float16` 或 `float16` 不行时回退 `int8` |
| Chrome 找不到 | `which google-chrome chromium chromium-browser` | 按 §6.4 装 `.deb` |
| 前端报 `EACCES` | `ls -ld src/frontend/node_modules` | 用非 root 用户重装,或 `sudo chown -R $USER src/frontend/node_modules` |
| 端口被占 | `ss -ltnp \| grep -E '4173\|8001'` | `kill <pid>` 后重跑 `start.sh` |
| `bash: ./start.sh: /bin/bash^M: bad interpreter` | `file start.sh` | `dos2unix start.sh`(若是从 Windows 拷贝) |

## 8. 验收通过标准(签收)

下列**全部**满足,才算本次 Linux 适配通过:

1. §6.1 全部勾选。
2. §6.2 B1 ~ B5 全部勾选。
3. §6.3 C1 ~ C5 全部勾选。
4. (可选)§6.4 / §6.5 视任务范围勾选。

任意一项失败 → 把:
- `data/logs/backend.log` 末尾 200 行
- `data/logs/frontend.log` 末尾 200 行
- 失败截图(若 UI 阶段)
- `nvidia-smi` 输出

一起回贴给开发者。

## 9. 验收完成后的清理(可选)

```bash
# 关掉当前会话启动的后端 + 前端
pkill -f 'backend.api.http.server'
pkill -f 'vite'
```

下次重启只需要 `./start.sh`。
