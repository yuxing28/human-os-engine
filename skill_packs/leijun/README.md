# 雷军扩展包

这套内容现在已经从默认 `skills/` 目录里隔离出来了。

一句话说：

**它是扩展包，不是主系统默认 skill。**

## 当前规则

1. 主系统默认只加载四个主场景：
   - `sales`
   - `management`
   - `negotiation`
   - `emotion`

2. 雷军这套统一放在：
   - `skill_packs/leijun/`

3. 后面这套内容只能：
   - 单独调用
   - 手动注入测试
   - 或作为可选人格包启用

4. 不能：
   - 自动混进主系统路由
   - 抢主系统大脑
   - 影响默认四个主场景

更上层的统一规则看这里：

- `docs/01_active/EXTENSION_PACK_STANDARD.md`

## 怎么单独测试

统一入口：

- `py -3 scripts/testing/run_leijun_ab_test.py --case all --judge`

说明文档：

- `docs/01_active/LEIJUN_TEST_PACK.md`

它会直接做：

1. 默认主系统
2. 默认主系统 + 指定雷军扩展

也就是标准 A/B 对比，不会碰主系统默认路由。

## 现在包含什么

- `leijun_persona_core`
- `leijun_decision`
- `leijun_product`
- `leijun_management`
- `leijun_communication`
- `leijun_recap`

一句话收口：

**这是一套可选扩展，不是默认内核。**
