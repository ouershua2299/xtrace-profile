# Xtrace 故障排查

先分清：环境加载失败、静态插桩拒绝、GPU 运行失败、trace 校验失败、结果解释问题。保留原始输入和首次错误；不要为了通过检查删除 backend gate、强行压低寄存器数或改 trace schema。

| 现象 | 检查与处理 |
|---|---|
| pip 找不到 0.0.35 的匹配版本 | 用 Python 3.12 / Linux x86-64 / glibc 2.28+；检查 pip 源是否同步该版本。不要直接升级 gwatch 来绕过固定后端。 |
| 缺 libcudart.so.12 / libcupti.so.12 | 用 `ldd` 检查 doctor 给出的 native 路径，提供 CUDA 12 runtime/CUPTI 的真实库目录，并通过进程级 `LD_LIBRARY_PATH` 暴露。CUDA 13 编译器不自动提供这些兼容库；不要把 .so.13 软链伪装成 .so.12。 |
| Unrecognized native library / 不支持版本 | 对照官方包版本与 native SHA；检查 PYTHONPATH、重复安装。不要修改 allowlist SHA 来接受未审计库。 |
| Input SHA does not match / 多个入口 | 对实际 cubin 重算 SHA，重新映射点位；用精确转义的符号正则选一个入口。编译变化后不能复用旧 PC。 |
| 入口 REG 从 96 变 104、too many resources | 检查原始/原版输出/本地修复产物是否混淆。入口预算和动态 warp-role cap 是不同概念；用适配器审计结果，禁止仅手改 REGCOUNT 强制启动。 |
| 编译日志或 SASS 出现 STL/LDL | 先比较未插桩原版、源码 clock 版本和二进制插桩版本；源码插桩造成的编译 spill 与 serializer 元数据膨胀是不同问题。本适配器不修复任意源程序 spill。 |
| 无可用 GPR/UR/谓词寄存器 | 保留失败点，检查异步操作和调用者存活值；尝试语义明确的另一边界或减少点位。移动点位改变了测量含义，必须记录。不能屏蔽自动保护来强行打点。 |
| INIT 不支配打点/位于循环/分配重试区 | 选一次执行且覆盖所有打点的 INIT；动态增配须经过成功分支。不要把 TRY_ALLOC 发出等同于分配已成功。 |
| 不支持 CALL/RET/ABI/控制流 | 当前仅实现已识别 SM90 直接调用约定。保留失败二进制与 disassembly，进行专门后端适配；不能自动退回 PTX 重编译后仍宣称原指令保真。 |
| 输出文件已存在 | 使用新目录/文件名；旧 proof 与新 cubin 混用会失去可复现性。 |
| illegal access / 输出不一致 / 多卡 hang | 停止扩展实验，先检查原始/新增参数 ABI、buffer 长度和生命周期、所有 rank 的配对 launch、PDL/cluster/共享内存、状态重置。用小案例和 memcheck 定位；保留失败产物。 |
| trace 为空/数量错误/guard 非零 | 核对实际加载 SHA、模式/warp/CTA 路径、初始化、record 容量和同步。根据真实 route 推导覆盖，不能仅把 expected 数字改成观测结果。 |
| 时钟校验失败 | 使用同次 launch 的可信耗时上界和合理 SM 时钟上界；26-bit 时间戳存在回绕。超出窗口时拆分实验；不要删除界限检查。 |
| overhead 为负或 max-rank 掩盖变化 | 交错 OFF/ON、固定输入与 route、保存各 rank 和整链耗时、增加独立重复；负数不是 profiler 加速证据。整条链计时也不是单 kernel 开销。 |

## 最小问题报告

- doctor JSON、操作系统/驱动/toolkit、应用环境版本。
- 原始和插桩 cubin SHA、入口、launch 形状/属性、配置与完整 proof。
- 失败命令、完整日志、原始输出是否正确；能否在单卡/小输入复现。
- 多卡说明 rank 数、通信与状态重置协议；不运行破坏协议的“单 rank”替代测试。
- trace schema、原始 trace、对应 launch 时间、预期序列的推导方式。

分享包仅提供 CPU 插桩与解析辅助；GPU launcher 和业务期望值检查由每个项目实现。历史归档未附带时，应明确“历史摘要可读，原始数据尚未独立复核”。
