
## 插件描述

用于控制微信一对一单聊，微信群聊的对话次数

使用前将`config.json.template`复制为`config.json`，并自行配置。

### 默认配置
没有配置的话，会按照如下参数设定默认参数：
```json
    "single_max": 10,
    "group_member_max": 10,
    "group_total_max": 100,
    "limit_interval": "day"
```
### 参数说明：
- single_max: 一对一聊天控制的限额次数
- group_member_max: 群聊里，控制的每个用户的限额次数
- group_total_max: 群聊总的限额次数
- limit_interval: 限额更新方式,`day`按天来更新数据;`hour`按小时清零数据。
