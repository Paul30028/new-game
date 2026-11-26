# 本地 AI 调度器

Windows 10/11，Python 3.12，仅使用标准库。调度进程独立于 Codex 聊天运行。

## 启动

双击仓库根目录 `START-AI-RELAY.cmd`，打开控制窗口。首次使用先点“检查接入”，需要时点“登录 Antigravity”。登录窗口完成后关闭，再点“启动 / 继续”。关掉控制窗口不会停止后台队列，点“停止并保存”才停止。重启电脑后需再次打开并启动，目前没有注册开机服务。

开发者命令（在仓库根目录执行）：

```powershell
python tools/relay/setup_local.py
python tools/relay/relay.py doctor
python tools/relay/relay.py enqueue coordination/queue/T001.json
python tools/relay/relay.py run --watch
python tools/relay/relay.py status
python tools/relay/relay.py stop
python tools/relay/relay.py resume
```

`run` 单次处理一个任务尝试。`run --watch` 每十秒检查任务变化，不通过模型轮询。`resume` 只清除停止标志，之后还需启动队列。重复入队会报错，不会覆盖已有进度。

## 实际能力与边界

- SQLite 保存任务状态、尝试次数、执行端冷却时间与事件。任务按依赖串行运行。依赖只有在 `done` 后才放行。
- 每个工作区只有一个调度进程和一个执行者。Windows 文件锁在进程退出后释放。worker 通过 Job Object 管理进程树，失败、超时、停止与崩溃后终止它启动的后代进程。
- 调度进程意外退出时，正在工作的 worker 可以继续。另一个调度进程不会抢占它。worker 意外退出时，下一次启动会检查改动范围，再恢复任务。
- 非零退出且日志含限额特征时，对该执行端冷却 30 分钟，再按任务中的顺序选择其他已启用执行端。限额识别是启发式，未知错误同样留日志并短暂冷却。不会改变账号限额。
- 每次尝试保存提示、修改前文件指纹、模型日志、变化文件清单和验证日志。助手被要求逐步保存 `.relay/checkpoints/<任务号>.md`。不能保证强制终止前的最后一个未保存步骤仍存在。
- 每任务默认最多 3 次，每个 UTC 日默认最多 12 次。重启不会重置次数。UTC 零点等于北京时间 08:00。该限制控制调用次数，不等同于精确 token 或人民币限额。
- 付费 API 默认禁用，须执行端与任务同时明确允许。既有订阅的有效额度与额外计费设置由各产品账户管理。
- 有新结果文件才可进入评审。默认 `review`；只有任务显式启用 `auto_accept`，且全部独立验证命令成功，才自动 `done`。首章设计评审 T001 永远先交人审。
- `allowed_paths` 是事后检查。发现越界修改会保留现场并阻塞，不会擅自回滚。它不是安全沙箱；实际文件与命令权限由执行端自身的沙箱/审批规则控制。默认不加跳过权限的参数。
- 控制器只管理它自己启动的 CLI 任务。无法监控、迁移或强制接管当前 Codex 桌面聊天，也不会控制已有 Antigravity 窗口。请勿让独立聊天同时编辑调度工作区。
- 电脑休眠/关机、断网、没有可用额度、需要人工审批或关键设计决策时会等待。没有承诺无限无人值守开发。

## 执行端

配置模板为 `config.example.json`，本机配置由 `setup_local.py` 生成到忽略版本控制的 `config.local.json`。不把密钥写入配置或仓库。配置中的命令必须是参数数组，直接调用 exe 或 `node + JS`，不接受 cmd/bat/ps1 包装，避免 shell 拼接。

Antigravity 应用和独立 `agy` CLI 是两个入口。官方支持 `-p` 无界面任务与 JSON 输出，默认采用其 `auto` 模式和终端沙箱。CLI 使用其自身保存的登录状态，调度器不读取凭据。`install_agy.py` 从官方清单下载 CLI 到 `.relay/bin`，通过 SHA-512 校验后才使用，不修改系统 PATH。

本机实测补充：已完成 Antigravity 的真实 T001 文件任务，但账号/环境提示 auto 模式不可用，回退到默认模式，其内部终端返回 -65536。不要据此禁用权限检查。后续可把已审阅的确定性测试命令配置在任务 `verify` 中，由调度器执行；助手自身的终端能力仍需单独排查。真实接入证据见 `coordination/RELAY_VALIDATION.md`。

Codex 适配 `codex exec --sandbox workspace-write --json -`。安装路径可自动探测，是否启用由本机配置决定。DeepSeek Harness 预留桌面内置 CLI 启动参数，未取得 API 预算前保持关闭，真实响应尚未验收。

官方参考：[Antigravity 无界面模式](https://antigravity.google/docs/cli/headless/)、[安装](https://antigravity.google/docs/getting-started?tab=cli)、[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)。

## 任务与验收

新增任务先写 Markdown 说明与 JSON 清单，再调用 `enqueue`。清单必须给出明确修改路径、结果文件、执行端顺序、最大尝试次数与超时。示例见 `coordination/queue/T001.json`。

```powershell
# 阅读结果与实际差异后接受人工评审任务
python tools/relay/relay.py accept T001
# 修复阻塞后重试，历史尝试次数仍保留
python tools/relay/relay.py retry T001
```

JSON 中 `verify` 是独立命令数组，支持 `{python}` 与 `{root}` 占位符。不填验证命令不会自动完成。达到终身任务尝试上限后，需另建有明确目标的返工任务，避免无限重试。

控制器日志在 `.relay/runner.log`；每次尝试记录在 `.relay/runs/<任务>/<次数>/`；这些文件可能包含项目内容，应留在本机。`.relay` 与本机配置已加入 `.gitignore`。

## 验证

```powershell
python -m unittest discover -s tools/relay -p test_relay.py -v
```

测试使用本地假执行端，不消耗任何模型额度。覆盖限额接棒、检查点恢复、父进程及 worker 崩溃、进程树清理、独占锁、重启后预算、结果缺失、范围越界、验证失败与付费执行端阻止。离线通过不等于已完成真实账号接棒验收。
