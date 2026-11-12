---
id: F-20261112-1320-platform-code-workspace
title: P1S-01 Code 三段式工作区入口
type: F
author: leemine
modules: [gateway, jiuwenswarm/channels/web, jiuwenswarm/server]
files:
  - gateway/routing/workspace_locations.py
  - gateway/channel_manager/web/app_web_handlers.py
  - jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py
  - jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx
designs: [code-projects:D-20261112-1120-platform-workspace-sync]
author_email: leewanlong@gmail.com
---

# P1S-01 实施记录

用户于 2026-11-12 明确授权启动三段式 UI 开发，随后授权沿用 113.207.105.228 隔离环境与已有测试账号验收。基线 origin/main `5048bd0fbc102bd813f8a4c1246deb11f3d083f6`，独立分支 `codex/platform-p1s01-workspace-20261112`；候选未提交，未修改主线目录、Core、协议或 Provider 源码。关联设计位于管理仓 `docs/design/PLATFORM_WORKSPACE_SYNC_INTEGRATION_20261112.md`，用户确认的是三段式 UI。

## 实际改动与解耦

Code 新对话在输入框上方左侧复用本地项目控件，中间选择 Local/Cloud，Cloud 显示右侧环境/目录菜单。纯云 Web 左侧没有本机桥接时明确不可用，不调用云服务器本地选择器冒充用户机器。本地原项目菜单和 Work 模式保持原流程。

目录请求经原 WebChannel、可信主体、Router/E2A、AgentServer 文件适配器到原 ProjectStore。固定根由目标实例的路径函数决定；浏览按需每页100项，最大10000项。逐级目录描述符拒绝符号链接、隐藏路径和越界。创建文件夹不创建项目；打开目录才由原项目创建逻辑注册，重复打开复用项目 ID。界面在操作中禁发，身份/连接变化使旧响应失效。

环境使用原 cloud.environment.status/ensure，不增加环境数据库或创建器。账号当前只有一个默认绑定；创建动作幂等复用，不创建多个命名环境。

## 与目标设计的差额

平台当前每入口绑定一个执行端，尚无 codeswarm 的同页双端目标目录。候选采用运营配置的入口导航，切换断开原连接后进入目标根 URL，目标原认证和 Runtime 接管。未配置目标时禁用，不静默降级。此实现不声称实现同页双端路由；未发送草稿或附件存在时禁切，避免跳转丢失。跨端草稿迁移和会话/历史同步不在本次实现内。

当前原会话绑定项目根；嵌套于已注册项目的目录返回 PROJECT_ROOT_REQUIRED，要求选择原项目根，避免创建第二份项目。设计中的 project_root + relative_path 子目录会话绑定仍未实现，应由后续会话契约接缝承接。

## 验证记录

任务证据目录：`artifacts/platform-p1s01-20261112/evidence`（管理仓本地，不打入产品）。后端目录/边界27项、Gateway/适配器77项、前端85项通过；完整生产构建通过。WebHandlers回归238通过、1跳过、2失败，两个模型探针失败在独立5048基线同样重现，没有扩充白名单。新增后端最终5项通过；最终工作区与跨入口模式专项17项通过。跨端导航携带一次性 Code 视图提示，不携带项目或凭据。

真实云端验收与收尾结果见管理仓 `docs/verification/PLATFORM_P1S01_IMPLEMENTATION_20261112.md`。本记录不以组件模拟环境状态作为云端验收，不以旧SHA成功结论替代候选验证。未触发每日全量、未提交推送或部署现网。

真实 Web 集成检视发现：WebChannel 对不含 session_id 的请求仍生成传输关联ID；初版目录适配错误拒绝这一参数。已改为仅拒绝显式业务选择器，始终向目录 E2A 委托传 session_id=None，并补有临时关联ID的注册处理链回归。此问题只在真实 Web 链暴露，原单测通过不视为完整验收。

窄屏真实点击发现首页可交互装饰图覆盖新顶部入口；只调整 Code 输入区层级，保留原首页其他交互。工作区菜单也显式处理 Esc，避免输入框持有焦点时菜单无法关闭。两项纳入最终浏览器与组件复验。

最终隔离结果：真实浏览器完整操作14项通过，最后图标/窄屏/Esc/退出复核5项通过，255个已部署前端文件与最终构建摘要一致；云端认证/路径负向及原项目消费者6项通过。原Router已回收专属实例并返回404，项目数据保留；本机专属服务和密码副本已清理。最终统一wheel已打包，但本次真实验证采用记录明确的按角色候选装配，未触发正式CI或部署现网。

## 统一产物交付补充（2026-11-12）

本轮按stable工作流新建Native与External非editable环境，核对锁定Core、协议和SDK实际安装来源。Native 1058通过、3项Windows专属跳过；External 467通过。前端原回归、新增工作区/模式测试及生产构建通过。新增专项纳入`.github/workflows/stable.yml`。既存两个模型探针失败仍按上文基线记录，不扩充白名单。

完整资源清单核验发现旧wheel因setuptools build缓存夹带135个过期前端资源；已保留失败证据并从独立干净源码目录重新打包。新增stable步骤比较整个wheel前端文件集合及每个文件字节，不能只检查当前入口引用的文件。该步骤本机通过，最终运行Web镜像恰好255个资源，与最终dist一致。三个角色同用干净wheel `4a3bc888ceb73f07e76044afdfec9737b8d582bd6b54acbbc42d4dac678e6e7b`；不使用角色源码补丁或额外UI挂载。

交付轮证据位于管理仓本地 `artifacts/platform-p1s01-20261112/delivery/evidence`；完整流程、角色摘要核验、资源回收、提交和远端stable状态见同一管理验收记录的交付续接。前文早期候选/未提交描述为当时事实，不替代本轮结论；没有合入或现网发布结论。

干净wheel最终实测：完整真实浏览器操作14项、图标/窄屏/Esc/退出展示5项均通过，浏览器异常为0。最终Web从wheel安装目录直接提供资源，不通过独立挂载覆盖静态文件。
