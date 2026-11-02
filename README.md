# Xtrace profile skill

可分享的 Xtrace GPU profiling skill：官方 gwatch 探针 + 本地 SM90 兼容适配层，包含安装、插桩、验证及故障排查说明。

## 下载与使用

- [下载 skill ZIP](https://github.com/ouershua2299/xtrace-profile/releases/download/v1.0.0/xtrace-profile-share-v1.zip)
- [下载 tar.gz](https://github.com/ouershua2299/xtrace-profile/releases/download/v1.0.0/xtrace-profile-share-v1.tar.gz)
- [下载 SHA256 校验文件](https://github.com/ouershua2299/xtrace-profile/releases/download/v1.0.0/SHA256SUMS)
- [中文安装与使用指南](xtrace-profile/README.md)
- [Skill 入口](xtrace-profile/SKILL.md)
- [故障排查](xtrace-profile/references/troubleshooting.md)

解压后将 `xtrace-profile` 文件夹放到 `${CODEX_HOME:-$HOME/.codex}/skills/`，在新会话中使用 `$xtrace-profile`。已有同名 skill 时先比较或备份，避免直接覆盖。

也可以克隆本仓库，再安装其中的 `xtrace-profile/` 文件夹。

## 范围

固定后端：gwatch 0.0.35、SM90/SM90a、CUDA ELF ABI8。官方依赖通过 pip 单独下载，仓库不包含官方 wheel/native 库、模型权重或业务 cubin。

本地适配层保留入口寄存器预算，修复直接调用/返回地址重定位，并自动保护跨调用存活寄存器。官方 native 库仍负责探针分配与调度；这是本地兼容版本，不是官方发行版。

历史验证摘要随 skill 附带；原始私有实验数据未包含。新 kernel、输入形状和点位仍需应用侧正确性、事件覆盖及扰动验证。本包不提供任意 kernel 的通用 launcher。
