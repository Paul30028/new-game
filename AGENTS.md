# 新游戏协作入口

开始前读取 coordination/README.md、coordination/BRIEF.md 和 coordination/STATUS.md，然后只读取分配任务及其必要资料。

旧 ark-of-dust 的设计全部属于历史，不默认继承。新项目的画风、镜头和引擎尚未定案。用户不懂代码，负责创作判断和试玩反馈。

调度器使用 Python 3.12 标准库，位于 tools/relay。任务队列在 coordination/queue，运行状态在忽略版本控制的 .relay。不要修改其他执行者的任务或同时在同一工作区写代码。不要把配置、凭据、模型日志和下载的 CLI 二进制提交到 Git。

调度器更改后运行 `python -m unittest discover -s tools/relay -p test_relay.py -v`。保留执行端自身的权限检查。报告真实验证结果，区分离线测试、账号接通、可用素材和实机验收。
