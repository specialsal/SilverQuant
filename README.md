# 简介

SilverQuant 是一款基于 [迅投QMT](https://www.thinktrader.net) 
搭建的A股证券交易实盘框架，开箱即可运行

旨在帮助新进入量化领域的同学解决大部分技术启动问题，支持在本地执行策略

组件化设计可以快速根据策略思路搭建原型并建立模拟测试，还能一键切换实盘

投机交易的游戏一共有四个关卡：

1. 保住本金不大幅亏损
2. 可以实现阶段性获利
3. 能够稳定持续的盈利
4. 尽可能地提高利润率

本框架赠予您一套短线防弹衣，避免初入市场即被深度套牢，帮您闯过第一关

之后的道路，还需各位少侠自渡，起落有时，顺逆皆安，岁月沉香，星河璀璨

希望您可以在修罗场里的磨砺中，也能找到属于自己合适的交易模式，共勉 ~

---

# 安装说明

## 系统需求

> 至少是 Windows 系统，国内交易软件生态大都不支持 Mac 和 Linux

## 软件下载

> 下载 Github 桌面版
> 
> https://desktop.github.com/

> 下载 PyCharm CE for Windows（注意是社区免费版即可，不必需Professional）
> 
> https://www.jetbrains.com/pycharm/download/?section=windows

> 下载国金证券 QMT（推荐国金证券的券商版 QMT，用其他券商QMT可以下载他们对应的券商版 QMT）
> 
> 截至2024年，国金开通后半年，有50万入金即可找客服开通免五
> 
> WinRAR下载 https://www.win-rar.com/start.html?&L=0
> 
> QMT 实盘 https://download.gjzq.com.cn/gjty/organ/gjzqqmt.rar
> 
> QMT 模拟 https://download.gjzq.com.cn/temp/organ/gjzqqmt_ceshi.rar

> 如果需要问财大模型相关功能，需要下载 Node.JS 版本大于v20
>
> https://nodejs.org/zh-cn

> 如果需要模拟盘先做策略测试，需要下载 掘金3 的仿真交易软件
> 
> https://www.myquant.cn/terminal


## 配置环境

克隆项目到本地

> 可以直接在Github Desktop里克隆
> 
> 也可以直接在终端输入 `gh repo clone silver6wings/SilverQuant` 然后在Github Desktop里打开

用 PyCharm 打开刚才 clone 的 SilverQuant 文件夹：主菜单 File > Open，选择 SilverQuant 文件夹

安装 Python 3.10 版本
 
> 1. 可以打开PyCharm在IDE里安装
> 2. 也可以直接去Python官网下载：https://www.python.org/downloads/release/python-31010/

安装对应的包
 
> 在PyCharm里安装依赖，打开Terminal输入：`pip install -r requirements.txt`

如果安装慢可以使用镜像源，在指令后加 ` -i [镜像网址]` 

> 可用的镜像网址
> 
> * https://pypi.tuna.tsinghua.edu.cn/simple/ 清华大学
> * https://pypi.mirrors.ustc.edu.cn/simple/ 中国科技大学
> * http://pypi.mirrors.ustc.edu.cn/simple/ 中国科学技术大学
> * http://mirrors.aliyun.com/pypi/simple/ 阿里云

## 启动程序

### 启动QMT交易软件

启动券商版迅投QMT的（勾选）极简模式，确认左下角数据源的链接状态正常

### 配置 Credentials

> 复制项目根目录下的`credentials_sample.py`，改名为`credential.py`并填入自己的参数
> 
> 1. `AUTHENTICATION` 是远程策略获取推送服务的密钥，其他策略不需要可置空
> 2. `CACHE_BASE_PATH` 是本地策略缓存文件夹路径，可不用修改
> 3. `QMT_XXX`的两项是账户相关，需要股票账户id和QMT安装位置，找不到`userdata_mini`文件夹需要先运行QMT一次
> 4. `DING_XXX`的两项是群通知相关，钉钉通知需要建群，然后建立机器人获取 Webhook URL
> 5. `GM_XXX`的两项是模拟盘相关，模拟盘需要自行获取掘金的 Secret Tokens

### 申请机器人

> 如果需要钉钉机器人播报，可以自行建通知群，首先拉至少三人创建一个普通群
>
> 1. 群设置里：机器人 -> 添加机器人 -> 自定义机器人 -> 添加
> 2. 安全设置：加签 获取 `DING_SECRET`
> 3. 勾选“同意xxxx”，并下一步
> 4. Webhook栏，点击复制，获取 `DING_TOKENS`
> 5. 配置到`credentials.py`

### 启动脚本

> PyCharm 中打开 SilverQuant 项目根目录
> 
> 1. 找到 `run_xxxxxx.py` 文件，根目录下
> 2. 找到 `IS_PROD = False` 代码处，将 False 改为 True 切换成实盘
> 3. 确认 QMT 交易软件正在运行
> 4. 启动 `run_xxxxxx.py` 文件，点击绿色小三角

### 参数配置

> 修改参数后需要重新启动程序生效

Pool Conf 股票池相关的参数

> * white_indexes 白名单指数列表，买点会选择这些指数的成分券
> * black_queries 黑名单问财语句，会拉黑当天问财语句里选出来的这些股票绝对不买

Buy Conf 买点相关的参数

> * time_ranges 扫描买点时间段，如果不用买点只用卖点的话可以改成 time_ranges = []
> * interval 扫描买点间隔，取60的约数：1-6, 10, 12, 15, 20, 30
> * order_premium 保证市价单成交的溢价，单位（元）
> 
> 其他看代码中详细说明

Sell Conf 卖点相关的参数

> * time_ranges 扫描卖点时间段，如果不用买点只用卖点的话可以改成 time_ranges = []
> * interval 扫描卖点间隔，取60的约数：1-6, 10, 12, 15, 20, 30
> * order_premium 保证市价单成交的溢价，单位（元）
> 
> 其他看代码中详细说明
 
## 注意事项

> * 尽量保持空仓开始，如果账户预先有股票则由于程序未记录持仓历史导致无法正确卖出
> * 确保手动买入的时候正在开启程序，程序也会自动记录主观买入的持仓
> * 使用过程，需要保证每日开市时开启程序，否则无法正确记录持仓时间和历史的最高价导致卖出无法符合预期
> * 可以在 CACHE_BASE_PATH对应的目录里查看缓存是否正确，关键文件有两个
>    * `assets.csv` 里记录的是账户资金曲线
>    * `held_days.json` 里记录的是持仓天数
>    * `max_price.json` 里记录的是历史最高价格

## 常见问题 Q & A

About setup
 
> * 启动之前最好重启一下系统刷新所有的软件配置

About akshare
 
> * 由于akshare会去各个官方网站抓取公开数据，网站改版会导致爬虫失效，akshare更新比较及时，更新akshare版本到最新会解决一些问题
> * `pip install akshare --upgrade`
 
About pywencai

> * pywencai的原理是去 https://www.iwencai.com/ 抓取数据，所以记得一定要先安装 Node.js
> * 其次检查自己的 prompt 能不能在网页上搜到票

---

# 进阶配置

## 入口说明

策略本身有一些开箱即用的启动程序，可以直接运行

> run_wencai.py
>
> 利用同花顺问财大模型选股买入，需要自行定义prompt选股问句，在`selector/select_wencai.py`中定义
> 
> 可以用来快速建立原型，做模拟盘测试，预估大致收益

> run_remote.py
>
> 对于需要Linux或者分布式大数据计算的场景，可以自行搭建推票服务，程序会通过http协议远程读取数据执行买入

> run_shield.py
>
> 适用于手动买入，量化卖出的半自动场景需求

> run_sword.py
>
> 适用于自定义票池，价格上穿自定义阈值后自动买入预设量额的场景需求

## 组合卖出

可以新建`GroupSeller`自行定义组合卖出的策略群

以下为预定义的卖出策略单元：

```
Hard Seller 硬性止损

根据建仓价的下跌比例绝对止损
# 绝对止盈率  earn_limit = 9.999
# 绝对止损率  risk_limit = 0.979
# 换仓下限乘数  risk_tight = 0.002
```
```
Switch Seller 换仓卖出

盈利未达预期则卖出换仓
# 持仓天数  switch_hold_days = 3
# 换仓上限乘数  switch_require_daily_up = 0.003
# 每天最早换仓时间  switch_begin_time = '14:30'
```
```
Fall Seller 回落止盈

历史最高价回落比例止盈
fall_from_top = [
    (1.02, 9.99, 0.200),
    (1.01, 1.02, 0.800),
]
```
```
Return Seller 回撤止盈

浮盈回撤百分止盈
# 至少保留收益范围
return_of_profit= [
    (1.07, 9.99, 0.10),
]
```
```
MA Seller 跌破均线卖出

均线一般为价格的一个支撑位
# 跌破N日均线卖出 ma_above = 5
```
```
CCI Seller
CCI 冲高或回落卖出
# cci 高卖点阈值  cci_upper = 330.0
# cci 低卖点阈值  cci_lower = 10.0
```
```
Tail Cap Seller 尾盘涨停卖出

尾盘涨停一般视为卖出信号，第二天多低开
# 尾盘开始时间 tail_start_minute = '14:30'
```
```
Open Day Seller 开仓日当天相关参数卖出

# 低于开仓日最低价比例  open_low_rate = 0.99
# 低于开仓日成交量比例  open_vol_rate = 0.60
# 低于开仓日成交量执行时间 tail_vol_time = '14:45'
```
```
Volume Drop Seller 次日成交量萎缩卖出

# 次日缩量止盈的阈值 vol_dec_thre = 0.08
# 次日缩量止盈的时间点  vol_dec_time = '09:46'
# 次日缩量止盈的最大涨幅  vol_dec_limit = 1.03
```
```
Upping Blocker

上升趋势禁止卖出阻断器
日内均价和MACD同时上升时，不执行后续的卖出策略
```

---

# 开源协议

本项目遵循 Apache 2.0 开原许可协议

* 对于代码使用过程中造成的任何损失，作者不承担任何责任
* 在您的策略被验证成熟之前，建议谨慎实盘重仓测试

# 联系作者

使用过程中遇到任何问题欢迎联系作者 VX: junchaoyu_
