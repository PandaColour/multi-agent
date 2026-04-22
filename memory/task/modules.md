# 系统模块清单

## 模块列表

| 模块名称 | 工作空间 | 职责说明 |
|---------|---------|---------|
| cloudbank-ags | D:/company/workspace/cloudbank/cloudbank-ags | 获客系统/协议模块/签署管理，包含授信合同上传逻辑、定时任务触发 |
| cloudbank-api | D:/company/workspace/cloudbank/cloudbank-api | API 接口定义层，为各业务域定义 Facade 接口契约和 DTO 数据传输对象 |
| cloudbank-common | D:/company/workspace/cloudbank/cloudbank-common | 公共组件，通用工具、基础实体、公共接口定义 |
| cloudbank-lcs | D:/company/workspace/cloudbank/cloudbank-lcs | 核心服务（贷款核心），包含额度模块等核心业务逻辑 |
| cloudbank-ods | D:/company/workspace/cloudbank/cloudbank-ods | 运营决策系统，ODS数据清洗、宽表生成、报表输出 |
| cloudbank-pcs | D:/company/workspace/cloudbank/cloudbank-pcs | 支付通道系统（Payment Channel System），负责支付通道管理、二类户操作、交易处理、鉴权签约、合作方对接 |

## 模块职责边界

- **cloudbank-ags**：协议管理、合同签署、合同上传、定时任务调度（涉及上传的部分）
- **cloudbank-lcs**：核心业务逻辑、额度管理、授信状态管理
- **cloudbank-common**：跨模块共享的 DTO、枚举、工具类、接口定义
- **cloudbank-api**：API 接口定义层，为各业务域（AMS、LCS、PCS、AGS、FAS、ARRCOLL等）定义 Facade 接口契约和 DTO，实现层在各业务模块中
- **cloudbank-ods**：ODS 数据清洗、宽表生成、报表输出、快照处理
- **cloudbank-pcs**：支付通道系统，对接银行/第三方支付通道、二类户操作、交易处理、鉴权签约

## cloudbank-ags 模块内关键类

### 定时任务（Job）
- **AuthFillJob**：授信流程协议回填 Job，拾取 status=CN 且 type=AP 的协议，查询授信状态后决定上传或作废。backfill() 方法含两条路径：降级路径（L121-128，核心查询失败走 fallback）和主路径（L130-141，核心查询成功分支）
- **LoanBackFillJob**：放款流程协议回填 Job，与 AuthFillJob 共用 backfillLoanAgreement() 方法

### 核心服务
- **CustomerAgreementServiceImpl**：协议服务核心实现，包含 backfillLoanAgreement() 等共用方法
- **contractQueryFacade**：授信状态查询门面（定义在 cloudbank-api 模块），提供 queryCreditReq() 方法，返回 CreditReqQueryOutput（仅含 status 字段，无 applState，无法直接用 ApplStatusEnum 判断授信通过/拒绝）
- **applQueryTargetFacade**：LPS fallback 查询门面，提供 queryApplByApplNoAddUser() 方法，返回 ApplOutput（含 applState 字段，可配合 ApplStatusEnum 判断）

### 数据访问
- **CustomerAgreementShardingMapper**：协议分表数据访问，包含 batchUpdateStatusfailed() 批量作废方法
- **CustomerAgreementMapperExt.xml**：协议 SQL 映射，包含 queryWaitBackFillAgreement 等查询

### 枚举
- **ApplStatusEnum**：授信状态枚举，包含 isFinalState()、checkIsApproval() 等判断方法

## 机构层扩展

- **qifu-partner**（工作空间：D:/company/workspace/qifu-hkbank/cloudbank）：部分模块在机构层有覆写或扩展，修改核心逻辑时需检查并同步适配
  - **HkPartnerSignatureServiceImpl**：继承 AbstractPartnerSignatureService，处理安心签开户+签署+下载
  - **PartnerSignServiceImpl**：实现核心 PartnerSignService 接口，处理签署同步+合同上传（SFTP上传+通知银行）
  - PartnerSignServiceImpl.uploadAgreement() 是上传层面的扩展点，被核心模块被动调用，与业务决策逻辑无关
  - partner 层 Job 仅有 HkRepayNotifyJob（还款通知）和 ChangeDefaultBankcardJob（换卡），均继承 AbstractAsyncJssTriggerClientService，与核心 AuthFillJob/LoanBackFillJob 无关联
  - partner 层不存在对 AuthFillJob 或授信合同上传逻辑的自定义覆写
