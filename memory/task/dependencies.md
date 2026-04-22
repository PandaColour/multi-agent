# 模块依赖关系与开发顺序

## 依赖原则

- cloudbank-common 变更需最先开发，其他模块依赖它
- 接口提供方的变更需先于调用方

## 典型开发顺序

1. cloudbank-common（公共组件）
2. cloudbank-lcs（核心服务，提供基础能力）
3. cloudbank-ags（获客/协议，调用核心服务）
4. cloudbank-pcs（流程中心）
5. cloudbank-ods（运营决策）
6. cloudbank-api（网关层，最后集成）

## 注意事项

- 如果只是修改模块内部逻辑，不涉及公共接口变更，则无严格开发顺序要求
- 需关注机构层（如 qifu-partner）的同步适配
