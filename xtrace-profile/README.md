# Xtrace 本地兼容版：同事使用指南

此目录可独立复制使用，也可以安装为 Codex skill。它包含官方 gwatch 探针的本地兼容适配代码、操作规范、验证工具和排障说明。官方 native 库仍负责探针分配与调度；本地层修复寄存器元数据、直接调用/返回重定位，并添加调用者存活寄存器保护。不是官方发行版，也不是完整独立重实现。

## 1. 下载、解压和安装 skill

从分享者提供的 `xtrace-profile-share-v1.zip` 或 `.tar.gz` 下载其中一种，并取得同目录的 `SHA256SUMS`。在下载目录校验对应文件：

```bash
sha256sum --ignore-missing -c SHA256SUMS
unzip xtrace-profile-share-v1.zip
# 或：tar -xzf xtrace-profile-share-v1.tar.gz
```

解压后进入 `xtrace-profile`，可直接阅读本文和运行脚本。安装到 Codex：

```bash
skill_dest="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skill_dest"
# 如果目标已存在，先比较/备份已有版本；不要覆盖正在使用的版本。
test ! -e "$skill_dest/xtrace-profile" && cp -R xtrace-profile "$skill_dest/"
```

上述复制命令在解压目录的父目录运行。开启新的 Codex 会话，用 `$xtrace-profile` 调用。其他助手可直接阅读 `SKILL.md`，再按本文执行脚本。

## 2. 安装运行依赖

支持的固定后端为 **gwatch 0.0.35 / SM90、SM90a / CUDA ELF ABI8**。官方该版本 wheel 是 CPython 3.12、Linux x86-64、glibc 2.28+，不要仅依据包元数据中的 Python >=3.8 安装。版本和下载文件见 [官方 PyPI](https://pypi.org/project/gwatch/0.0.35/)。

在解压目录内建立独立环境：

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/doctor.py
```

CUDA 驱动、GPU 作业和应用自身 PyTorch/通信环境由使用者提供。本工具不会替换它们。native 库需要能加载 CUDA 12 的 runtime/CUPTI；若报缺库，见排障文档。CPU 插桩工具与应用 launcher 可以使用不同的 Python 环境，通过 cubin、JSON 和原始 trace 文件交接。

可在同平台联网机器准备离线依赖：

```bash
python3.12 -m pip download -r requirements.txt -d wheelhouse
# 将 wheelhouse 复制到目标机器，再在目标虚拟环境执行：
python -m pip install --no-index --find-links wheelhouse -r requirements.txt
```

若缺少 CUDA 12 runtime/CUPTI，可在此独立环境安装历史验证使用的兼容库：

```bash
python -m pip install nvidia-cuda-runtime-cu12==12.8.90 nvidia-cuda-cupti-cu12==12.8.90
cuda_py_libs="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/nvidia"
export LD_LIBRARY_PATH="$cuda_py_libs/cuda_runtime/lib:$cuda_py_libs/cuda_cupti/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python scripts/doctor.py
```

离线机器需要将这两个包也加入 `pip download` 列表。驱动仍由宿主机提供。CUDA 共享库和驱动不是上述默认 wheelhouse 的完整组成部分。分享包不附带官方 wheel、native 库、模型权重、业务 cubin 或内部输入数据。

## 3. 首次使用：生成插桩产物

先取得**实际运行的原始 cubin**，固定入口符号、shape、grid/block、cluster、动态 shared memory 和应用状态；用 nvdisasm/cuobjdump 与源码映射核实 SASS 点位。不要通过 `serialize()` 把重建文件当作原始文件。

复制 `examples/sites.template.json` 为 `sites.json`，填入本次二进制的 SHA256、入口正则、真实 launch 形状及原始指令索引。模板有意留空，不能直接运行。SM90 上 `insert_index = 原始 PC / 16`；它不是源码行号。`records` 要覆盖整个 launch 中的动态访问次数并留余量；`expected_by_warp` 是完整事件序列约束，不会过滤运行中的 warp。

```bash
sha256sum original.cubin
python scripts/splice_cubin.py --cubin original.cubin --config sites.json --output traced.cubin
```

必须选择新的输出路径。阅读生成的 `traced.json`，核对资源、参数 ABI、role 上限和调用/返回审计。`traced.upstream-unvalidated.cubin` 只供诊断，不能当成验证成功产物。

## 4. 在应用中运行和分析

包内不提供可以启动任意 kernel 的通用 launcher：参数、通信状态和依赖必须由应用正确传递。

1. 通过已有 launcher 加载 `traced.cubin`，按 proof 的 `parameter_abi` 保留全部原始参数，再追加 trace 指针。按 `schema.total_bytes` 分配并清零 buffer，保持生命周期直到运行结束。
2. 保留原来的 stream、cluster、动态共享内存和 PDL/Graph 依赖；多卡通信需要所有 peer 配对执行。每次重复前按应用协议重置状态。
3. 比较原版/插桩版输出；记录同一次 trace-producing launch 的耗时上界；同步后保存原始 buffer 为 `.npy`。示例格式和校验命令见 [package-api.md](references/package-api.md#raw-validation)。
4. 验证事件数量、warp/CTA/模式覆盖、buffer 边界、时钟范围，再做 OFF/ON 交错重复计时。静态成功不等于运行正确，低总开销也不等于局部时长绝对准确。

点位选择和 K-stage 解读见 [k-stage.md](references/k-stage.md)，完整比较协议见 [validation.md](references/validation.md)。当前适配器不支持运行时 CTA/warp/迭代采样过滤、跨 SM 绝对时钟比较或任意新架构。

## 5. 排障与可复现记录

先运行 `python scripts/doctor.py > doctor.json`，再按 [故障排查表](references/troubleshooting.md) 定位。向同事报告时提供版本、doctor 输出、配置、原始/产物 SHA、完整异常、proof 和最小 launcher；只在获准时分享业务 cubin/输入。

本地历史验证覆盖四条 MiMo 路径、512 次分布式调用和 4096 次 rank 输出检查。摘要在 [validation-summary.json](references/validation-summary.json)；原始实验数据不在分享包中，这些历史结果不能替代接收者的新环境验证。
