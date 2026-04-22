# 模块间接口规范

## 已有接口

| 接口名称 | 调用方 | 提供方 | 说明 |
|---------|-------|-------|------|
| 查询授信状态（queryCreditReq） | cloudbank-ags | cloudbank-lcs（通过 cloudbank-api 定义的 Dubbo 接口） | 查询客户授信状态（通过/拒绝等），返回 CreditReqQueryOutput |
| 查询授信状态（LPS fallback） | cloudbank-ags | 获客系统/LPS | 核心查询失败时的备选通道，返回 ApplOutput 含 applState |

## cloudbank-ags 模块内部关键接口

### 授信状态查询
| 方法 | 所属类 | 说明 |
|------|-------|------|
| queryCreditReq() | contractQueryFacade（定义在 cloudbank-api，LCS 通过 Dubbo @Reference 调用） | 查询核心系统授信状态，返回 CreditReqQueryOutput（仅含 status 字段，无 applState） |
| queryApplByApplNoAddUser() | applQueryTargetFacade | LPS fallback 查询，返回 ApplOutput（含 applState 字段，可配合 ApplStatusEnum 判断） |
| isFinalState() | ApplStatusEnum（外部依赖 tech.qifu.jinke.targets.api.lps） | 判断授信状态是否为终态 |
| checkIsApproval() | ApplStatusEnum（外部依赖 tech.qifu.jinke.targets.api.lps） | 判断授信终态是否为通过 |

### 授信查询 DTO 详情
| DTO | 所属模块 | 关键字段 | 说明 |
|-----|---------|---------|------|
| CreditReqQueryInput | cloudbank-api | custNo, contractNo, requestNo | queryCreditReq() 入参 |
| CreditReqQueryOutput | cloudbank-api | status, creditAmt, dateCredit, dateBegin, dateEnd | queryCreditReq() 出参，**无 applState 字段** |
| ApplOutput | - | applState | queryApplByApplNoAddUser() 出参，含 applState 可用 ApplStatusEnum 判断 |

### 协议数据操作
| 方法 | 所属类/Mapper | 说明 |
|------|--------------|------|
| backfillLoanAgreement() | CustomerAgreementServiceImpl | 协议回填共用方法（授信+放款共用，修改需谨慎） |
| batchUpdateStatusfailed() | CustomerAgreementShardingMapper | 批量将协议状态置为 CA（作废） |
| queryWaitBackFillAgreement | CustomerAgreementMapperExt.xml | 查询待回填协议（status=CN） |

## 接口约束

- 协议模块(cloudbank-ags) ↔ 额度模块(cloudbank-lcs)：只能查询，无其他动作
- 协议模块(cloudbank-ags) → 授信模块/获客系统：可查询授信状态
- backfillLoanAgreement() 是授信/放款共用方法，禁止直接修改其内部逻辑

## partner 层接口

| 接口/类 | 职责 | 说明 |
|---------|------|------|
| PartnerSignServiceImpl | 实现核心 PartnerSignService 接口 | 签署同步+合同上传（SFTP上传+通知银行） |
| HkPartnerSignatureServiceImpl | 继承 AbstractPartnerSignatureService | 安心签开户+签署+下载 |
| HkRepayNotifyJob | 还款通知定时任务 | 继承 AbstractAsyncJssTriggerClientService |
| ChangeDefaultBankcardJob | 换卡定时任务 | 继承 AbstractAsyncJssTriggerClientService |

**partner 层接口特性**：均为核心模块被动调用的扩展点/实现，不包含对核心 Job（AuthFillJob/LoanBackFillJob）的覆写或引用
