# 运行与资源方案

核对日期 2026-11-26。本页用于接入与采购判断，按具体任务读取。官方功能已查阅，个人账户权益和实际运行能力仍需验证。

## 仓库

用户已提供新仓库 [Paul30028/new-game](https://github.com/Paul30028/new-game)。2026-11-26 已克隆至 `C:/Users/holyx/new-game`，远端当前有初始 README 提交。本轮协作文件与调度器由用户授权提交并推送至 codex/local-ai-relay 分支。已有 ark-of-dust 仓库用于旧实现追溯。可复用代码经评估后逐项迁入。工作名称和引擎尚未确定。

## 美术制作工具候选

用户随后明确 Tripo 不可用，以下 Tripo 调研仅保留历史依据，不列为生产依赖。当前替代方案见 [ART_BACKUPS.md](ART_BACKUPS.md)。Blender 与替代服务尚未完成实机样本验证。

- Blender 建议作为模型整理、模块化建筑、材质、骨骼动画、渲染和导出的基础工具。软件免费，所制作作品可商用。编码助手可通过 Python 自动化部分制作与检查，复杂角色与服装变形仍须逐项验收。
- Tripo 可作为图像或文字生成模型初稿的辅助工具，先测试一栋建筑和一个穿长袍人物，再评估是否付费。模块化建筑也可直接由 Blender 脚本生成，不必逐栋消耗生成额度。
- 优先利用已有 Gemini 图像能力制作参考图，随后视资产需要使用 Tripo，再由 Blender 统一尺寸、材质和导出规格。使用 Blender 不锁定实时 3D，可支持预渲染 2D 素材。引擎、镜头与正式画风尚未定案。
- Tripo 官方授权页面存在冲突。当前价格页将免费档标为非商用，2026-11-13 更新的条款 5.2.1 则允许公众商业使用免费输出，并规定权利放弃或公共许可。付费内容与免费内容另有区分，后续订阅不会自动改变原免费输出的性质。正式发行素材须核对生成时适用套餐及条款，必要时取得官方书面确认并保存记录。

参考 [Blender 功能](https://www.blender.org/features/)、[Blender 许可](https://www.blender.org/about/license/)、[Python 自动化](https://docs.blender.org/api/main/info_tips_and_tricks.html)、[Tripo 功能](https://www.tripo3d.ai/help/getting-started/what-features-does-tripo-have)、[Tripo 价格页](https://www.tripo3d.ai/pricing) 与 [Tripo 条款](https://www.tripo3d.ai/terms)。

## DeepSeek

推荐官方 DeepSeek Harness 作为本地工程执行端。其官方指南支持选择工作区、读写文件、执行命令，模型设置通过 DeepSeek API key 配置。其本地 Web UI 可以用于操作。官方聊天网页适合人工讨论与轻量审查。开发预览版本选定后记录版本，升级前验证兼容性。

自动调度可评估 Harness 的 headless / SDK 模式。API 调用费用按实际账户与计费方案核验。当前 API key、余额和允许支出尚未确认。

来源包括 [官方项目](https://github.com/deepseek-ai/deepseek-harness)、[工作区与模型配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/index.md) 和 [命令模式](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md)。

## Google AI Pro

以下为项目用途建议，实际权益以账户和产品的额度页面为准。

| 产品或权益 | 项目用途 |
| --- | --- |
| Antigravity、Gemini CLI / Code Assist | 开发、调试、接棒协调 |
| Gemini / AI Studio 的图像工具 | 角色、建筑和场景素材制作 |
| Gemini Notebook | 经文、历史资料和设定的来源检索 |
| Flow / Veo | 神迹演出镜头及宣传片素材 |
| Flow Music / Lyria | 配乐、音色和音频素材实验 |
| Colab | 批量处理和计算实验 |
| Drive 存储 | 原始素材、导出包与备份 |
| Developer Program 的开发额度 | 小规模云端工具实验，按领取状态和预算启用 |

额度按具体产品和登录方式登记。Gemini CLI 使用 Google 账号登录可适用订阅额度，API key 路径按其计费规则处理。每件拟发行素材记录来源、版本与适用授权。

官方参考包括 [Pro 权益](https://support.google.com/googleone/answer/14534406?hl=en)、[订阅产品](https://gemini.google/subscriptions/)、[CLI 计费](https://geminicli.com/docs/resources/quota-and-pricing/)、[开发者权益](https://developers.google.com/profile/help/benefits) 和 [音乐工具](https://www.flowmusic.app/)。

## 独立调度

推荐先通过一次人工接棒验证文件交接，再接入常驻调度程序。调度程序运行于用户电脑，由普通程序领取任务并调用已连接的执行端。各编码任务使用独立工作树，部分结果和验证记录及时保存。账户限额出现后，结束或隔离旧执行者，再把可恢复任务交给已授权的备用执行端。

电脑休眠、网络故障和所有执行端额度耗尽均会影响续作。Colab 适合批处理，常驻调度使用本地独立进程。调度器已实现并通过离线故障测试，真实账号接棒和资产服务连接尚待实测。参见 [调度器说明](../tools/relay/README.md)。
