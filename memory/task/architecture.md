# 系统架构说明

## 整体架构

系统采用微服务/模块化架构，主要模块包括：

```
外部请求 → cloudbank-api(接口定义层) → cloudbank-ags(获客/协议)
                                       → cloudbank-lcs(核心/额度)
                                       → cloudbank-ods(运营决策/ODS)
                                       → cloudbank-pcs(支付通道)
```

## 公共依赖

- 所有模块依赖 `cloudbank-common` 提供的公共组件

## 模块间调用关系

- cloudbank-ags 可查询 cloudbank-lcs 的授信状态（通过已有接口）
- cloudbank-ags 与 cloudbank-lcs 之间：只能查询，无其他动作
- cloudbank-ags 可调用获客系统查询授信状态

## 关键业务流程

### 合同上传流程
1. 定时任务触发 → 扫描已签署的合同
2. 根据合同类型和业务状态判断是否上传到行方
3. 授信合同：需查询授信状态 → 根据授信结果和建档状态决定上传策略

### 签署流程
- 授信合同由获客系统穿插调用签署
- 无论授信通过还是拒绝，授信合同都会签署

## 共用方法架构

### AuthFillJob 与 LoanBackFillJob
- 两者共用 `CustomerAgreementServiceImpl.backfillLoanAgreement()` 方法
- **修改共用方法时必须在调用方层面区分**，不能直接修改共用方法本身，否则会影响另一个流程
- 正确做法：在各自 Job 的调用前进行条件过滤，只将符合条件的结果传入共用方法

### 双通道查询模式
授信状态查询采用双通道（核心查询 + LPS fallback）模式：
1. 先通过 `contractQueryFacade.queryCreditReq()` 查询核心系统
2. 核心查询失败时，通过 `applQueryTargetFacade.queryApplByApplNoAddUser()` 走 LPS fallback
3. 使用 `ApplStatusEnum.isFinalState()` 判断是否终态，`checkIsApproval()` 判断是否通过

### ⚠️ AuthFillJob 双路径覆盖风险
AuthFillJob.backfill() 中授信状态判断存在两条路径，修改逻辑时需同时检查两条路径：

```
AuthFillJob.backfill() 调用链路（具体行号）：
  ① queryCreditReq() 查询核心
  ② 核心查询失败 → 降级路径（L121-128，applQueryTargetFacade fallback）
      → isFinalState && !isApproval → 授信拒绝处理
  ③ 核心查询成功 → 主路径（L130-141，else 分支）
      → 直接创建 status="03" 尝试上传
      ⚠️ 此分支未判断授信是否真的通过！
```

**关键风险**：如果核心接口 `queryCreditReq()` 在授信拒绝时返回成功（checkIfFail()=false 且 data 不为空），则拒绝记录会走主路径直接上传。修改授信相关逻辑时，必须同时检查主路径和降级路径的覆盖情况。

**⚠️ DTO 字段限制**：主路径使用的 `CreditReqQueryOutput`（定义在 cloudbank-api 模块）仅含 `status` 字段，**无 `applState` 字段**，无法直接使用 `ApplStatusEnum.isFinalState()/checkIsApproval()` 判断。如需与降级路径保持一致的判断标准，主路径必须额外调用 `applQueryTargetFacade.queryApplByApplNoAddUser()` 获取 `applState`。

### 防重方案选择指南

| 方案 | 改动范围 | 适用场景 | 风险 |
|------|---------|---------|------|
| 接受重复查询 | 仅 Job 层 | 终态不变、拒绝记录少（<总量20%）、调度频率低 | 无 |
| remark 标记+SQL排除 | Job层+Mapper XML | 拒绝记录持续积累影响性能 | remark 语义不干净，需确认其他 Job 不设置类似值 |
| 新增状态枚举 | Job层+枚举+Mapper | 需明确状态语义 | 改动较大 |

**推荐策略**：第一阶段用"接受重复查询"上线并埋点监控，如性能有问题再升级方案。

## ODS 报表执行器架构

cloudbank-ods 模块包含独立的报表执行器体系：

- **ReportExecutor** 接口定义（`cloudbank-ods` 模块）
- **ReportExecutorService** 实现类负责调度执行
- **standard.report 包**下包含具体报表执行器：
  - `LoanAmtStatisticsReportExecutor`：贷款金额统计报表
  - `LoanBalStatisticsReportExecutor`：贷款余额统计报表
  - `LoanBalanceDailyReportExecutor`：贷款余额日报表
- 各执行器通过 `OdsExecutorConfiguration` 以 `@ConditionalOnProperty` 方式按需注册启用

## 报表实体职责分离

核心模块的报表实体与 partner 层 ODS 接入实体**职责完全分离**：
- **核心报表实体**（如 `RGzRepayDetailEntity`）：服务于内部报表生成（`GzRepayDetailReportExecutor`）
- **partner ODS 实体**（如 `CHkRepayDetailEntity`）：服务于银行文件解析落库，使用 `@LineColumn` 注解映射文件列
- 两者无继承关系，数据流独立

## 防重处理模式

定时任务拾取记录后，如果需要跳过某些记录但不改变其状态，需防止无限重处理循环。常用方案：

| 方案 | 说明 | 适用场景 |
|------|------|---------|
| remark 标记 | 更新 remark 字段标记已处理，SQL 排除 | 轻量级，不改变状态流转 |
| 新增状态 | 新增枚举值表示特殊终态 | 需要明确状态语义 |
| 接受重复查询 | 不做特殊处理，每次重查 | 终态不会变化且性能要求不高 |
